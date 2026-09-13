from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from broker.backtest_broker import BacktestBroker

from strategy.signal import (
    Signal,
    SignalType
)


broker = BacktestBroker()

signal = Signal(
    symbol="301313",
    signal_type=SignalType.BUY,
    price=20,
    volume=100
)

trade = broker.execute_signal(signal)

print(trade)