"""
Quant V2 止损管理模块
三种止损策略：固定比例、ATR动态、移动止损
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class StopOrder:
    symbol: str
    stop_type: str
    entry_price: float
    direction: str
    initial_stop: float = 0.0
    current_stop: float = 0.0
    params: dict = None

    def __post_init__(self):
        if self.params is None:
            self.params = {}
        if self.initial_stop == 0.0:
            self.initial_stop = self._calculate_initial_stop()
        if self.current_stop == 0.0:
            self.current_stop = self.initial_stop

    def _calculate_initial_stop(self) -> float:
        if self.stop_type == "fixed":
            stop_pct = self.params.get("stop_percent", 0.02)
            if self.direction == "long":
                return self.entry_price * (1 - stop_pct)
            else:
                return self.entry_price * (1 + stop_pct)
        elif self.stop_type == "atr":
            atr_multiplier = self.params.get("atr_multiplier", 2.0)
            atr = self.params.get("atr", self.entry_price * 0.02)
            if self.direction == "long":
                return self.entry_price - atr * atr_multiplier
            else:
                return self.entry_price + atr * atr_multiplier
        return self.entry_price

    def update(self, price: float) -> bool:
        if self.stop_type == "trailing":
            trailing_pct = self.params.get("trailing_percent", 0.03)
            if self.direction == "long":
                new_stop = price * (1 - trailing_pct)
                self.current_stop = max(self.current_stop, new_stop)
            else:
                new_stop = price * (1 + trailing_pct)
                self.current_stop = min(self.current_stop, new_stop) if self.current_stop > 0 else new_stop
        if self.direction == "long":
            return price <= self.current_stop
        else:
            return price >= self.current_stop


class StopManager:
    def __init__(self):
        self.stop_orders: dict = {}

    def add_stop_order(self, stop_order: StopOrder):
        self.stop_orders[stop_order.symbol] = stop_order

    def remove_stop_order(self, symbol: str):
        if symbol in self.stop_orders:
            del self.stop_orders[symbol]

    def update(self, symbol: str, price: float) -> Optional[str]:
        if symbol not in self.stop_orders:
            return None
        stop_order = self.stop_orders[symbol]
        triggered = stop_order.update(price)
        if triggered:
            return "SELL" if stop_order.direction == "long" else "COVER"
        return None

    def get_stop_price(self, symbol: str) -> Optional[float]:
        if symbol in self.stop_orders:
            return self.stop_orders[symbol].current_stop
        return None

    def summary(self) -> str:
        lines = ["=" * 60, "Stop Manager Summary", "=" * 60]
        for symbol, stop_order in self.stop_orders.items():
            lines.append(f"{symbol}: {stop_order.stop_type} stop")
            lines.append(f"  Entry: {stop_order.entry_price:.2f}")
            lines.append(f"  Current Stop: {stop_order.current_stop:.2f}")
            lines.append(f"  Direction: {stop_order.direction}")
        lines.append("=" * 60)
        return "\n".join(lines)


def create_fixed_stop(entry_price: float, direction: str, stop_percent: float = 0.02, **kwargs) -> StopOrder:
    return StopOrder(symbol=kwargs.get("symbol", ""), stop_type="fixed",
                     entry_price=entry_price, direction=direction,
                     params={"stop_percent": stop_percent})


def create_atr_stop(entry_price: float, direction: str, atr: float,
                    atr_multiplier: float = 2.0, **kwargs) -> StopOrder:
    return StopOrder(symbol=kwargs.get("symbol", ""), stop_type="atr",
                     entry_price=entry_price, direction=direction,
                     params={"atr": atr, "atr_multiplier": atr_multiplier})


def create_trailing_stop(entry_price: float, direction: str, trailing_percent: float = 0.03, **kwargs) -> StopOrder:
    return StopOrder(symbol=kwargs.get("symbol", ""), stop_type="trailing",
                     entry_price=entry_price, direction=direction,
                     params={"trailing_percent": trailing_percent})
