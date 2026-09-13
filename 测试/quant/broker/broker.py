# broker/broker.py

from abc import ABC, abstractmethod

from strategy.signal import Signal
from portfolio.trade import Trade


class Broker(ABC):

    @abstractmethod
    def execute_signal(
        self,
        signal: Signal
    ) -> Trade | None:
        """
        Signal -> Trade
        """
        pass