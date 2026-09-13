# risk/risk_manager.py

from strategy.signal import Signal
from strategy.signal import SignalType

from portfolio.portfolio import Portfolio

from risk.rules import RiskConfig

class RiskManager:

    def __init__(
        self,
        portfolio: Portfolio,
        config: RiskConfig
    ):

        self.portfolio = portfolio

        self.config = config

    def check_cash(
        self,
        signal: Signal
    ) -> bool:

        if signal.signal_type != SignalType.BUY:
            return True

        required_cash = (
            signal.price
            * signal.volume
        )

        return (
            self.portfolio.account.cash
            >= required_cash
        )
    def check_position(
        self,
        signal: Signal
    ) -> bool:

            if signal.signal_type != SignalType.SELL:
                return True

            position = (
                self.portfolio.positions
                .get(signal.symbol)
            )

            if position is None:
                return False

            return (
                position.volume
                >= signal.volume
            )
    def check_single_position_ratio(
        self,
        signal: Signal
    ) -> bool:

        if signal.signal_type != SignalType.BUY:
            return True

        account = self.portfolio.account

        total_asset = max(
            account.total_asset,
            account.cash
        )

        target_value = (
            signal.price
            * signal.volume
        )

        ratio = (
            target_value
            / total_asset
        )

        return (
            ratio
            <= self.config.max_position_ratio
        )
    def check_total_position_ratio(
        self,
        signal: Signal
    ) -> bool:

        if signal.signal_type != SignalType.BUY:
            return True

        current_value = sum(
            pos.market_value
            for pos
            in self.portfolio.positions.values()
        )

        target_value = (
            signal.price
            * signal.volume
        )

        total_asset = max(
            self.portfolio.account.total_asset,
            self.portfolio.account.cash
        )

        ratio = (
            current_value
            + target_value
        ) / total_asset

        return (
            ratio
            <= self.config.max_total_position_ratio
        )
    def validate(
        self,
        signal: Signal
    ) -> bool:

        if signal is None:
            return False

        if not self.check_cash(signal):

            print(
                f"[RISK] 资金不足 "
                f"{signal.symbol}"
            )

            return False

        if not self.check_position(signal):

            print(
                f"[RISK] 持仓不足 "
                f"{signal.symbol}"
            )

            return False

        if not self.check_single_position_ratio(signal):

            print(
                f"[RISK] 超过单票仓位限制 "
                f"{signal.symbol}"
            )

            return False

        if not self.check_total_position_ratio(signal):

            print(
                f"[RISK] 超过总仓位限制 "
                f"{signal.symbol}"
            )

            return False

        return True
