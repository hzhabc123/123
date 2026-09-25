"""
Quant V2 数据源抽象基类

所有行情数据源（akshare / 掘金 / tushare 等）统一实现此接口，
由引擎/回测在 DataManager 中按需调用。
"""

from abc import ABC, abstractmethod
from datetime import datetime, date
from typing import List, Optional

from data.bar import Bar


class DataSourceError(Exception):
    pass


class DataSourceAuthError(DataSourceError):
    pass


class AbstractDataSource(ABC):

    name: str = "abstract"

    def __init__(self, token: Optional[str] = None, **kwargs):
        self.token = token
        self.kwargs = kwargs

    def _check_auth(self, required: bool = True, message: str = "") -> None:
        if required and not self.token:
            raise DataSourceAuthError(
                message or f"{self.name} 需要 apikey，请在 data source 配置中提供 token"
            )

    @staticmethod
    def _to_bar(
        symbol: str, dt: datetime, open_p: float, high: float, low: float,
        close: float, volume: float = 0.0, amount: float = 0.0,
    ) -> Bar:
        return Bar(
            symbol=symbol, datetime=dt,
            open=float(open_p), high=float(high), low=float(low),
            close=float(close), volume=float(volume), amount=float(amount),
        )

    @abstractmethod
    def fetch_daily(self, symbol: str, start: date, end: date,
                    adjust: str = "qfq") -> List[Bar]:
        raise NotImplementedError

    @abstractmethod
    def price_to_fetch(self, symbol: str) -> Bar:
        raise NotImplementedError

    def fetch_daily_sorted(self, *args, **kwargs) -> List[Bar]:
        bars = self.fetch_daily(*args, **kwargs)
        bars.sort(key=lambda b: b.datetime)
        return bars
