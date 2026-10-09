"""
Quant V2 akshare 数据源适配器

akshare 免费开源，无需 apikey。
- 主接口 stock_zh_a_daily（新浪），稳定返回 date/open/high/low/close/volume/amount
- 回退 stock_zh_a_hist（东财），部分网络下被反爬会断连

新浪代码前缀：sh/sz/bj，如 sh600519、sz000001。
"""

from datetime import datetime
from typing import List, Optional

from data.bar import Bar
from data.data_source import AbstractDataSource, DataSourceError


def _normalize_symbol(symbol: str) -> str:
    """把 600519 -> sh600519，000001 -> sz000001，带前缀则原样返回"""
    s = symbol.strip()
    if s[:2].lower() in ("sh", "sz", "bj"):
        return s
    if len(s) == 6:
        if s[0] in ("6", "9"):
            return "sh" + s
        if s[0] in ("0", "2", "3"):
            return "sz" + s
        if s[0] in ("4", "8"):
            return "bj" + s
        return "sh" + s
    return s


class AkshareDataSource(AbstractDataSource):
    """akshare 数据源（免费，token 可选留空）"""

    name = "akshare"

    def __init__(self, token: Optional[str] = None, **kwargs):
        super().__init__(token=token, **kwargs)

    def _import(self):
        # Python 3.13 兼容补丁（akshare 依赖 py_mini_racer 使用已移除的 ImpImporter）
        from utils.compat import patch_imp_importer
        patch_imp_importer()
        try:
            import akshare as ak
        except ImportError as e:
            raise DataSourceError("未安装 akshare，请运行: pip install -r requirements.txt") from e
        return ak

    def fetch_daily(self, symbol, start, end, adjust: str = "qfq") -> List:
        """
        获取 A 股日线

        symbol: "600519" / "sh600519"
        adjust: 'qfq' 前复权 / 'hfq' 后复权 / '' 不复权
        """
        ak = self._import()
        code = _normalize_symbol(symbol)
        start_s = start.strftime("%Y%m%d")
        end_s = end.strftime("%Y%m%d")

        # 主路径：新浪
        df = self._fetch_sina(ak, code, start_s, end_s, adjust)
        if df is not None and not df.empty:
            return self._df_to_bars(df, symbol, adjust)

        # 回退：东财
        df = self._fetch_em(ak, symbol, start_s, end_s, adjust)
        if df is not None and not df.empty:
            return self._df_to_bars_em(df, symbol)

        # ETF（5 开头）或普通个股兜底：新浪 ETF 历史接口
        if str(code).lower().startswith("sh5") or str(code).lower().startswith("sz1"):
            df = self._fetch_sina_etf(ak, code)
            if df is not None and not df.empty:
                df = df[(df["date"] >= start) & (df["date"] <= end)]
                return self._df_to_bars(df, symbol, adjust)

        raise DataSourceError(f"akshare 未取到 {symbol} 日线数据")

    def _fetch_sina_etf(self, ak, code) -> Optional:
        """新浪 ETF 历史接口（东财被屏蔽时的回退）"""
        try:
            return ak.fund_etf_hist_sina(symbol=code)
        except Exception:
            return None

    def _fetch_sina(self, ak, code, start_s, end_s, adjust) -> Optional:
        """新浪日线接口"""
        try:
            return ak.stock_zh_a_daily(symbol=code, start_date=start_s, end_date=end_s, adjust=adjust)
        except Exception:
            return None

    def _fetch_em(self, ak, symbol, start_s, end_s, adjust) -> Optional:
        """东财日线接口（回退）"""
        sport = "qfq" if adjust == "qfq" else ("hfq" if adjust == "hfq" else "")
        try:
            return ak.stock_zh_a_hist(symbol=symbol, period="daily",
                                      start_date=start_s, end_date=end_s, adjust=sport)
        except Exception:
            return None

    def _df_to_bars(self, df, symbol, adjust) -> List:
        """新浪 df -> List[Bar]"""
        bars = []
        for _, row in df.iterrows():
            day = row.get("date")
            dt = day if isinstance(day, datetime) else datetime.combine(day, datetime.min.time())
            bars.append(self._to_bar(
                symbol=str(symbol),
                dt=dt,
                open_p=float(row.get("open", 0)),
                high=float(row.get("high", 0)),
                low=float(row.get("low", 0)),
                close=float(row.get("close", 0)),
                volume=float(row.get("volume", 0) or 0),
                amount=float(row.get("amount", 0) or 0),
            ))
        bars.sort(key=lambda b: b.datetime)
        return bars

    def _df_to_bars_em(self, df, symbol) -> List:
        """东财 df -> List[Bar]"""
        bars = []
        for _, row in df.iterrows():
            day = row.get("日期")
            dt = datetime.combine(day, datetime.min.time()) if isinstance(day, (datetime,)) else day
            bars.append(self._to_bar(
                symbol=str(symbol),
                dt=dt,
                open_p=float(row.get("开盘", 0)),
                high=float(row.get("最高", 0)),
                low=float(row.get("最低", 0)),
                close=float(row.get("收盘", 0)),
                volume=float(row.get("成交量", 0) or 0) * 100,  # 手 -> 股
                amount=float(row.get("成交额", 0) or 0),
            ))
        bars.sort(key=lambda b: b.datetime)
        return bars

    def price_to_fetch(self, symbol) -> Bar:
        """获取最新一日的单根 Bar"""
        import datetime as _dt
        end = _dt.date.today()
        start = end - _dt.timedelta(days=10)
        bars = self.fetch_daily(symbol, start, end, adjust="")
        if not bars:
            raise DataSourceError(f"{self.name}: 无最新行情 {symbol}")
        return bars[-1]
