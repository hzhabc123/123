"""
Quant V2 掘金量化（MyQuant）数据源适配器

config 方式配置 token：data source 传入 token 或环境变量 GM_TOKEN。
掘金接口：gm.api.history -> 日线/分钟/tick；需先 set_token。
"""

from datetime import datetime
from typing import List, Optional

from data.bar import Bar
from data.data_source import AbstractDataSource, DataSourceError, DataSourceAuthError


def _gm_symbol(symbol: str) -> str:
    s = symbol.strip().upper()
    if "." in s:
        return s
    if len(s) == 6:
        if s[0] in ("6", "9"):
            return f"SHSE.{s}"
        if s[0] in ("0", "2", "3"):
            return f"SZSE.{s}"
        if s[0] in ("4", "8"):
            return f"BJSE.{s}"
        return f"SHSE.{s}"
    return s


class GmtokenDataSource(AbstractDataSource):
    """掘金量化数据源（需 apikey/GM token）"""

    name = "gm"

    def __init__(self, token: Optional[str] = None, **kwargs):
        super().__init__(token=token, **kwargs)

    def _import(self):
        try:
            from gm.api import set_token, history, context  # noqa
            return set_token, history
        except ImportError as e:
            raise DataSourceAuthError("未安装掘金 SDK，请运行: pip install gm，并配置 token") from e

    def _require_auth(self) -> None:
        if not self.token:
            raise DataSourceAuthError("掘金数据源需要 apikey（token），请提供 account id / token")

    def fetch_daily(self, symbol, start, end, adjust: str = "qfq") -> List:
        self._require_auth()
        set_token, history = self._import()
        set_token(self.token)
        code = _gm_symbol(symbol)
        freq = "1d"
        fields = "symbol, eob, open, high, low, close, volume, amount"
        start_s = start.strftime("%Y-%m-%d %H:%M:%S")
        end_s = end.strftime("%Y-%m-%d %H:%M:%S")
        adj = {"qfq": "pre", "hfq": "post", "": "none"}.get(adjust, "pre")
        data = history(symbol=code, frequency=freq, start_time=start_s,
                       end_time=end_s, fields=fields, adjust=adj)
        bars = []
        for row in data:
            eob = getattr(row, "eob", None)
            dt = eob if isinstance(eob, datetime) else datetime.strptime(eob, "%Y-%m-%d %H:%M:%S")
            bars.append(self._to_bar(
                symbol=str(symbol), dt=dt,
                open_p=getattr(row, "open", 0), high=getattr(row, "high", 0),
                low=getattr(row, "low", 0), close=getattr(row, "close", 0),
                volume=getattr(row, "volume", 0) or 0,
                amount=getattr(row, "amount", 0) or 0,
            ))
        bars.sort(key=lambda b: b.datetime)
        return bars

    def price_to_fetch(self, symbol) -> Bar:
        import datetime as _dt
        end = _dt.date.today()
        start = end - _dt.timedelta(days=5)
        bars = self.fetch_daily(symbol, start, end, adjust="")
        if not bars:
            raise DataSourceError(f"{self.name}: 无最新行情 {symbol}")
        return bars[-1]
