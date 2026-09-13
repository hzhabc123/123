# portfolio/portfolio.py

from portfolio.account import Account
from portfolio.position import Position
from portfolio.trade import Trade
from portfolio.order import Direction


class Portfolio:

    def __init__(self, initial_cash: float):

        self.account = Account(
            initial_cash=initial_cash,
            cash=initial_cash,
            total_asset=initial_cash
        )

        self.positions: dict[str, Position] = {}

    def on_trade(self, trade: Trade):

        symbol = trade.symbol

        if symbol not in self.positions:

            self.positions[symbol] = Position(
                symbol=symbol
            )

        position = self.positions[symbol]

        amount = trade.price * trade.volume

        if trade.direction == Direction.BUY:

            self.account.cash -= (
                amount + trade.commission
            )

            total_cost = (
                position.avg_price * position.volume
                + amount
            )

            position.volume += trade.volume

            position.avg_price = (
                total_cost / position.volume
            )

        else:

            self.account.cash += (
                amount - trade.commission
            )

            position.volume -= trade.volume

            if position.volume == 0:

                position.avg_price = 0.0

    def update_market_value(
        self,
        symbol: str,
        last_price: float
    ):

        if symbol not in self.positions:
            return

        position = self.positions[symbol]

        position.market_value = (
            position.volume * last_price
        )

        position.unrealized_pnl = (
            (last_price - position.avg_price)
            * position.volume
        )

        self.account.total_asset = (
            self.account.cash
            + sum(
                pos.market_value
                for pos in self.positions.values()
            )
        )
    def summary(self):

        print()

        print("=" * 50)

        print("Portfolio Summary")

        print("=" * 50)

        print(
            f"Cash: "
            f"{self.account.cash:.2f}"
        )

        print(
            f"Total Asset: "
            f"{self.account.total_asset:.2f}"
        )

        print()

        for position in self.positions.values():

            print(position)