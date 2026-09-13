# data/data_source.py

from abc import ABC, abstractmethod
from datetime import datetime

from data.bar import Bar


class DataSource(ABC):

    @abstractmethod
    def get_bars(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        frequency: str,
    ) -> list[Bar]:
        pass