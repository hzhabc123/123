"""
Quant V2 成交对象
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from core.enums import Side


@dataclass
class Trade:
    trade_id: str
    order_id: str
    symbol: str
    side: Side
    price: float
    qty: float
    commission: float = 0.0
    slippage: float = 0.0
    trade_time: datetime = field(default_factory=datetime.now)
    strategy_id: str = ""
    fee_breakdown: Optional[object] = None

    def __repr__(self) -> str:
        return (f"Trade({self.trade_id}, {self.symbol}, {self.side.value}, "
                f"price={self.price}, qty={self.qty}, commission={self.commission})")

    @property
    def is_buy(self) -> bool:
        return self.side == Side.BUY

    @property
    def is_sell(self) -> bool:
        return self.side == Side.SELL

    @property
    def notional(self) -> float:
        return self.price * self.qty

    @property
    def total_cost(self) -> float:
        return self.commission + self.slippage

    @property
    def net_amount(self) -> float:
        if self.is_buy:
            return -(self.notional + self.total_cost)
        else:
            return self.notional - self.total_cost
