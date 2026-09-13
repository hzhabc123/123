# portfolio/position.py
# 持仓对象
from dataclasses import dataclass


@dataclass
class Position:

    symbol: str

    volume: int = 0

    avg_price: float = 0.0

    market_value: float = 0.0

    unrealized_pnl: float = 0.0

    realized_pnl: float = 0.0