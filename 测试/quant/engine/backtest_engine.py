# engine/backtest_engine.py

from strategy.base_strategy import BaseStrategy
from broker.backtest_broker import BacktestBroker
from portfolio.portfolio import Portfolio
from risk.risk_manager import RiskManager


class BacktestEngine:

    def __init__(
        self,
        data_source,
        strategy: BaseStrategy,
        portfolio: Portfolio,
        broker: BacktestBroker,
        risk_manager: RiskManager
    ):

        self.data_source = data_source

        self.strategy = strategy

        self.portfolio = portfolio

        self.broker = broker

        self.risk_manager = risk_manager

    def sync_strategy_position(self, symbol):
        """
        以组合实际持仓为准，回写策略内部 position，
        保证信号被风控拒绝时策略状态也能正确回滚
        """
        position = self.portfolio.positions.get(symbol)
        self.strategy.position = (
            position.volume if position else 0
        )

    def process_signal(self, signal):

        if not signal:
            return

        if not self.risk_manager.validate(signal):
            self.sync_strategy_position(signal.symbol)
            return

        trade = self.broker.execute_signal(signal)

        if trade:

            self.portfolio.on_trade(trade)

            self.sync_strategy_position(signal.symbol)

    def run(
        self,
        symbol,
        start,
        end
    ):

        bars = self.data_source.get_bars(
            symbol=symbol,
            start=start,
            end=end
        )

        print(f"加载数据: {len(bars)} 条")

        for bar in bars:

            signal = self.strategy.on_bar(bar)

            self.process_signal(signal)

            self.portfolio.update_market_value(
                symbol=bar.symbol,
                last_price=bar.close
            )

        return self.portfolio
