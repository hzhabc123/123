"""
Quant V2 订单对象
"""

from dataclasses import dataclass, field
from datetime import datetime

from core.enums import OrderStatus, OrderType, Side, TimeInForce


@dataclass
class Order:
    order_id: str
    symbol: str
    side: Side
    order_type: OrderType
    price: float
    qty: float
    status: OrderStatus = OrderStatus.NEW
    filled_qty: float = 0.0
    filled_price: float = 0.0
    avg_price: float = 0.0
    create_time: datetime = field(default_factory=datetime.now)
    update_time: datetime = field(default_factory=datetime.now)
    strategy_id: str = ""
    time_in_force: TimeInForce = TimeInForce.GTC
    stop_price: float = 0.0
    reject_reason: str = ""

    def __repr__(self) -> str:
        return (f"Order({self.order_id}, {self.symbol}, {self.side.value}, "
                f"{self.order_type.value}, price={self.price}, qty={self.qty}, "
                f"status={self.status.value})")

    @property
    def is_buy(self) -> bool:
        return self.side == Side.BUY

    @property
    def is_sell(self) -> bool:
        return self.side == Side.SELL

    @property
    def is_active(self) -> bool:
        return self.status in (OrderStatus.NEW, OrderStatus.PART_FILLED)

    @property
    def is_completed(self) -> bool:
        return self.status in (OrderStatus.FILLED, OrderStatus.CANCELLED, OrderStatus.REJECTED, OrderStatus.EXPIRED)

    @property
    def remaining_qty(self) -> float:
        return self.qty - self.filled_qty

    @property
    def fill_ratio(self) -> float:
        return self.filled_qty / self.qty if self.qty > 0 else 0.0

    def fill(self, fill_price: float, fill_qty: float):
        if fill_qty <= 0:
            return
        total_value = self.avg_price * self.filled_qty + fill_price * fill_qty
        self.filled_qty += fill_qty
        self.avg_price = total_value / self.filled_qty if self.filled_qty > 0 else 0.0
        self.filled_price = fill_price
        self.update_time = datetime.now()
        if self.filled_qty >= self.qty:
            self.status = OrderStatus.FILLED
        else:
            self.status = OrderStatus.PART_FILLED

    def cancel(self):
        if self.is_active:
            self.status = OrderStatus.CANCELLED
            self.update_time = datetime.now()

    def reject(self, reason: str = ""):
        self.status = OrderStatus.REJECTED
        self.reject_reason = reason
        self.update_time = datetime.now()

    def expire(self):
        if self.is_active:
            self.status = OrderStatus.EXPIRED
            self.update_time = datetime.now()
