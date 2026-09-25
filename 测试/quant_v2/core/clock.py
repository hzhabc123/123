"""
Quant V2 时钟模块
提供统一的回测时钟和实盘时钟
"""

from datetime import datetime, timedelta
from typing import Optional


class Clock:
    def __init__(self, start_time: datetime):
        self._current_time = start_time
        self._start_time = start_time

    @property
    def now(self) -> datetime:
        return self._current_time

    @property
    def start_time(self) -> datetime:
        return self._start_time

    def advance(self, dt: timedelta):
        self._current_time += dt

    def set_time(self, dt: datetime):
        self._current_time = dt

    def elapsed(self) -> timedelta:
        return self._current_time - self._start_time


class LiveClock:

    @property
    def now(self) -> datetime:
        return datetime.now()
