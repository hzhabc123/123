"""
Quant V2 持仓对象
"""

from dataclasses import dataclass
from core.enums import PositionSide


@dataclass
class Position:
    symbol: str
    side: PositionSide = PositionSide.LONG
    qty: float = 0.0
    available_qty: float = 0.0
    frozen_qty: float = 0.0
    avg_price: float = 0.0
    market_price: float = 0.0
    market_value: float = 0.0
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    margin: float = 0.0
    multiplier: float = 1.0
    currency: str = "CNY"

    def __repr__(self) -> str:
        return (f"Position({self.symbol}, {self.side.value}, "
                f"qty={self.qty}, avg_price={self.avg_price}, "
                f"market_value={self.market_value})")

    @property
    def is_long(self) -> bool:
        return self.side == PositionSide.LONG and self.qty > 0

    @property
    def is_short(self) -> bool:
        return self.side == PositionSide.SHORT and self.qty > 0

    @property
    def is_flat(self) -> bool:
        return self.qty == 0

    @property
    def direction_multiplier(self) -> float:
        return 1.0 if self.side == PositionSide.LONG else -1.0

    @property
    def total_cost(self) -> float:
        return self.avg_price * self.qty * self.multiplier

    def update_price(self, price: float):
        self.market_price = price
        self.market_value = price * self.qty * self.multiplier * self.direction_multiplier
        if self.qty > 0:
            self.unrealized_pnl = (price - self.avg_price) * self.qty * self.multiplier * self.direction_multiplier

    def update_position(self, qty_delta: float, price: float = None):
        old_qty = self.qty
        new_qty = old_qty + qty_delta

        if old_qty > 0 and new_qty < 0:
            self.realized_pnl += ((price - self.avg_price) * old_qty * self.multiplier * self.direction_multiplier) if price else 0.0
            self.side = PositionSide.SHORT if self.side == PositionSide.LONG else PositionSide.LONG
            self.qty = abs(new_qty)
            self.avg_price = price if price else self.avg_price
        elif old_qty < 0 and new_qty > 0:
            self.realized_pnl += ((self.avg_price - price) * abs(old_qty) * self.multiplier * self.direction_multiplier) if price else 0.0
            self.side = PositionSide.LONG if self.side == PositionSide.SHORT else PositionSide.SHORT
            self.qty = new_qty
            self.avg_price = price if price else self.avg_price
        else:
            if price and qty_delta > 0:
                total_cost = self.avg_price * old_qty + price * qty_delta
                self.qty = new_qty
                self.avg_price = total_cost / self.qty if self.qty > 0 else 0.0
            elif qty_delta < 0:
                if price:
                    self.realized_pnl += ((price - self.avg_price) * abs(qty_delta) * self.multiplier * self.direction_multiplier)
                self.qty = new_qty
                if self.qty == 0:
                    self.avg_price = 0.0

        self.available_qty = self.qty
        self.frozen_qty = 0.0
        if self.market_price > 0:
            self.update_price(self.market_price)

    def close(self, price: float = None):
        if self.qty > 0 and price:
            self.realized_pnl += ((price - self.avg_price) * self.qty * self.multiplier * self.direction_multiplier)
        self.qty = 0.0
        self.available_qty = 0.0
        self.frozen_qty = 0.0
        self.avg_price = 0.0
        self.unrealized_pnl = 0.0
