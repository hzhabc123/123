"""
Quant V2 唐奇安通道策略（Donchian Channel）
"""

from typing import Optional
from collections import deque

from data.bar import Bar
from strategy.base_strategy import BaseStrategy
from signals.trading_signal import Signal
from risk.stop_manager import create_atr_stop, StopOrder


class DonchianStrategy(BaseStrategy):
    def __init__(self, name: str = "DonchianStrategy", entry_period: int = 20, exit_period: int = 10,
                 atr_period: int = 20, atr_multiplier: float = 2.0, **kwargs):
        super().__init__(name=name, **kwargs)
        self.entry_period = entry_period
        self.exit_period = exit_period
        self.atr_period = atr_period
        self.atr_multiplier = atr_multiplier
        self.position: Optional[str] = None
        self.entry_price: float = 0.0
        self.stop_order: Optional[StopOrder] = None
        self.highs: deque = deque(maxlen=entry_period)
        self.lows: deque = deque(maxlen=exit_period)
        self.closes: deque = deque(maxlen=atr_period + 1)
        self.initialize()

    def initialize(self):
        print(f"[{self.name}] Initialized with entry={self.entry_period}, exit={self.exit_period}, ATR={self.atr_period}x{self.atr_multiplier}")

    def on_bar(self, bar: Bar):
        self.highs.append(bar.high)
        self.lows.append(bar.low)
        self.closes.append(bar.close)
        if len(self.closes) < max(self.entry_period, self.atr_period + 1):
            return
        prev_highs = list(self.highs)[:-1]
        prev_lows = list(self.lows)[:-1]
        entry_high = max(prev_highs) if prev_highs else 0.0
        exit_low = min(prev_lows) if prev_lows else 0.0
        atr = self._calculate_atr()
        symbol = bar.symbol
        current_position = self._get_position_qty(symbol)

        if current_position == 0:
            if bar.close > entry_high:
                self.buy(symbol=symbol, price=bar.close, qty=100, reason=f"突破{self.entry_period}日最高价{entry_high:.2f}")
                self.entry_price = bar.close
                self.stop_order = create_atr_stop(entry_price=bar.close, direction="long", atr=atr, atr_multiplier=self.atr_multiplier, symbol=symbol)
                print(f"[{self.name}] BUY {symbol} @ {bar.close:.2f}, Stop={self.stop_order.current_stop:.2f}, ATR={atr:.2f}")
        else:
            should_exit = False
            exit_reason = ""
            if self.stop_order and self.stop_order.update(bar.close):
                should_exit = True
                exit_reason = f"触发ATR止损 @ {self.stop_order.current_stop:.2f}"
            elif bar.close < exit_low:
                should_exit = True
                exit_reason = f"跌破{self.exit_period}日最低价{exit_low:.2f}"
            if should_exit:
                self.sell(symbol=symbol, price=bar.close, qty=current_position, reason=exit_reason)
                print(f"[{self.name}] SELL {symbol} @ {bar.close:.2f}, Reason: {exit_reason}")
                self.stop_order = None
                self.entry_price = 0.0

    def _calculate_atr(self) -> float:
        history_bars = self.get_history_bars(self.atr_period + 1)
        if len(history_bars) < self.atr_period + 1:
            return 0.0
        true_ranges = []
        for i in range(1, len(history_bars)):
            prev_bar, curr_bar = history_bars[i - 1], history_bars[i]
            tr = max(curr_bar.high - curr_bar.low, abs(curr_bar.high - prev_bar.close), abs(curr_bar.low - prev_bar.close))
            true_ranges.append(tr)
        return sum(true_ranges[-self.atr_period:]) / self.atr_period

    def _get_position_qty(self, symbol: str) -> float:
        if self.portfolio is not None:
            pos = self.portfolio.get_position(symbol)
            return pos.qty if pos else 0.0
        return 0.0

    def on_trade(self, trade):
        print(f"[{self.name}] Trade executed: {trade}")

    def summary(self) -> str:
        lines = [super().summary(), f"Entry Period: {self.entry_period}", f"Exit Period: {self.exit_period}",
                 f"ATR Period: {self.atr_period}", f"ATR Multiplier: {self.atr_multiplier}", f"Current Position: {self.position or 'None'}", f"Entry Price: {self.entry_price:.2f}"]
        if self.stop_order:
            lines.append(f"Stop Price: {self.stop_order.current_stop:.2f}")
        return "\n".join(lines)


