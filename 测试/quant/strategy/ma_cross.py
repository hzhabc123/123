# strategy/ma_cross.py
from collections import deque
from data.bar import Bar
from strategy.base_strategy import BaseStrategy
from strategy.signal import (
    Signal,
    SignalType
)
class MACrossStrategy(BaseStrategy):
    def __init__(
        self,
        symbol: str,
        fast_period: int = 5,
        slow_period: int = 20,
        trade_size: int = 100
    ):
        super().__init__(symbol)
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.trade_size = trade_size
        self.close_buffer = deque(
            maxlen=slow_period
        )
        self.prev_fast_ma = None
        self.prev_slow_ma = None
    def on_bar(self, bar: Bar):
        self.close_buffer.append(bar.close)
        if len(self.close_buffer) < self.slow_period:
            return
        closes = list(self.close_buffer)
        fast_ma = (
            sum(closes[-self.fast_period:])
            / self.fast_period
        )
        slow_ma = (
            sum(closes)
            / self.slow_period
        )
        signal = None
        if (
            self.prev_fast_ma is not None
            and self.prev_slow_ma is not None
        ):
            # 金叉
            if (
                self.prev_fast_ma <= self.prev_slow_ma
                and fast_ma > slow_ma
            ):
                if self.position == 0:
                    signal = Signal(
                        symbol=self.symbol,
                        signal_type=SignalType.BUY,
                        price=bar.close,
                        volume=self.trade_size
                    )
                    self.position += self.trade_size
            # 死叉
            elif (
                self.prev_fast_ma >= self.prev_slow_ma
                and fast_ma < slow_ma
            ):
                if self.position > 0:
                    signal = Signal(
                        symbol=self.symbol,
                        signal_type=SignalType.SELL,
                        price=bar.close,
                        volume=self.trade_size
                    )
                    self.position -= self.trade_size
        # 无论是否产生信号，都更新均线状态
        self.prev_fast_ma = fast_ma
        self.prev_slow_ma = slow_ma
        return signal
