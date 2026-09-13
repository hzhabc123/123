# data/gm_data_source.py

from datetime import datetime

from gm.api import history_n

from data.bar import Bar
from data.data_source import DataSource


# GM数据源示例
# from gm.api import set_token

# set_token("你的token")

# source = GMDataSource()

# bars = source.get_bars(
#     symbol="SZSE.000001",
#     start=datetime(2024,1,1),
#     end=datetime(2024,12,31),
#     frequency="1d"
# )


class GMDataSource(DataSource):

    def get_bars(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        frequency: str,
    ) -> list[Bar]:

        df = history_n(
            symbol=symbol,
            frequency=frequency,
            count=100000,
            end_time=end,
            fields="symbol,eob,open,high,low,close,volume,amount",
            adjust=1,
            df=True
        )

        bars = []

        for _, row in df.iterrows():

            bars.append(
                Bar(
                    symbol=row["symbol"],
                    datetime=row["eob"],
                    open=row["open"],
                    high=row["high"],
                    low=row["low"],
                    close=row["close"],
                    volume=row["volume"],
                    amount=row["amount"]
                )
            )

        return bars