"""
Quant V2 动量策略（Momentum）
"""

from collections import deque

from data.bar import Bar
from strategy.base_strategy import BaseStrategy


class MomentumStrategy(BaseStrategy):
    def __init__(self, name: str = "MomentumStrategy", lookback: int = 20, threshold: float = 0.0, **kwargs):
        super().__init__(name=name, **kwargs)
        self.lookback = lookback
        self.threshold = threshold
        self.closes: deque = deque(maxlen=lookback + 1)
        self.initialize()

    def initialize(self):
        print(f"[{self.name}] Initialized with Momentum({self.lookback}), threshold={self.threshold}")

    def on_bar(self, bar: Bar):
        self.closes.append(bar.close)
        if len(self.closes) < self.lookback + 1:
            return
        closes = list(self.closes)
        ref_price = closes[0]
        momentum = (bar.close - ref_price) / ref_price if ref_price else 0.0
        symbol = bar.symbol
        current_position = self._get_position_qty(symbol)

        if current_position == 0:
            if momentum > self.threshold:
                self.buy(symbol=symbol, price=bar.close, qty=100, reason=f"动量 {momentum:.2%} > {self.threshold:.2%}（{self.lookback}日）")
                print(f"[{self.name}] BUY {symbol} @ {bar.close:.2f}, Momentum={momentum:.2%}")
        else:
            if momentum < 0:
                self.sell(symbol=symbol, price=bar.close, qty=current_position, reason=f"动量转负 {momentum:.2%}")
                print(f"[{self.name}] SELL {symbol} @ {bar.close:.2f}, Momentum={momentum:.2%}")

    def _get_position_qty(self, symbol: str) -> float:
        if self.portfolio is not None:
            pos = self.portfolio.get_position(symbol)
            return pos.qty if pos else 0.0
        return 0.0

    def on_trade(self, trade):
        print(f"[{self.name}] Trade executed: {trade}")
