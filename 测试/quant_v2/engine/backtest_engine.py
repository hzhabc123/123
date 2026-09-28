"""
Quant V2 回测引擎

主循环（每根bar）：
  1. 撮合上一根bar留下的挂单（broker.match_orders）→ 成交回调 portfolio.on_trade / 策略.on_trade
  2. 给策略注入上下文 set_bar_context（防前视）
  3. 策略.on_bar 产生信号
  4. 每个信号：风控校验 → 仓位计算 → 转成LIMIT/MARKET订单提交给broker
  5. 更新组合市值，记录净值曲线
  6. 回撤控制（RiskManager）

结束：输出净值曲线 / 全部成交 / 订单
"""

from typing import List, Optional

from data.bar import Bar
from strategy.base_strategy import BaseStrategy
from risk.risk_manager import RiskManager, RiskConfig
from risk.position_sizer import PositionSizer, FixedSizer
from portfolio.portfolio import Portfolio
from broker.backtest_broker import BacktestBroker
from broker.matcher import OrderMatcher
from broker.fee_model import FeeModel, ChinaAFeeModel
from core.enums import Side, OrderType, SignalDirection


class BacktestEngine:
    """回测引擎"""

    def __init__(
        self,
        strategy: BaseStrategy,
        portfolio: Portfolio,
        broker: Optional[BacktestBroker] = None,
        risk_manager: Optional[RiskManager] = None,
        position_sizer: Optional[PositionSizer] = None,
        symbol: str = "",
        lookback: int = 500,
        recorder: Optional[object] = None,
    ):
        self.strategy = strategy
        self.portfolio = portfolio
        self.broker = broker or BacktestBroker()
        self.risk_manager = risk_manager or RiskManager(RiskConfig())
        self.position_sizer = position_sizer or FixedSizer(100)
        self.symbol = symbol
        self.lookback = lookback
        # 可视化记录器（可选注入；无则不影响原有回测行为）
        self.recorder = recorder

        # 绑定组合到策略（供策略查询真实持仓）
        self.strategy.set_portfolio(self.portfolio)

        # 净值曲线
        self.equity_curve: List[dict] = []
        # 所有成交
        self.all_trades = portfolio.trades
        # 策略持有的订单
        self.strategy_orders = []

        # 连接 broker 成交回调 → portfolio
        self.broker.on_trade_callback = self._on_trade

    def _on_trade(self, trade):
        """broker 成交 → 更新组合"""
        self.portfolio.on_trade(trade)
        # 同步给策略
        try:
            self.strategy.on_trade(trade)
        except Exception:
            pass

        # 可视化：记录成交（Trade 点，口径 = portfolio 实际入账）
        if self.recorder is not None:
            try:
                self.recorder.record_trade(trade)
            except Exception:
                pass

    def run(self, bars: List[Bar], start_equity: bool = True) -> dict:
        """
        运行回测主循环

        Parameters
        ----------
        bars : List[Bar]
            按时间顺序排列的K线
        start_equity : bool
            是否在首bar记录初始净值（默认True）

        Returns
        -------
        dict
            回测结果摘要
        """
        for index, bar in enumerate(bars):
            self._on_bar(bar, index, bars)
        return self._summarize()

    def _on_bar(self, bar: Bar, index: int, bars: List[Bar]):
        """处理单根bar"""
        # 可视化：记录本根 bar
        if self.recorder is not None:
            try:
                self.recorder.record_bar(bar)
            except Exception:
                pass

        # 1. 撮合上一根bar挂单
        trades = self.broker.match_orders(bar)

        # 2. 注入策略上下文（防前视：只给到 index 之前的 bar）
        lookback_start = max(0, index - self.lookback)
        history = bars[lookback_start:index]
        self.strategy.set_bar_context(bar, index, history)

        # 3. 策略产生信号
        self.strategy.on_bar(bar)
        signals = self.strategy.get_signals()

        # 可视化：上报策略本 bar 实际计算使用的指标（口径=策略内部，非事后重算）
        if self.recorder is not None:
            try:
                for name, value in self.strategy.indicator_values().items():
                    self.recorder.record_indicator(name, value, bar.datetime)
            except Exception:
                pass

        # 4. 逐信号处理
        for signal in signals:
            # 可视化：记录策略信号（Signal 点，与成交严格区分）
            if self.recorder is not None:
                try:
                    self.recorder.record_signal(signal)
                except Exception:
                    pass
            self._process_signal(signal, bar)

        # 5. 更新组合市值 & 记录净值
        self.portfolio.update_market_value(bar.symbol, bar.close)
        equity = self.portfolio.calculate_equity()

        # 风控更新峰值
        if equity > self.risk_manager.peak_equity:
            self.risk_manager.peak_equity = equity

        self.equity_curve.append({
            "datetime": bar.datetime,
            "equity": equity,
            "cash": self.portfolio.account.cash,
            "market_value": self.portfolio.calculate_market_value(),
            "close": bar.close,
        })

        # 可视化：记录净值 / 回撤 / 持仓（口径 = portfolio）
        if self.recorder is not None:
            try:
                self.recorder.record_equity(self.equity_curve[-1])
                peak = self.risk_manager.peak_equity
                dd = (peak - equity) / peak if peak else 0.0
                self.recorder.record_drawdown(dd, bar.datetime)
                for sym, pos in self.portfolio.positions.items():
                    self.recorder.record_position(pos)
            except Exception:
                pass

    def _process_signal(self, signal, bar: Bar):
        """处理单个信号：风控 → 仓位 → 订单"""
        # 方向映射
        if signal.direction == SignalDirection.BUY:
            side = Side.BUY
        elif signal.direction == SignalDirection.SELL:
            side = Side.SELL
        elif signal.direction == SignalDirection.COVER:
            side = Side.BUY
        else:  # SHORT 暂不支持现货做空
            return

        # 1. 卖出时若仓位不足则截断
        qty = signal.target_qty or self.position_sizer.calculate_qty(
            symbol=signal.symbol, price=signal.price, portfolio=self.portfolio, bar=bar
        )
        if side == Side.SELL:
            pos = self.portfolio.get_position(signal.symbol)
            have = pos.qty if pos else 0
            qty = min(qty, have)
            if qty <= 0:
                self._reject_signal(signal, "持仓不足")
                return

        # 2. 风控
        result = self.risk_manager.validate_signal(signal, self.portfolio)
        if not result.passed:
            self._reject_signal(signal, result.reason)
            return

        # 3. 买入时校验可用资金
        if side == Side.BUY:
            cost = signal.price * qty
            if cost > self.portfolio.account.available_cash:
                # 按可用资金截断
                qty = int(self.portfolio.account.available_cash / signal.price * 0.98 // 100 * 100)
                if qty <= 0:
                    self._reject_signal(signal, "可用资金不足")
                    return

        # 4. 生成订单（默认市价单，下一bar开盘成交）
        order = self.broker.create_order(
            symbol=signal.symbol,
            side=side,
            order_type=signal.order_type if signal.order_type else OrderType.MARKET,
            price=signal.price,
            qty=qty,
            strategy_id=signal.strategy_id or self.strategy.name,
        )
        self.strategy_orders.append(order)
        # 可视化：记录订单（Order 点，观察执行延迟 = T+1 撮合）
        if self.recorder is not None:
            try:
                self.recorder.record_order(order)
            except Exception:
                pass

    def _reject_signal(self, signal, reason: str):
        """记录被拒信号（供测试/日志）"""
        if not hasattr(self, "rejected_signals"):
            self.rejected_signals = []
        self.rejected_signals.append({"signal": signal, "reason": reason})
        # 可视化：记录风控/资金拒绝（Reject 点，看未执行原因）
        if self.recorder is not None:
            try:
                self.recorder.record_risk_reject(signal, None, reason)
            except Exception:
                pass

    # ---------------- 结果 ---------------- #

    def get_equity_curve(self) -> List[dict]:
        return self.equity_curve

    def get_all_trades(self) -> list:
        return self.portfolio.trades

    def get_all_orders(self) -> list:
        return self.strategy_orders

    @property
    def event_count(self) -> int:
        """已处理的bar数（近似事件数）"""
        return len(self.equity_curve)

    def analyzer(self):
        """构造绩效分析器"""
        from performance.analyzer import PerformanceAnalyzer
        return PerformanceAnalyzer(self.equity_curve, self.portfolio.trades)

    def _summarize(self) -> dict:
        equity = self.portfolio.account.equity
        start = self.portfolio.account.initial_cash
        return {
            "bars": len(self.equity_curve),
            "trades": len(self.portfolio.trades),
            "orders": len(self.strategy_orders),
            "final_equity": equity,
            "total_return": (equity - start) / start if start else 0.0,
            "rejected": getattr(self, "rejected_signals", []),
        }
