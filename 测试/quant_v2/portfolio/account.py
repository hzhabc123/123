"""
Quant V2 账户对象
"""

from dataclasses import dataclass, field


@dataclass
class Account:
    initial_cash: float = 100000.0
    cash: float = 100000.0
    frozen_cash: float = 0.0
    equity: float = 100000.0
    margin: float = 0.0
    currency: str = "CNY"
    leverage: float = 1.0
    ledger: list = field(default_factory=list)

    def __repr__(self) -> str:
        return f"Account(cash={self.cash:.2f}, equity={self.equity:.2f}, margin={self.margin:.2f})"

    @property
    def available_cash(self) -> float:
        return self.cash - self.frozen_cash

    @property
    def total_asset(self) -> float:
        return self.equity

    def deposit(self, amount: float):
        if amount <= 0:
            raise ValueError("入金金额必须大于0")
        self.cash += amount
        self.equity += amount

    def withdraw(self, amount: float):
        if amount <= 0:
            raise ValueError("出金金额必须大于0")
        if amount > self.available_cash:
            raise ValueError(f"可用资金不足: {self.available_cash:.2f} < {amount:.2f}")
        self.cash -= amount
        self.equity -= amount

    def freeze_cash(self, amount: float):
        if amount <= 0:
            return
        if amount > self.available_cash:
            raise ValueError(f"可用资金不足: {self.available_cash:.2f} < {amount:.2f}")
        self.frozen_cash += amount

    def unfreeze_cash(self, amount: float):
        if amount <= 0:
            return
        self.frozen_cash = max(0, self.frozen_cash - amount)

    def update_equity(self, market_value: float):
        self.equity = self.cash + market_value
