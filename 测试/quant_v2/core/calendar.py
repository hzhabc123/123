"""
Quant V2 交易日历
支持多市场交易日历
"""

from datetime import date, timedelta
from typing import List, Optional, Set
from dataclasses import dataclass, field


@dataclass
class TradingCalendar:
    market: str = "default"
    holidays: Set[date] = field(default_factory=set)

    def is_trading_day(self, dt: date) -> bool:
        if dt.weekday() >= 5:
            return False
        if dt in self.holidays:
            return False
        return True

    def next_trading_day(self, dt: date) -> date:
        candidate = dt + timedelta(days=1)
        while not self.is_trading_day(candidate):
            candidate += timedelta(days=1)
        return candidate

    def prev_trading_day(self, dt: date) -> date:
        candidate = dt - timedelta(days=1)
        while not self.is_trading_day(candidate):
            candidate -= timedelta(days=1)
        return candidate

    def add_trading_days(self, dt: date, n: int) -> date:
        if n == 0:
            return dt if self.is_trading_day(dt) else self.next_trading_day(dt)
        if n > 0:
            current = dt if self.is_trading_day(dt) else self.next_trading_day(dt)
            for _ in range(n):
                current = self.next_trading_day(current)
            return current
        else:
            current = dt if self.is_trading_day(dt) else self.prev_trading_day(dt)
            for _ in range(-n):
                current = self.prev_trading_day(current)
            return current

    def trading_days_between(self, start: date, end: date) -> List[date]:
        days = []
        current = start
        while current <= end:
            if self.is_trading_day(current):
                days.append(current)
            current += timedelta(days=1)
        return days

    def count_trading_days(self, start: date, end: date) -> int:
        return len(self.trading_days_between(start, end))


default_calendar = TradingCalendar()


def get_calendar(market: str = "default") -> TradingCalendar:
    return default_calendar
