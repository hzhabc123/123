# portfolio/order.py
# 订单对象
from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class Direction(Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderStatus(Enum):
    NEW = "NEW"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"


@dataclass
class Order:

    order_id: str

    symbol: str

    direction: Direction

    price: float

    volume: int

    create_time: datetime

    status: OrderStatus = OrderStatus.NEW