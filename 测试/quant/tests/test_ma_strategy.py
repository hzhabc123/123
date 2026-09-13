from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from datetime import datetime

from data.tdx_txt_data_source import TDXTxtDataSource
from strategy.ma_cross import MACrossStrategy


source = TDXTxtDataSource(
    ROOT_DIR / "data"
)

bars = source.get_bars(
        symbol="301313",
        start=datetime(2024, 9, 6),
        end=datetime(2026, 6, 12)
    )

strategy = MACrossStrategy(
    symbol="301313",
    fast_period=5,
    slow_period=20
)

# for bar in bars:
#     strategy.on_bar(bar)

for bar in bars:
    signal = strategy.on_bar(bar)
    # print(signal)
    if signal:
        print(signal)