class DonchianStrategyV2(BaseStrategy):
    def __init__(self, name: str = "DonchianV2", entry_period: int = 20, exit_period: int = 10,
                 atr_period: int = 20, atr_multiplier: float = 2.0, trend_ma_period: int = 50, **kwargs):
        super().__init__(name=name, **kwargs)
        self.entry_period = entry_period
        self.exit_period = exit_period
        self.atr_period = atr_period
        self.atr_multiplier = atr_multiplier
        self.trend_ma_period = trend_ma_period
        self.position_side: str = "flat"
        self.entry_price: float = 0.0
        self.stop_order: Optional[StopOrder] = None
        self.highs: deque = deque(maxlen=entry_period)
        self.lows: deque = deque(maxlen=exit_period)
        self.closes: deque = deque(maxlen=max(entry_period, trend_ma_period) + 1)
        self.initialize()

    def initialize(self):
        print(f"[{self.name}] V2 Initialized with trend filter MA{self.trend_ma_period}")

    def on_bar(self, bar: Bar):
        self.highs.append(bar.high)
        self.lows.append(bar.low)
        self.closes.append(bar.close)
        if len(self.closes) < max(self.entry_period, self.trend_ma_period, self.atr_period + 1):
            return
        entry_high = max(self.highs)
        exit_low = min(self.lows)
        entry_low = min(self.highs)
        exit_high = max(self.lows)
        atr = self._calculate_atr()
        trend_ma = self._calculate_ma(self.trend_ma_period)
        symbol = bar.symbol
        current_position = self._get_position_qty(symbol)

        if current_position == 0:
            if bar.close > entry_high and bar.close > trend_ma:
                self.buy(symbol=symbol, price=bar.close, qty=100, reason=f"突破高点{entry_high:.2f} + 趋势向上")
                self._set_stop(bar.close, "long", atr)
            elif bar.close < entry_low and bar.close < trend_ma:
                self.sell(symbol=symbol, price=bar.close, qty=100, reason=f"跌破低点{entry_low:.2f} + 趋势向下")
                self._set_stop(bar.close, "short", atr)
        else:
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
                if self.position_side == "long":
                    self.sell(symbol=symbol, price=bar.close, qty=current_position, reason=exit_reason)
                else:
                    self.buy(symbol=symbol, price=bar.close, qty=current_position, reason=exit_reason)
                self.stop_order = None
                self.entry_price = 0.0
                self.position_side = "flat"

    def _calculate_atr(self) -> float:
        history_bars = self.get_history_bars(self.atr_period + 1)
        if len(history_bars) < self.atr_period + 1:
            return 0.0
        true_ranges = []
        for i in range(1, len(history_bars)):
            prev_bar, curr_bar = history_bars[i - 1], history_bars[i]
            tr = max(curr_bar.high - curr_bar.low, abs(curr_bar.high - prev_bar.close), abs(curr_bar.low - prev_bar.close))
            true_ranges.append(tr)
        return sum(true_ranges[-self.atr_period:]) / self.atr_period

    def _calculate_ma(self, period: int) -> float:
        if len(self.closes) < period:
            return 0.0
        return sum(list(self.closes)[-period:]) / period

    def _set_stop(self, entry_price: float, direction: str, atr: float):
        self.entry_price = entry_price
        self.position_side = direction
        self.stop_order = create_atr_stop(entry_price=entry_price, direction=direction, atr=atr, atr_multiplier=self.atr_multiplier, symbol="")

    def _get_position_qty(self, symbol: str) -> float:
        return 0.0
