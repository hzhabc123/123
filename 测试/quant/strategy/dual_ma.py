# strategy/dual_ma.py
from collections import deque

from data.bar import Bar
from strategy.base_strategy import BaseStrategy
from strategy.signal import (
    Signal,
    SignalType
)


class DualMAStrategy(BaseStrategy):
    """
    双均线策略

    短周期均线上穿长周期均线（金叉）买入，
    短周期均线下穿长周期均线（死叉）卖出。

    与 ma_cross.py 相比修复了两点：
    1. 每根 K 线都会更新上一根均线状态，
       不会因为当根发出信号而漏更新；
    2. 策略内部正确跟踪持仓 position，
       保证死叉时能够发出卖出信号。
    """

    def __init__(
        self,
        symbol: str,
        fast_period: int = 5,
        slow_period: int = 20,
        trade_size: int = 100
    ):
        super().__init__(symbol)

        if fast_period >= slow_period:
            raise ValueError(
                "fast_period must be smaller than slow_period"
            )

        self.fast_period = fast_period
        self.slow_period = slow_period
        self.trade_size = trade_size

        self.close_buffer = deque(
            maxlen=slow_period
        )

        self.prev_fast_ma = None
        self.prev_slow_ma = None

    def calculate_ma(self, closes: list, period: int):
        """
        计算最近 period 根收盘价的简单移动平均
        """
        return sum(closes[-period:]) / period

    def on_bar(self, bar: Bar):
        self.close_buffer.append(bar.close)

        # 数据不足以计算长周期均线，继续累积
        if len(self.close_buffer) < self.slow_period:
            return None

        closes = list(self.close_buffer)

        fast_ma = self.calculate_ma(
            closes,
            self.fast_period
        )
        slow_ma = self.calculate_ma(
            closes,
            self.slow_period
        )

        signal = None

        # 需要上一根均线才能判断交叉
        if (
            self.prev_fast_ma is not None
            and self.prev_slow_ma is not None
        ):
            # 金叉：快线由下方上穿慢线
            if (
                self.prev_fast_ma <= self.prev_slow_ma
                and fast_ma > slow_ma
                and self.position == 0
            ):
                signal = Signal(
                    symbol=self.symbol,
                    signal_type=SignalType.BUY,
                    price=bar.close,
                    volume=self.trade_size
                )
                self.position += self.trade_size

            # 死叉：快线由上方下穿慢线
            elif (
                self.prev_fast_ma >= self.prev_slow_ma
                and fast_ma < slow_ma
                and self.position > 0
            ):
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
