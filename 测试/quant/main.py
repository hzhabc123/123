# main.py
from datetime import datetime
from pathlib import Path

from config.settings import SETTINGS
from data.tdx_txt_data_source import TDXTxtDataSource
from strategy.dual_ma import DualMAStrategy
from broker.backtest_broker import BacktestBroker
from portfolio.portfolio import Portfolio
from risk.risk_manager import RiskManager
from risk.rules import RiskConfig
from engine.backtest_engine import BacktestEngine
from utils.logger import get_logger

logger = get_logger(__name__)

# --------------------------------------------------
# 回测参数（可按需调整）
# --------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

SYMBOL = "301313"
START = datetime(2024, 9, 6)
END = datetime(2026, 6, 12)
FAST_PERIOD = 5
SLOW_PERIOD = 20
TRADE_SIZE = 200


def build_engine() -> BacktestEngine:
    """
    按真实构造签名组装数据源、策略、组合、券商、风控与引擎
    """
    data_source = TDXTxtDataSource(DATA_DIR)

    strategy = DualMAStrategy(
        symbol=SYMBOL,
        fast_period=FAST_PERIOD,
        slow_period=SLOW_PERIOD,
        trade_size=TRADE_SIZE
    )

    portfolio = Portfolio(
        initial_cash=SETTINGS["START_CASH"]
    )

    broker = BacktestBroker(
        commission_rate=SETTINGS["COMMISSION"]
    )

    risk_manager = RiskManager(
        portfolio=portfolio,
        config=RiskConfig()
    )

    return BacktestEngine(
        data_source=data_source,
        strategy=strategy,
        portfolio=portfolio,
        broker=broker,
        risk_manager=risk_manager
    )


def main():
    logger.info("=" * 60)
    logger.info("Quant V2 Backtest Starting...")
    logger.info("=" * 60)

    try:
        engine = build_engine()
        portfolio = engine.run(
            symbol=SYMBOL,
            start=START,
            end=END
        )
        portfolio.summary()

        logger.info("Quant V2 Finished Successfully")

    except KeyboardInterrupt:
        logger.warning("System interrupted by user")

    except Exception as e:
        logger.exception(f"System crashed: {e}")
        raise


if __name__ == "__main__":
    main()
