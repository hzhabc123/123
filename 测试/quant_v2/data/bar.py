"""
Quant V2 K线数据对象
标准的OHLCV数据结构
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class BarFlags:
    is_suspended: bool = False
    is_st: bool = False
    is_delisted: bool = False
    limit_up: bool = False
    limit_down: bool = False
    is_ex_dividend: bool = False


@dataclass
class Bar:
    symbol: str
    datetime: datetime

    open: float
    high: float
    low: float
    close: float

    volume: float = 0.0
    amount: float = 0.0

    flags: BarFlags = field(default_factory=BarFlags)
    adj_factor: float = 1.0
    open_interest: float = 0.0

    def __repr__(self) -> str:
        return (
            f"Bar({self.symbol}, {self.datetime}, "
            f"O={self.open}, H={self.high}, L={self.low}, C={self.close}, "
            f"V={self.volume})"
        )

    @property
    def mid(self) -> float:
        return (self.high + self.low) / 2

    @property
    def typical_price(self) -> float:
        return (self.high + self.low + self.close) / 3

    @property
    def range(self) -> float:
        return self.high - self.low

    @property
    def body(self) -> float:
        return abs(self.close - self.open)

    @property
    def is_bullish(self) -> bool:
        return self.close > self.open

    @property
    def is_bearish(self) -> bool:
        return self.close < self.open


@dataclass
class Tick:
    symbol: str
    datetime: datetime

    last_price: float
    bid_price: float
    ask_price: float
    bid_volume: float
    ask_volume: float
    volume: float

    open_interest: float = 0.0
    settlement_price: float = 0.0

    def __repr__(self) -> str:
        return (
            f"Tick({self.symbol}, {self.datetime}, "
            f"last={self.last_price}, bid={self.bid_price}, ask={self.ask_price}, "
            f"vol={self.volume})"
        )

    @property
    def mid_price(self) -> float:
        return (self.bid_price + self.ask_price) / 2

    @property
    def spread(self) -> float:
        return self.ask_price - self.bid_price

    @property
    def spread_bps(self) -> float:
        mid = self.mid_price
        if mid > 0:
            return (self.spread / mid) * 10000
        return 0.0
