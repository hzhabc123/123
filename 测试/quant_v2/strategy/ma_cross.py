"""
Quant V2 双均线交叉策略（Moving Average Crossover）
"""

from typing import Optional
from collections import deque

from data.bar import Bar
from strategy.base_strategy import BaseStrategy
from risk.stop_manager import create_atr_stop


class MACrossStrategy(BaseStrategy):
    def __init__(self, name: str = "MACrossStrategy", short_period: int = 5, long_period: int = 20,
                 atr_period: int = 14, atr_multiplier: float = 2.0, **kwargs):
        super().__init__(name=name, **kwargs)
        self.short_period = short_period
        self.long_period = long_period
        self.atr_period = atr_period
        self.atr_multiplier = atr_multiplier
        self.closes: deque = deque(maxlen=long_period + 1)
        self._prev_short = 0.0
        self._prev_long = 0.0
        self._entry_price = 0.0
        self._stop_price = 0.0
        self.initialize()

    def initialize(self):
        print(f"[{self.name}] Initialized with MA{self.short_period}/MA{self.long_period}, ATR={self.atr_period}x{self.atr_multiplier}")

    def on_bar(self, bar: Bar):
        self.closes.append(bar.close)
        if len(self.closes) < self.long_period + 1:
            return
        closes = list(self.closes)
        short_ma = sum(closes[-self.short_period:]) / self.short_period
        long_ma = sum(closes[-self.long_period:]) / self.long_period
        symbol = bar.symbol
        current_position = self._get_position_qty(symbol)
        atr = self._calculate_atr(bar)

        if current_position == 0:
            if self._prev_short <= self._prev_long and short_ma > long_ma:
                self.buy(symbol=symbol, price=bar.close, qty=100, reason=f"金叉 MA{self.short_period}={short_ma:.2f} 上穿 MA{self.long_period}={long_ma:.2f}")
                self._entry_price = bar.close
                self._stop_price = self._entry_price - atr * self.atr_multiplier
                print(f"[{self.name}] BUY {symbol} @ {bar.close:.2f}, Stop={self._stop_price:.2f}, ATR={atr:.2f}")
        else:
            self._stop_price = max(self._stop_price, bar.close - atr * self.atr_multiplier) if self._stop_price else bar.close - atr * self.atr_multiplier
            exited = False
            reason = ""
            if bar.close < self._stop_price:
                exited, reason = True, f"ATR止损 @ {self._stop_price:.2f}"
            elif self._prev_short >= self._prev_long and short_ma < long_ma:
                exited, reason = True, f"死叉 MA{self.short_period}={short_ma:.2f} 下穿 MA{self.long_period}={long_ma:.2f}"
            if exited:
                self.sell(symbol=symbol, price=bar.close, qty=current_position, reason=reason)
                self._entry_price = 0.0
                self._stop_price = 0.0
                print(f"[{self.name}] SELL {symbol} @ {bar.close:.2f}, Reason: {reason}")
        self._prev_short = short_ma
        self._prev_long = long_ma

    def _calculate_atr(self, bar: Bar) -> float:
        history = self.get_history_bars(self.atr_period + 1)
        if len(history) < self.atr_period + 1:
            return bar.close * 0.02
        true_ranges = []
        for i in range(1, len(history)):
            prev_bar, curr_bar = history[i - 1], history[i]
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
