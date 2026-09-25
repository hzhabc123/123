"""
Quant V2 回测引擎

主循环（每根bar）：
  1. 撮合上一根bar留下的挂单（broker.match_orders）
  2. 给策略注入上下文 set_bar_context（防前视）
  3. 策略.on_bar 产生信号
  4. 每个信号：风控校验 → 仓位计算 → 转成订单提交给broker
  5. 更新组合市值，记录净值曲线
  6. 回撤控制（RiskManager）
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

    def __init__(self, strategy: BaseStrategy, portfolio: Portfolio,
                 broker: Optional[BacktestBroker] = None,
                 risk_manager: Optional[RiskManager] = None,
                 position_sizer: Optional[PositionSizer] = None,
                 symbol: str = "", lookback: int = 500):
        self.strategy = strategy
        self.portfolio = portfolio
        self.broker = broker or BacktestBroker()
        self.risk_manager = risk_manager or RiskManager(RiskConfig())
        self.position_sizer = position_sizer or FixedSizer(100)
        self.symbol = symbol
        self.lookback = lookback
        self.strategy.set_portfolio(self.portfolio)
        self.equity_curve: List[dict] = []
        self.all_trades = portfolio.trades
        self.strategy_orders = []
        self.broker.on_trade_callback = self._on_trade

    def _on_trade(self, trade):
        self.portfolio.on_trade(trade)
        try:
            self.strategy.on_trade(trade)
        except Exception:
            pass

    def run(self, bars: List[Bar], start_equity: bool = True) -> dict:
        for index, bar in enumerate(bars):
            self._on_bar(bar, index, bars)
        return self._summarize()

    def _on_bar(self, bar: Bar, index: int, bars: List[Bar]):
        trades = self.broker.match_orders(bar)
        lookback_start = max(0, index - self.lookback)
        history = bars[lookback_start:index]
        self.strategy.set_bar_context(bar, index, history)
        self.strategy.on_bar(bar)
        signals = self.strategy.get_signals()
        for signal in signals:
            self._process_signal(signal, bar)
        self.portfolio.update_market_value(bar.symbol, bar.close)
        equity = self.portfolio.calculate_equity()
        if equity > self.risk_manager.peak_equity:
            self.risk_manager.peak_equity = equity
        self.equity_curve.append({
            "datetime": bar.datetime, "equity": equity,
            "cash": self.portfolio.account.cash,
            "market_value": self.portfolio.calculate_market_value(),
            "close": bar.close,
        })

    def _process_signal(self, signal, bar: Bar):
        if signal.direction == SignalDirection.BUY:
            side = Side.BUY
        elif signal.direction == SignalDirection.SELL:
            side = Side.SELL
        elif signal.direction == SignalDirection.COVER:
            side = Side.BUY
        else:
            return

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

        result = self.risk_manager.validate_signal(signal, self.portfolio)
        if not result.passed:
            self._reject_signal(signal, result.reason)
            return

        if side == Side.BUY:
            cost = signal.price * qty
            if cost > self.portfolio.account.available_cash:
                qty = int(self.portfolio.account.available_cash / signal.price * 0.98 // 100 * 100)
                if qty <= 0:
                    self._reject_signal(signal, "可用资金不足")
                    return

        order = self.broker.create_order(
            symbol=signal.symbol, side=side,
            order_type=signal.order_type if signal.order_type else OrderType.MARKET,
            price=signal.price, qty=qty, strategy_id=signal.strategy_id or self.strategy.name,
        )
        self.strategy_orders.append(order)

    def _reject_signal(self, signal, reason: str):
        if not hasattr(self, "rejected_signals"):
            self.rejected_signals = []
        self.rejected_signals.append({"signal": signal, "reason": reason})

    def get_equity_curve(self) -> List[dict]:
        return self.equity_curve

    def get_all_trades(self) -> list:
        return self.portfolio.trades

    def get_all_orders(self) -> list:
        return self.strategy_orders

    @property
    def event_count(self) -> int:
        return len(self.equity_curve)

    def analyzer(self):
        from performance.analyzer import PerformanceAnalyzer
        return PerformanceAnalyzer(self.equity_curve, self.portfolio.trades)

    def _summarize(self) -> dict:
        equity = self.portfolio.account.equity
        start = self.portfolio.account.initial_cash
        return {
            "bars": len(self.equity_curve), "trades": len(self.portfolio.trades),
            "orders": len(self.strategy_orders), "final_equity": equity,
            "total_return": (equity - start) / start if start else 0.0,
            "rejected": getattr(self, "rejected_signals", []),
        }
