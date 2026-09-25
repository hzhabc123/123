"""
Quant V2 核心枚举定义
统一全系统的枚举类型
"""

from enum import Enum, auto


class OrderStatus(Enum):
    NEW = "NEW"
    PART_FILLED = "PART_FILLED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class OrderType(Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"
    STOP_LIMIT = "STOP_LIMIT"


class Side(Enum):
    BUY = "BUY"
    SELL = "SELL"


class PositionSide(Enum):
    LONG = "LONG"
    SHORT = "SHORT"


class EventType(Enum):
    BAR = auto()
    TICK = auto()
    ORDER = auto()
    TRADE = auto()
    ACCOUNT = auto()
    POSITION = auto()
    TIMER = auto()
    RISK = auto()
    LOG = auto()
    SIGNAL = auto()


class AssetClass(Enum):
    STOCK = "stock"
    ETF = "etf"
    FUTURES = "futures"
    CRYPTO = "crypto"
    OPTION = "option"


class SignalDirection(Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"
    SHORT = "SHORT"
    COVER = "COVER"


class TimeInForce(Enum):
    GTC = "GTC"
    IOC = "IOC"
    FOK = "FOK"
    DAY = "DAY"
