"""
Quant V2 布林带策略（Bollinger Bands）
"""

from collections import deque

from data.bar import Bar
from strategy.base_strategy import BaseStrategy


class BollingerStrategy(BaseStrategy):
    def __init__(self, name: str = "BollingerStrategy", period: int = 20, num_std: float = 2.0, **kwargs):
        super().__init__(name=name, **kwargs)
        self.period = period
        self.num_std = num_std
        self.closes: deque = deque(maxlen=period)
        self.initialize()

    def initialize(self):
        print(f"[{self.name}] Initialized with BOLL({self.period}, {self.num_std})")

    def on_bar(self, bar: Bar):
        self.closes.append(bar.close)
        if len(self.closes) < self.period:
            return
        closes = list(self.closes)
        mid = sum(closes) / self.period
        variance = sum((c - mid) ** 2 for c in closes) / self.period
        std = variance ** 0.5
        upper = mid + self.num_std * std
        lower = mid - self.num_std * std
        symbol = bar.symbol
        current_position = self._get_position_qty(symbol)

        if current_position == 0:
            if bar.close < lower:
                self.buy(symbol=symbol, price=bar.close, qty=100, reason=f"跌破下轨 {lower:.2f}（超卖）")
                print(f"[{self.name}] BUY {symbol} @ {bar.close:.2f}, Lower={lower:.2f}, Mid={mid:.2f}")
        else:
            if bar.close > mid:
                self.sell(symbol=symbol, price=bar.close, qty=current_position, reason=f"回归中轨上方 {mid:.2f}")
                print(f"[{self.name}] SELL {symbol} @ {bar.close:.2f}, Mid={mid:.2f}")

    def _get_position_qty(self, symbol: str) -> float:
        if self.portfolio is not None:
            pos = self.portfolio.get_position(symbol)
            return pos.qty if pos else 0.0
        return 0.0

    def on_trade(self, trade):
        print(f"[{self.name}] Trade executed: {trade}")
