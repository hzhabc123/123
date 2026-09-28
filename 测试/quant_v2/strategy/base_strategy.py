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
    """策略状态"""
    strategy_id: str
    name: str
    current_bar: Optional[Bar] = None
    current_bar_index: int = 0
    history: List[Bar] = None
    
    def __post_init__(self):
        if self.history is None:
            self.history = []


class BaseStrategy:
    """
    策略基类
    
    所有策略必须继承此类并实现on_bar方法
    """
    
    def __init__(self, name: str = "BaseStrategy", **params):
        self.name = name
        self.params = params
        self.state: Optional[StrategyState] = None
        self._signals: List[Signal] = []
        # 组合引用（用于查询真实持仓），由引擎注入
        self.portfolio = None

    def set_portfolio(self, portfolio):
        """绑定组合引用（引擎初始化时调用）"""
        self.portfolio = portfolio
    
    def indicator_values(self) -> dict:
        """
        返回策略当前 bar 实际使用/计算的指标值（供可视化 Recorder 上报）。
        
        口径约定：图上展示的指标必须 == 策略真实计算所用，不得事后重算。
        子类覆写此方法，返回 {指标名: 数值}。
        """
        return {}
    
    def initialize(self):
        pass
    
    def get_signals(self) -> list:
        return self._signals
    
    def add_signal(self, signal: Signal):
        self._signals.append(signal)
        self._signals = list(self.state.history) if self.state and self.state.history else self._signals
        return signal
    
    def buy(self, symbol: str, price: float, qty: float, reason: str = "") -> Optional[Signal]:
        """买入信号"""
        from signals.trading_signal import SignalDirection
        signal = Signal(
            symbol=symbol,
            direction=SignalDirection.BUY,
            price=price,
            qty=qty,
            reason=reason,
            timestamp=self._now()
        )
        return self.add_signal(signal)
    
    def sell(self, symbol: str, price: float, qty: float, reason: str = "") -> Optional[Signal]:
        """卖出信号"""
        from signals.trading_signal import SignalDirection
        signal = Signal(
            symbol=symbol,
            direction=SignalDirection.SELL,
            price=price,
            qty=qty,
            reason=reason,
            timestamp=self._now()
        )
        return self.add_signal(signal)

    def get_history_bars(self, count: int) -> list:
        """获取历史K线"""
        if self.state and self.state.history:
            return self.state.history[-count:]
        return []
    
    def _now(self):
        from datetime import datetime
        return datetime.now()
    
    def summary(self) -> str:
        return f"Strategy: {self.name}"
