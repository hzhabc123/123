"""
Quant V2 RSI 均值回归策略（Relative Strength Index）
"""

from collections import deque

from data.bar import Bar
from strategy.base_strategy import BaseStrategy


class RSIStrategy(BaseStrategy):
    def __init__(self, name: str = "RSIStrategy", period: int = 14, oversold: float = 30.0,
                 overbought: float = 70.0, exit_rsi: float = 50.0, **kwargs):
        super().__init__(name=name, **kwargs)
        self.period = period
        self.oversold = oversold
        self.overbought = overbought
        self.exit_rsi = exit_rsi
        self.closes: deque = deque(maxlen=period + 1)
        self.initialize()

    def initialize(self):
        print(f"[{self.name}] Initialized with RSI({self.period}), OS={self.oversold}, OB={self.overbought}")

    def on_bar(self, bar: Bar):
        self.closes.append(bar.close)
        if len(self.closes) < self.period + 1:
            return
        rsi = self._calculate_rsi()
        symbol = bar.symbol
        current_position = self._get_position_qty(symbol)

        if current_position == 0:
            if rsi < self.oversold:
                self.buy(symbol=symbol, price=bar.close, qty=100, reason=f"RSI={rsi:.1f} 超卖(<{self.oversold})")
                print(f"[{self.name}] BUY {symbol} @ {bar.close:.2f}, RSI={rsi:.1f}")
        else:
            if rsi > self.exit_rsi:
                self.sell(symbol=symbol, price=bar.close, qty=current_position, reason=f"RSI={rsi:.1f} 回升到中线({self.exit_rsi})上方")
                print(f"[{self.name}] SELL {symbol} @ {bar.close:.2f}, RSI={rsi:.1f}")

    def _calculate_rsi(self) -> float:
        closes = list(self.closes)
        gains, losses = [], []
        for i in range(1, len(closes)):
            diff = closes[i] - closes[i - 1]
            gains.append(max(diff, 0.0))
            losses.append(max(-diff, 0.0))
        avg_gain = sum(gains) / len(gains)
        avg_loss = sum(losses) / len(losses)
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100.0 - (100.0 / (1.0 + rs))

    def _get_position_qty(self, symbol: str) -> float:
        if self.portfolio is not None:
            pos = self.portfolio.get_position(symbol)
            return pos.qty if pos else 0.0
        return 0.0

    def on_trade(self, trade):
        print(f"[{self.name}] Trade executed: {trade}")
