# main.py

from pathlib import Path

from config.settings import Settings

from engine.backtest_engine import BacktestEngine

from strategy.ma_cross import MACrossStrategy

from utils.logger import get_logger


logger = get_logger(__name__)


def create_engine(settings: Settings):
    """
    根据运行模式创建引擎
    """

    mode = settings.RUN_MODE.lower()

    if mode == "backtest":
        return BacktestEngine(settings)

    raise ValueError(f"Unsupported run mode: {mode}")


def register_strategies(engine):
    """
    注册策略
    """

    strategy = MACrossStrategy(
        symbol="000001.SZ",
        fast_period=5,
        slow_period=20,
    )

    engine.add_strategy(strategy)


def main():
    """
    系统入口
    """

    logger.info("=" * 60)
    logger.info("Quant V2 Starting...")
    logger.info("=" * 60)

    try:
        # --------------------------------------------------
        # 1. 加载配置
        # --------------------------------------------------
        settings = Settings()

        logger.info(f"Run Mode: {settings.RUN_MODE}")

        # --------------------------------------------------
        # 2. 创建引擎
        # --------------------------------------------------
        engine = create_engine(settings)

        # --------------------------------------------------
        # 3. 注册策略
        # --------------------------------------------------
        register_strategies(engine)

        # --------------------------------------------------
        # 4. 初始化
        # --------------------------------------------------
        engine.initialize()

        # --------------------------------------------------
        # 5. 运行
        # --------------------------------------------------
        engine.run()

        # --------------------------------------------------
        # 6. 输出结果
        # --------------------------------------------------
        engine.summary()

        logger.info("Quant V2 Finished Successfully")

    except KeyboardInterrupt:
        logger.warning("System interrupted by user")

    except Exception as e:
        logger.exception(f"System crashed: {e}")

        raise


if __name__ == "__main__":
    main()