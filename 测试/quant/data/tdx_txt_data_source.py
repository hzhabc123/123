# data/tdx_txt_data_source.py

from pathlib import Path
from datetime import datetime

import pandas as pd

from data.bar import Bar
from data.data_source import DataSource


class TDXTxtDataSource(DataSource):

    def __init__(self, data_dir: str):

        self.data_dir = Path(data_dir)

    def get_bars(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        frequency: str = "1d"
    ) -> list[Bar]:

        file_path = self.data_dir / f"{symbol}.txt"

        if not file_path.exists():
            raise FileNotFoundError(file_path)

        # 第一行为股票信息
        # 第二行为表头
        df = pd.read_csv(
            file_path,
            sep="\t",
            skiprows=1,
            encoding="gbk"
        )[:-1]
        # print(df)

        df.columns = [
            col.strip()
            for col in df.columns
        ]

        df["日期"] = pd.to_datetime(df["日期"])

        df = df[
            (df["日期"] >= start)
            & (df["日期"] <= end)
        ]

        bars = []

        for row in df.itertuples(index=False):

            bars.append(
                Bar(
                    symbol=symbol,
                    datetime=row.日期,

                    open=row.开盘,
                    high=row.最高,
                    low=row.最低,
                    close=row.收盘,

                    volume=row.成交量,
                    amount=row.成交额
                )
            )

        return bars
