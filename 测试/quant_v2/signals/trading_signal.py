"""
Quant V2 信号模块
策略产生的交易信号
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from core.enums import SignalDirection


@dataclass
class Signal:
    symbol: str
    direction: SignalDirection
    price: float
    timestamp: datetime
    strategy_id: str
    strength: float = 1.0
    reason: str = ""
    target_qty: float = 0.0
    order_type: Optional[str] = None

    def __repr__(self) -> str:
        return (f"Signal({self.symbol}, {self.direction.value}, price={self.price}, "
                f"strength={self.strength:.2f}, strategy={self.strategy_id})")

    @property
    def is_buy(self) -> bool:
        return self.direction in (SignalDirection.BUY, SignalDirection.COVER)

    @property
    def is_sell(self) -> bool:
        return self.direction in (SignalDirection.SELL, SignalDirection.SHORT)

    @property
    def is_entry(self) -> bool:
        return self.direction in (SignalDirection.BUY, SignalDirection.SHORT)

    @property
    def is_exit(self) -> bool:
        return self.direction in (SignalDirection.SELL, SignalDirection.COVER)
