# strategy/base_strategy.py

from abc import ABC, abstractmethod

from data.bar import Bar
from strategy.signal import Signal

class BaseStrategy(ABC):

    def __init__(self, symbol: str):

        self.symbol = symbol

        self.position = 0

    # def buy(self, price: float, volume: int):

    #     print(
    #         f"[BUY] {self.symbol} "
    #         f"price={price:.2f} "
    #         f"volume={volume}"
    #     )

    #     self.position += volume

    # def sell(self, price: float, volume: int):

    #     print(
    #         f"[SELL] {self.symbol} "
    #         f"price={price:.2f} "
    #         f"volume={volume}"
    #     )

    #     self.position -= volume

    @abstractmethod
    def on_bar(self, bar) -> Signal | None:
        pass