"""
Quant V2 海龟交易法（Turtle Trading）
"""

from collections import deque

from data.bar import Bar
from strategy.base_strategy import BaseStrategy


class TurtleStrategy(BaseStrategy):
    def __init__(self, name: str = "TurtleStrategy", entry_period: int = 20, exit_period: int = 10,
                 atr_period: int = 20, atr_multiplier: float = 2.0, pyramid: bool = False, **kwargs):
        super().__init__(name=name, **kwargs)
        self.entry_period = entry_period
        self.exit_period = exit_period
        self.atr_period = atr_period
        self.atr_multiplier = atr_multiplier
        self.pyramid = pyramid
        self.highs: deque = deque(maxlen=entry_period + 1)
        self.lows: deque = deque(maxlen=exit_period + 1)
        self._entry_price = 0.0
        self._stop_price = 0.0
        self._entry_n = 0.0
        self.initialize()

    def initialize(self):
        print(f"[{self.name}] Initialized with entry={self.entry_period}, exit={self.exit_period}, N*{self.atr_multiplier}")

    def on_bar(self, bar: Bar):
        self.highs.append(bar.high)
        self.lows.append(bar.low)
        if len(self.highs) < max(self.entry_period, self.atr_period + 1):
            return
        prev_highs = list(self.highs)[:-1]
        prev_lows = list(self.lows)[:-1]
        entry_high = max(prev_highs)
        exit_low = min(prev_lows)
        n = self._calculate_atr(bar)
        symbol = bar.symbol
        current_position = self._get_position_qty(symbol)

        if current_position == 0:
            if bar.close > entry_high:
                self.buy(symbol=symbol, price=bar.close, qty=100, reason=f"突破{self.entry_period}日高点 {entry_high:.2f}")
                self._entry_price = bar.close
                self._entry_n = n
                self._stop_price = self._entry_price - self.atr_multiplier * n
                print(f"[{self.name}] BUY {symbol} @ {bar.close:.2f}, N={n:.2f}, Stop={self._stop_price:.2f}")
        else:
            self._stop_price = max(self._stop_price, bar.close - self.atr_multiplier * n) if self._stop_price else bar.close - self.atr_multiplier * n
            exited = False
            reason = ""
            if bar.close < self._stop_price:
                exited, reason = True, f"2N止损 @ {self._stop_price:.2f}"
            elif bar.close < exit_low:
                exited, reason = True, f"跌破{self.exit_period}日低点 {exit_low:.2f}"
            if exited:
                self.sell(symbol=symbol, price=bar.close, qty=current_position, reason=reason)
                self._entry_price = 0.0
                self._stop_price = 0.0
                self._entry_n = 0.0
                print(f"[{self.name}] SELL {symbol} @ {bar.close:.2f}, Reason: {reason}")

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
