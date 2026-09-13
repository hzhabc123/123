# strategy/signal.py

from dataclasses import dataclass
from enum import Enum


class SignalType(Enum):

    BUY = "BUY"

    SELL = "SELL"


@dataclass
class Signal:

    symbol: str

    signal_type: SignalType

    price: float

    volume: int