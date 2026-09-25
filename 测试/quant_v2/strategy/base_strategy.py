"""
Quant V2 策略基类
"""

from typing import List, Optional, Any
from dataclasses import dataclass
from datetime import datetime

from data.bar import Bar
from signals.trading_signal import Signal


@dataclass
class StrategyState:
    strategy_id: str
    name: str
    current_bar: Optional[Bar] = None
    current_bar_index: int = 0
    history: List[Bar] = None

    def __post_init__(self):
        if self.history is None:
            self.history = []


class BaseStrategy:
    def __init__(self, name: str = "BaseStrategy", **params):
        self.name = name
        self.params = params
        self.state: Optional[StrategyState] = None
        self._signals: List[Signal] = []
        self.portfolio = None

    def set_portfolio(self, portfolio):
        self.portfolio = portfolio

    def initialize(self):
        pass

    def on_bar(self, bar: Bar):
        raise NotImplementedError("子类必须实现on_bar方法")

    def on_trade(self, trade: Any):
        pass

    def on_order(self, order: Any):
        pass

    def set_bar_context(self, bar: Bar, index: int, history: List[Bar]):
        if self.state is None:
            self.state = StrategyState(strategy_id=id(self), name=self.name)
        self.state.current_bar = bar
        self.state.current_bar_index = index
        self.state.history = history

    def get_current_price(self) -> float:
        if self.state and self.state.current_bar:
            return self.state.current_bar.close
        return 0.0

    def get_history_bars(self, n: int) -> List[Bar]:
        if self.state is None or not self.state.history:
            return []
        history = self.state.history
        if n <= 0:
            return []
        return history[-n:] if len(history) >= n else history

    def buy(self, symbol: str, price: float, qty: float = 100, reason: str = "") -> Signal:
        from core.enums import SignalDirection
        signal = Signal(symbol=symbol, direction=SignalDirection.BUY, price=price,
                        timestamp=self.state.current_bar.datetime if self.state else datetime.now(),
                        strategy_id=self.name, target_qty=qty, reason=reason)
        self._signals.append(signal)
        return signal

    def sell(self, symbol: str, price: float, qty: float = 100, reason: str = "") -> Signal:
        from core.enums import SignalDirection
        signal = Signal(symbol=symbol, direction=SignalDirection.SELL, price=price,
                        timestamp=self.state.current_bar.datetime if self.state else datetime.now(),
                        strategy_id=self.name, target_qty=qty, reason=reason)
        self._signals.append(signal)
        return signal

    def get_signals(self) -> List[Signal]:
        signals = self._signals.copy()
        self._signals.clear()
        return signals

    def summary(self) -> str:
        return f"Strategy: {self.name}\nParams: {self.params}"
