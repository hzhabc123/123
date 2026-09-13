# portfolio/trade.py
# 成交对象
from dataclasses import dataclass
from datetime import datetime

from portfolio.order import Direction


@dataclass
class Trade:

    trade_id: str

    order_id: str

    symbol: str

    direction: Direction

    price: float

    volume: int

    trade_time: datetime

    commission: float = 0.0