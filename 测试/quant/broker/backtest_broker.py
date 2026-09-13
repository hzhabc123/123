# broker/backtest_broker.py

from datetime import datetime
from itertools import count

from broker.broker import Broker

from strategy.signal import Signal
from strategy.signal import SignalType

from portfolio.trade import Trade
from portfolio.order import Direction


class BacktestBroker(Broker):

    _trade_counter = count(1)

    def __init__(
        self,
        commission_rate: float = 0.0003,
        slippage: float = 0.0001
    ):

        self.commission_rate = commission_rate
        self.slippage = slippage

    def execute_signal(
        self,
        signal: Signal
    ) -> Trade | None:

        if signal is None:
            return None

        trade_id = f"T{next(self._trade_counter):06d}"

        if signal.signal_type == SignalType.BUY:

            fill_price = (
                signal.price
                * (1 + self.slippage)
            )

            direction = Direction.BUY

        else:

            fill_price = (
                signal.price
                * (1 - self.slippage)
            )

            direction = Direction.SELL

        commission = (
            fill_price
            * signal.volume
            * self.commission_rate
        )

        trade = Trade(
            trade_id=trade_id,
            order_id=f"O{trade_id[1:]}",

            symbol=signal.symbol,

            direction=direction,

            price=fill_price,

            volume=signal.volume,

            trade_time=datetime.now(),

            commission=commission
        )

        return trade