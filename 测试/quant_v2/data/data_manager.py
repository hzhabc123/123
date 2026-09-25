"""
Quant V2 数据管理器

- 数据源注册与工厂
- 多标的 / 多区间日线
- 内存缓存（LRU）
"""

from typing import Dict, List, Optional

from data.bar import Bar
from data.data_source import AbstractDataSource


class DataManager:

    def __init__(self, sources: Optional[Dict[str, AbstractDataSource]] = None):
        self._sources: Dict[str, AbstractDataSource] = sources or {}
        self._cache: Dict[tuple, List[Bar]] = {}
        self._default = None
        if self._sources:
            self._default = list(self._sources.values())[0]

    def register(self, name: str, source: AbstractDataSource) -> "DataManager":
        self._sources[name] = source
        if self._default is None:
            self._default = source
        return self

    def set_default(self, source_or_name):
        if isinstance(source_or_name, str):
            if source_or_name not in self._sources:
                raise KeyError(f"数据源未注册: {source_or_name}")
            self._default = self._sources[source_or_name]
        else:
            self._default = source_or_name
        return self

    @property
    def default(self) -> Optional[AbstractDataSource]:
        return self._default

    def get_bars(self, symbol: str, start, end, adjust: str = "qfq",
                 source: Optional[str] = None, use_cache: bool = True) -> List[Bar]:
        src = self._resolve_source(source)
        key = (src.name, symbol, str(start), str(end), adjust)
        if use_cache and key in self._cache:
            return self._cache[key]
        bars = src.fetch_daily_sorted(symbol, start, end, adjust)
        if use_cache:
            self._cache[key] = bars
        return bars

    def get_many_bars(self, symbols: List[str], start, end, adjust: str = "qfq",
                      source: Optional[str] = None) -> Dict[str, List[Bar]]:
        return {s: self.get_bars(s, start, end, adjust=adjust, source=source) for s in symbols}

    def latest_price(self, symbol: str, source: Optional[str] = None) -> Bar:
        src = self._resolve_source(source)
        return src.price_to_fetch(symbol)

    def clear_cache(self) -> None:
        self._cache.clear()

    def _resolve_source(self, source: Optional[str]) -> AbstractDataSource:
        if source is not None:
            if source not in self._sources:
                raise KeyError(f"数据源未注册: {source}")
            return self._sources[source]
        if self._default is None:
            raise ValueError("DataManager 未注册任何数据源")
        return self._default
