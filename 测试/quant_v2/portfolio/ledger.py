"""
Quant V2 账本模块
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class LedgerEntryType(Enum):
    INITIAL = "INITIAL"
    TRADE = "TRADE"
    FEE = "FEE"
    DIVIDEND = "DIVIDEND"
    BONUS_SHARE = "BONUS_SHARE"
    SPLIT = "SPLIT"


@dataclass
class LedgerEntry:
    entry_id: str
    entry_type: LedgerEntryType
    timestamp: datetime
    symbol: str = ""
    cash_delta: float = 0.0
    position_delta: float = 0.0
    price: float = 0.0
    fee: float = 0.0
    note: str = ""

    def __repr__(self) -> str:
        return f"Ledger({self.entry_id}, {self.entry_type.value}, {self.timestamp}, cash={self.cash_delta:.2f}, {self.note})"
