"""
Quant V2 费用模型

支持：
- A股：佣金（双向，最低5元）、印花税（仅卖出）、过户费（双向）
- 美股：佣金、SEC费（仅卖出）、TA费
- 加密货币：手续费（maker/taker）
- 滑点成本
"""

from dataclasses import dataclass
from typing import Optional

from core.enums import Side, AssetClass


@dataclass
class FeeBreakdown:
    commission: float = 0.0
    stamp_tax: float = 0.0
    transfer_fee: float = 0.0
    sec_fee: float = 0.0
    ta_fee: float = 0.0
    slippage_cost: float = 0.0
    impact_cost: float = 0.0

    @property
    def total(self) -> float:
        return (
            self.commission + self.stamp_tax + self.transfer_fee
            + self.sec_fee + self.ta_fee
        )

    @property
    def all_in_cost(self) -> float:
        return self.total + self.slippage_cost + self.impact_cost

    def __repr__(self) -> str:
        return (
            f"FeeBreakdown(commission={self.commission:.4f}, "
            f"stamp_tax={self.stamp_tax:.4f}, transfer={self.transfer_fee:.4f}, "
            f"slippage={self.slippage_cost:.4f}, total={self.total:.4f})"
        )


class FeeModel:
    def calculate(self, side: Side, price: float, qty: float,
                  notional: Optional[float] = None) -> FeeBreakdown:
        raise NotImplementedError


class ChinaAFeeModel(FeeModel):
    """
    A股费用模型
    - 佣金：双向，最低5元
    - 印花税：仅卖出，0.05%（2023.8.28起）
    - 过户费：双向，0.001%
    """

    def __init__(self, commission_rate: float = 0.0003, min_commission: float = 5.0,
                 stamp_tax_rate: float = 0.0005, transfer_fee_rate: float = 0.00001,
                 slippage_rate: float = 0.0001):
        self.commission_rate = commission_rate
        self.min_commission = min_commission
        self.stamp_tax_rate = stamp_tax_rate
        self.transfer_fee_rate = transfer_fee_rate
        self.slippage_rate = slippage_rate

    def calculate(self, side: Side, price: float, qty: float,
                  notional: Optional[float] = None) -> FeeBreakdown:
        if notional is None:
            notional = price * qty
        commission = max(notional * self.commission_rate, self.min_commission)
        stamp_tax = notional * self.stamp_tax_rate if side == Side.SELL else 0.0
        transfer_fee = notional * self.transfer_fee_rate
        slippage_cost = notional * self.slippage_rate
        return FeeBreakdown(
            commission=round(commission, 4), stamp_tax=round(stamp_tax, 4),
            transfer_fee=round(transfer_fee, 4), slippage_cost=round(slippage_cost, 4),
        )


class USStockFeeModel(FeeModel):
    def __init__(self, commission_per_share: float = 0.0, min_commission: float = 0.0,
                 sec_fee_rate: float = 0.0000278, ta_fee_rate: float = 0.0001,
                 slippage_rate: float = 0.0002):
        self.commission_per_share = commission_per_share
        self.min_commission = min_commission
        self.sec_fee_rate = sec_fee_rate
        self.ta_fee_rate = ta_fee_rate
        self.slippage_rate = slippage_rate

    def calculate(self, side: Side, price: float, qty: float,
                  notional: Optional[float] = None) -> FeeBreakdown:
        if notional is None:
            notional = price * qty
        commission = max(qty * self.commission_per_share, self.min_commission)
        sec_fee = notional * self.sec_fee_rate if side == Side.SELL else 0.0
        ta_fee = notional * self.ta_fee_rate if side == Side.SELL else 0.0
        slippage_cost = notional * self.slippage_rate
        return FeeBreakdown(
            commission=round(commission, 4), sec_fee=round(sec_fee, 4),
            ta_fee=round(ta_fee, 4), slippage_cost=round(slippage_cost, 4),
        )


class CryptoFeeModel(FeeModel):
    def __init__(self, taker_rate: float = 0.0005, maker_rate: float = 0.0002,
                 slippage_rate: float = 0.0001):
        self.taker_rate = taker_rate
        self.maker_rate = maker_rate
        self.slippage_rate = slippage_rate

    def calculate(self, side: Side, price: float, qty: float,
                  notional: Optional[float] = None) -> FeeBreakdown:
        if notional is None:
            notional = price * qty
        commission = notional * self.taker_rate
        slippage_cost = notional * self.slippage_rate
        return FeeBreakdown(
            commission=round(commission, 6), slippage_cost=round(slippage_cost, 6),
        )


def create_fee_model(asset_class: str, **kwargs) -> FeeModel:
    if asset_class in ("china_stock", "stock", "cn", "a"):
        return ChinaAFeeModel(**kwargs)
    elif asset_class in ("us_stock", "us"):
        return USStockFeeModel(**kwargs)
    elif asset_class == "crypto":
        return CryptoFeeModel(**kwargs)
    else:
        raise ValueError(f"Unknown asset class: {asset_class}")
