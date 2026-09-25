"""
Quant V2 仓位管理模块
三种仓位管理策略：固定数量、固定比例、ATR动态
"""

from dataclasses import dataclass
from typing import Optional
import math

from data.bar import Bar
from portfolio.portfolio import Portfolio


class PositionSizer:
    def calculate_qty(self, symbol: str, price: float, portfolio: Portfolio, **kwargs) -> float:
        raise NotImplementedError


class FixedSizer(PositionSizer):
    def __init__(self, qty: float = 100.0):
        self.qty = qty

    def calculate_qty(self, symbol: str, price: float, portfolio: Portfolio, **kwargs) -> float:
        return self.qty


class PercentSizer(PositionSizer):
    def __init__(self, percent: float = 0.1, min_amount: float = 1000.0):
        self.percent = percent
        self.min_amount = min_amount

    def calculate_qty(self, symbol: str, price: float, portfolio: Portfolio, **kwargs) -> float:
        equity = portfolio.account.equity
        target_amount = equity * self.percent
        if target_amount < self.min_amount:
            return 0.0
        qty = target_amount / price
        qty = math.floor(qty / 100) * 100
        return max(qty, 0.0)


class ATRSizer(PositionSizer):
    def __init__(self, risk_percent: float = 0.02, atr_multiplier: float = 2.0,
                 atr_period: int = 20, min_qty: float = 100.0):
        self.risk_percent = risk_percent
        self.atr_multiplier = atr_multiplier
        self.atr_period = atr_period
        self.min_qty = min_qty

    def calculate_qty(self, symbol: str, price: float, portfolio: Portfolio,
                     bar: Optional[Bar] = None, **kwargs) -> float:
        if bar is None:
            return self.min_qty
        atr = self._calculate_atr(bar)
        if atr <= 0:
            return self.min_qty
        equity = portfolio.account.equity
        risk_budget = equity * self.risk_percent
        risk_per_share = atr * self.atr_multiplier
        qty = risk_budget / risk_per_share
        qty = math.floor(qty / 100) * 100
        if qty < self.min_qty:
            return self.min_qty
        max_amount = portfolio.account.available_cash * 0.95
        max_qty = max_amount / price
        max_qty = math.floor(max_qty / 100) * 100
        qty = min(qty, max_qty)
        return qty

    def _calculate_atr(self, bar: Bar) -> float:
        if hasattr(bar, 'flags') and hasattr(bar.flags, 'is_suspended'):
            return bar.close * 0.02
        return bar.close * 0.02


def create_sizer(sizer_type: str, **kwargs) -> PositionSizer:
    if sizer_type == "fixed":
        return FixedSizer(**kwargs)
    elif sizer_type == "percent":
        return PercentSizer(**kwargs)
    elif sizer_type == "atr":
        return ATRSizer(**kwargs)
    else:
        raise ValueError(f"Unknown sizer type: {sizer_type}")
