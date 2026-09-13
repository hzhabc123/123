from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from datetime import datetime
from risk.risk_manager import RiskManager
from risk.rules import RiskConfig

from data.tdx_txt_data_source import (
    TDXTxtDataSource
)

from strategy.ma_cross import (
    MACrossStrategy
)

from broker.backtest_broker import (
    BacktestBroker
)

from portfolio.portfolio import (
    Portfolio
)

from engine.backtest_engine import (
    BacktestEngine
)


source = TDXTxtDataSource(
    ROOT_DIR / "data"
)

strategy = MACrossStrategy(
    symbol="301313",
    fast_period=5,
    slow_period=20
)

portfolio = Portfolio(
    initial_cash=100000
)

broker = BacktestBroker()
risk_manager = RiskManager(
    portfolio,
    RiskConfig(
        max_position_ratio=0.2,
        max_total_position_ratio=0.8
    )
)

engine = BacktestEngine(
    data_source=source,
    strategy=strategy,
    portfolio=portfolio,
    broker=broker,
    risk_manager=risk_manager
)

result = engine.run(
    symbol="301313",
    start=datetime(2024, 9, 6),
    end=datetime(2026, 6, 12)
)

result.summary()