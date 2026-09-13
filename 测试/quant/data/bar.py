# data/bar.py

from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True)
class Bar:
    """
    标准K线对象

    所有数据源最终都转换成Bar
    """

    symbol: str

    datetime: datetime

    open: float
    high: float
    low: float
    close: float

    volume: float = 0.0
    amount: float = 0.0

    def __repr__(self) -> str:
        return (
            f"Bar("
            f"{self.symbol}, "
            f"{self.datetime}, "
            f"O={self.open}, "
            f"H={self.high}, "
            f"L={self.low}, "
            f"C={self.close}, "
            f"V={self.volume}"
            f")"
        )