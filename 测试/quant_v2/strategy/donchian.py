"""
Quant V2 唐奇安通道策略（Donchian Channel）
经典趋势跟踪策略，配合ATR止损
"""

from typing import List, Optional
from collections import deque

from data.bar import Bar
from strategy.base_strategy import BaseStrategy
from signals.trading_signal import Signal
from risk.stop_manager import create_atr_stop, StopOrder


class DonchianStrategy(BaseStrategy):
    """
    唐奇安通道策略
    
    策略逻辑：
    1. 价格突破N日最高价 → 做多
    2. 价格跌破N日最低价 → 平仓
    3. 配合ATR动态止损（2倍ATR）
    
    参数：
    - entry_period: 入场周期（默认20日）
    - exit_period: 离场周期（默认10日）
    - atr_period: ATR周期（默认20日）
    - atr_multiplier: ATR止损倍数（默认2.0）
    """
    
    def __init__(self, name: str = "DonchianStrategy", 
                 entry_period: int = 20, 
                 exit_period: int = 10,
                 atr_period: int = 20,
                 atr_multiplier: float = 2.0,
                 **kwargs):
        super().__init__(name=name, **kwargs)
        
        self.entry_period = entry_period
        self.exit_period = exit_period
        self.atr_period = atr_period
        self.atr_multiplier = atr_multiplier
        
        # 状态跟踪
        self.position: Optional[str] = None  # 当前持仓标的
        self.entry_price: float = 0.0
        self.stop_order: Optional[StopOrder] = None
        
        # 数据缓存
        self.highs: deque = deque(maxlen=entry_period)
        self.lows: deque = deque(maxlen=exit_period)
        self.closes: deque = deque(maxlen=atr_period + 1)
        
        # 最近一期指标快照（供可视化上报，口径=策略实际计算）
        self._last_indicator: dict = {}
        
        # 初始化
        self.initialize()
    
    def initialize(self):
        """策略初始化"""
        print(f"[{self.name}] Initialized with entry={self.entry_period}, "
              f"exit={self.exit_period}, ATR={self.atr_period}x{self.atr_multiplier}")
    
    def on_bar(self, bar: Bar):
        """
        处理新的Bar数据
        
        策略逻辑：
        1. 计算唐奇安通道（最高价、最低价）
        2. 计算ATR
        3. 生成交易信号
        """
        # 更新数据缓存
        self.highs.append(bar.high)
        self.lows.append(bar.low)
        self.closes.append(bar.close)

        # 数据不足，等待
        if len(self.closes) < max(self.entry_period, self.atr_period + 1):
            return

        # 计算唐奇安通道
        # 注意：self.highs 已含当前bar的high，需用当前bar之前的N日作为突破参考。
        # 由于收盘可能等于当日高点，这里保守采用"当日收盘 > 前entry_period日最高价(不含今日)"
        prev_highs = list(self.highs)[:-1]  # 不含当前bar
        prev_lows = list(self.lows)[:-1]
        entry_high = max(prev_highs) if prev_highs else 0.0
        exit_low = min(prev_lows) if prev_lows else 0.0

        # 计算ATR
        atr = self._calculate_atr()

        # 记录本 bar 指标快照（口径=本策略实际计算，供可视化上报）
        self._last_indicator = {
            "entry_high": entry_high,
            "exit_low": exit_low,
            "atr": atr,
            "close": bar.close,
        }
        
        # 获取当前持仓
        symbol = bar.symbol
        current_position = self._get_position_qty(symbol)
        
        # 策略逻辑
        if current_position == 0:
            # 空仓：检查是否突破入场通道
            if bar.close > entry_high:
                # 做多信号
                signal = self.buy(
                    symbol=symbol,
                    price=bar.close,
                    qty=100,  # 仓位由PositionSizer决定
                    reason=f"突破{self.entry_period}日最高价{entry_high:.2f}"
                )
                
                # 设置ATR止损
                self.entry_price = bar.close
                self.stop_order = create_atr_stop(
                    entry_price=bar.close,
                    direction="long",
                    atr=atr,
                    atr_multiplier=self.atr_multiplier,
                    symbol=symbol
                )
                
                print(f"[{self.name}] BUY {symbol} @ {bar.close:.2f}, "
                      f"Stop={self.stop_order.current_stop:.2f}, ATR={atr:.2f}")
        
        else:
            # 持仓中：检查止损和离场
            should_exit = False
            exit_reason = ""
            
            # 1. 检查止损
            if self.stop_order and self.stop_order.update(bar.close):
                should_exit = True
                exit_reason = f"触发ATR止损 @ {self.stop_order.current_stop:.2f}"
            
            # 2. 检查离场通道
            elif bar.close < exit_low:
                should_exit = True
                exit_reason = f"跌破{self.exit_period}日最低价{exit_low:.2f}"
            
            # 生成卖出信号
            if should_exit:
                signal = self.sell(
                    symbol=symbol,
                    price=bar.close,
                    qty=current_position,
                    reason=exit_reason
                )
                
                print(f"[{self.name}] SELL {symbol} @ {bar.close:.2f}, "
                      f"Reason: {exit_reason}")
                
                # 清除止损订单
                self.stop_order = None
                self.entry_price = 0.0
    
    def indicator_values(self) -> dict:
        """
        返回策略当前 bar 实际使用的指标（供 Recorder 上报，口径与策略内部一致）。
        未进入计算期时无指标，返回空 dict。
        """
        return dict(self._last_indicator)

    def _calculate_atr(self) -> float:
        """
        计算ATR（Average True Range）
        
        ATR = SMA(True Range, period)
        True Range = max(High-Low, |High-PrevClose|, |Low-PrevClose|)
        """
        if len(self.closes) < self.atr_period + 1:
            return 0.0
        
        # 获取历史Bar
        history_bars = self.get_history_bars(self.atr_period + 1)
        if len(history_bars) < self.atr_period + 1:
            return 0.0
        
        # 计算True Range
        true_ranges = []
        for i in range(1, len(history_bars)):
            prev_bar = history_bars[i - 1]
            curr_bar = history_bars[i]
            
            tr = max(
                curr_bar.high - curr_bar.low,
                abs(curr_bar.high - prev_bar.close),
                abs(curr_bar.low - prev_bar.close)
            )
            true_ranges.append(tr)
        
        # 计算ATR（简单平均）
        atr = sum(true_ranges[-self.atr_period:]) / self.atr_period
        
        return atr
    
    def _get_position_qty(self, symbol: str) -> float:
        """
        获取持仓数量

        优先从 Portfolio 读取真实持仓；没有绑定组合时回退内部状态。
        """
        if self.portfolio is not None:
            pos = self.portfolio.get_position(symbol)
            return pos.qty if pos else 0.0
        return 0.0
    
    def on_trade(self, trade):
        """成交回调"""
        print(f"[{self.name}] Trade executed: {trade}")
    
    def summary(self) -> str:
        """策略摘要"""
        lines = [
            super().summary(),
            f"Entry Period: {self.entry_period}",
            f"Exit Period: {self.exit_period}",
            f"ATR Period: {self.atr_period}",
            f"ATR Multiplier: {self.atr_multiplier}",
            f"Current Position: {self.position or 'None'}",
            f"Entry Price: {self.entry_price:.2f}",
        ]
        
        if self.stop_order:
            lines.append(f"Stop Price: {self.stop_order.current_stop:.2f}")
        
        return "\n".join(lines)
    

