from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from datetime import datetime

from data.tdx_txt_data_source import TDXTxtDataSource
from strategy.dual_ma import DualMAStrategy


def main():
    source = TDXTxtDataSource(ROOT_DIR / "data")

    bars = source.get_bars(
        symbol="301313",
        start=datetime(2024, 9, 6),
        end=datetime(2026, 6, 12)
    )

    strategy = DualMAStrategy(
        symbol="301313",
        fast_period=5,
        slow_period=20,
        trade_size=100
    )

    buy_count = 0
    sell_count = 0

    for bar in bars:
        signal = strategy.on_bar(bar)
        if signal:
            print(
                f"{bar.datetime} "
                f"{signal.signal_type.value:4s} "
                f"price={signal.price:.2f} "
                f"volume={signal.volume} "
                f"position={strategy.position}"
            )
            if signal.signal_type.value == "BUY":
                buy_count += 1
            else:
                sell_count += 1

    print("-" * 50)
    print(f"买入信号: {buy_count} 次")
    print(f"卖出信号: {sell_count} 次")
    print(f"回测结束持仓: {strategy.position}")


if __name__ == "__main__":
    main()
