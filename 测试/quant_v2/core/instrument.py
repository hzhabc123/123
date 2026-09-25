"""
Quant V2 合约/标的元数据
统一股票、ETF、期货、加密货币的基础信息
"""

from dataclasses import dataclass, field
from typing import List, Optional
from datetime import time

from core.enums import AssetClass


@dataclass
class Instrument:
    symbol: str
    asset_class: AssetClass
    exchange: str
    currency: str = "CNY"

    lot_size: float = 1.0
    tick_size: float = 0.01
    multiplier: float = 1.0

    price_precision: int = 2
    qty_precision: int = 0

    t_plus: int = 1
    shortable: bool = False

    trading_hours: List[tuple] = field(default_factory=list)
    calendar: str = "default"

    margin_rate: float = 1.0
    expiry_date: Optional[str] = None

    funding_interval: Optional[int] = None

    def __post_init__(self):
        if not self.trading_hours:
            if self.asset_class == AssetClass.STOCK:
                self.trading_hours = [
                    (time(9, 30), time(11, 30)),
                    (time(13, 0), time(15, 0)),
                ]
            elif self.asset_class == AssetClass.CRYPTO:
                self.trading_hours = [
                    (time(0, 0), time(23, 59)),
                ]

    def round_price(self, price: float) -> float:
        return round(round(price / self.tick_size) * self.tick_size, self.price_precision)

    def round_qty(self, qty: float) -> float:
        if self.qty_precision == 0:
            return int(qty)
        return round(qty, self.qty_precision)

    def calc_notional(self, price: float, qty: float) -> float:
        return price * qty * self.multiplier

    def calc_margin(self, price: float, qty: float) -> float:
        return self.calc_notional(price, qty) * self.margin_rate

    def __hash__(self):
        return hash(self.symbol)

    def __eq__(self, other):
        if not isinstance(other, Instrument):
            return False
        return self.symbol == other.symbol


INSTRUMENTS = {
    "301313": Instrument(
        symbol="301313", asset_class=AssetClass.STOCK, exchange="SZSE",
        currency="CNY", lot_size=100, tick_size=0.01, t_plus=1, shortable=False,
    ),
    "BTCUSDT": Instrument(
        symbol="BTCUSDT", asset_class=AssetClass.CRYPTO, exchange="BINANCE",
        currency="USDT", lot_size=1, tick_size=0.01, multiplier=1, t_plus=0,
        shortable=True, price_precision=2, qty_precision=3,
    ),
}


def get_instrument(symbol: str) -> Optional[Instrument]:
    return INSTRUMENTS.get(symbol)


def register_instrument(instrument: Instrument):
    INSTRUMENTS[instrument.symbol] = instrument
