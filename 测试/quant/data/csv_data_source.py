# data/csv_data_source.py

from datetime import datetime

import pandas as pd

from data.bar import Bar
from data.data_source import DataSource


# CSV数据源示例
# from data.csv_data_source import CSVDataSource

# source = CSVDataSource("./data")

# bars = source.get_bars(
#     symbol="000001.SZ",
#     start=datetime(2024,1,1),
#     end=datetime(2024,12,31),
#     frequency="1d"
# )

class CSVDataSource(DataSource):

    def __init__(self, data_dir: str):
        self.data_dir = data_dir

    def get_bars(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        frequency: str,
    ) -> list[Bar]:

        file_path = f"{self.data_dir}/{symbol}.csv"

        df = pd.read_csv(file_path)

        df["datetime"] = pd.to_datetime(df["datetime"])

        df = df[
            (df["datetime"] >= start)
            & (df["datetime"] <= end)
        ]

        bars = []

        for _, row in df.iterrows():

            bars.append(
                Bar(
                    symbol=symbol,
                    datetime=row["datetime"],
                    open=row["open"],
                    high=row["high"],
                    low=row["low"],
                    close=row["close"],
                    volume=row.get("volume", 0),
                    amount=row.get("amount", 0),
                )
            )

        return bars