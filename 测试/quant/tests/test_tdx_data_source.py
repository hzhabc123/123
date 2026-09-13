# tests/test_tdx_data_source.py

from datetime import datetime
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))
from data.tdx_txt_data_source import TDXTxtDataSource


def main():

    source = TDXTxtDataSource(
        data_dir=ROOT_DIR / "data"
    )

    bars = source.get_bars(
        symbol="301313",
        start=datetime(2024, 9, 6),
        end=datetime(2026, 6, 12)
    )

    print(f"读取到 {len(bars)} 条K线")

    print()

    print("前5条数据")

    for bar in bars[:5]:
        print(bar)

    print()

    print("最后5条数据")

    for bar in bars[-5:]:
        print(bar)


if __name__ == "__main__":
    main()