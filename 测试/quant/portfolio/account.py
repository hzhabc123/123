# portfolio/account.py
# 账户对象
from dataclasses import dataclass


@dataclass
class Account:

    initial_cash: float

    cash: float

    frozen_cash: float = 0.0

    total_asset: float = 0.0