class DonchianStrategyV2(BaseStrategy):
    """
    唐奇安通道策略V2（增强版）
    
    改进：
    1. 支持多空双向交易
    2. 加入趋势过滤器（均线）
    3. 动态调整止损距离
    """
    
    def __init__(self, name: str = "DonchianV2",
                 entry_period: int = 20,
                 exit_period: int = 10,
                 atr_period: int = 20,
                 atr_multiplier: float = 2.0,
                 trend_ma_period: int = 50,
                 **kwargs):
        super().__init__(name=name, **kwargs)
        
        self.entry_period = entry_period
        self.exit_period = exit_period
        self.atr_period = atr_period
        self.atr_multiplier = atr_multiplier
        self.trend_ma_period = trend_ma_period
        
        # 状态
        self.position_side: str = "flat"  # 'long', 'short', 'flat'
        self.entry_price: float = 0.0
        self.stop_order: Optional[StopOrder] = None
        
        # 数据缓存
        self.highs: deque = deque(maxlen=entry_period)
        self.lows: deque = deque(maxlen=exit_period)
        self.closes: deque = deque(maxlen=max(entry_period, trend_ma_period) + 1)
        
        self.initialize()
    
    def initialize(self):
        """策略初始化"""
        print(f"[{self.name}] V2 Initialized with trend filter MA{self.trend_ma_period}")
    
    def on_bar(self, bar: Bar):
        """处理Bar数据"""
        self.highs.append(bar.high)
        self.lows.append(bar.low)
        self.closes.append(bar.close)
        
        # 数据不足
        if len(self.closes) < max(self.entry_period, self.trend_ma_period, self.atr_period + 1):
            return
        
        # 计算指标
        entry_high = max(self.highs)
        exit_low = min(self.lows)
        entry_low = min(self.highs)  # 做空用
        exit_high = max(self.lows)   # 做空用
        atr = self._calculate_atr()
        trend_ma = self._calculate_ma(self.trend_ma_period)
        
        symbol = bar.symbol
        current_position = self._get_position_qty(symbol)
        
        # 策略逻辑
        if current_position == 0:
            # 空仓：检查开仓信号
            # 做多：突破高点 + 趋势向上
            if bar.close > entry_high and bar.close > trend_ma:
                signal = self.buy(
                    symbol=symbol,
                    price=bar.close,
                    qty=100,
                    reason=f"突破高点{entry_high:.2f} + 趋势向上"
                )
                self._set_stop(bar.close, "long", atr)
            
            # 做空：跌破低点 + 趋势向下
            elif bar.close < entry_low and bar.close < trend_ma:
                signal = self.sell(
                    symbol=symbol,
                    price=bar.close,
                    qty=100,
                    reason=f"跌破低点{entry_low:.2f} + 趋势向下"
                )
                self._set_stop(bar.close, "short", atr)
        
        else:
            # 持仓中：检查离场
            should_exit = False
            exit_reason = ""
            
            if self.stop_order and self.stop_order.update(bar.close):
                should_exit = True
                exit_reason = f"止损 @ {self.stop_order.current_stop:.2f}"
            
            elif self.position_side == "long" and bar.close < exit_low:
                should_exit = True
                exit_reason = f"跌破离场低点{exit_low:.2f}"
            
            elif self.position_side == "short" and bar.close > exit_high:
                should_exit = True
                exit_reason = f"突破离场高点{exit_high:.2f}"
            
            if should_exit:
                # 平仓
                if self.position_side == "long":
                    self.sell(symbol=symbol, price=bar.close, qty=current_position, reason=exit_reason)
                else:
                    self.buy(symbol=symbol, price=bar.close, qty=current_position, reason=exit_reason)
                
                self.stop_order = None
                self.entry_price = 0.0
                self.position_side = "flat"
    
    def _calculate_atr(self) -> float:
        """计算ATR"""
        history_bars = self.get_history_bars(self.atr_period + 1)
        if len(history_bars) < self.atr_period + 1:
            return 0.0
        
        true_ranges = []
        for i in range(1, len(history_bars)):
            prev_bar = history_bars[i - 1]
            curr_bar = history_bars[i]
            tr = max(
                curr_bar.high - curr_bar.low,
                abs(curr_bar.high - prev_bar.close),
                abs(curr_bar.low - prev_bar.close)
            )
            true_ranges.append(tr)
        
        return sum(true_ranges[-self.atr_period:]) / self.atr_period
    
    def _calculate_ma(self, period: int) -> float:
        """计算移动平均"""
        if len(self.closes) < period:
            return 0.0
        return sum(list(self.closes)[-period:]) / period
    
    def _set_stop(self, entry_price: float, direction: str, atr: float):
        """设置止损"""
        self.entry_price = entry_price
        self.position_side = direction
        self.stop_order = create_atr_stop(
            entry_price=entry_price,
            direction=direction,
            atr=atr,
            atr_multiplier=self.atr_multiplier,
            symbol=""
        )
    
    def _get_position_qty(self, symbol: str) -> float:
        """获取持仓"""
        return 0.0  # TODO: 从Portfolio获取
