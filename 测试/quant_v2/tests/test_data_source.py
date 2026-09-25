"""数据源模块测试：AbstractDataSource / 适配器 / DataManager"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from datetime import date, datetime

from data.data_source import AbstractDataSource, DataSourceError, DataSourceAuthError
from data.data_manager import DataManager
from data.akshare_source import AkshareDataSource, _normalize_symbol
from data.gm_source import _gm_symbol
from data.bar import Bar


class FakeSource(AbstractDataSource):
    name = "fake"
    def __init__(self, **kw):
        super().__init__(**kw)
        self.calls = 0
    def fetch_daily(self, symbol, start, end, adjust="qfq"):
        self.calls += 1
        return [
            Bar(symbol=symbol, datetime=datetime(2024,1,2), open=10, high=11, low=9, close=10.5, volume=1000),
            Bar(symbol=symbol, datetime=datetime(2024,1,3), open=10.5, high=12, low=10, close=11.5, volume=1000),
        ]
    def price_to_fetch(self, symbol):
        return self.fetch_daily(symbol, None, None)[-1]


class TestCodeNormalize:
    def test_akshare_prefix(self):
        assert _normalize_symbol("600519") == "sh600519"
        assert _normalize_symbol("000001") == "sz000001"
        assert _normalize_symbol("sh600519") == "sh600519"
        assert _normalize_symbol("688001") == "sh688001"
        assert _normalize_symbol("300750") == "sz300750"

    def test_gm_prefix(self):
        assert _gm_symbol("600519") == "SHSE.600519"
        assert _gm_symbol("000001") == "SZSE.000001"
        assert _gm_symbol("SHSE.600519") == "SHSE.600519"


class TestFakeSource:
    def test_fetch_sorted(self):
        src = FakeSource()
        bars = src.fetch_daily_sorted("TEST", date(2024,1,1), date(2024,1,31))
        assert bars[0].datetime == datetime(2024,1,2)

    def test_default_bar_fields(self):
        src = FakeSource()
        bars = src.fetch_daily("TEST", date(2024,1,1), date(2024,1,31))
        assert bars[0].volume == 1000.0
        assert isinstance(bars[0], Bar)

    def test_auth_required_raises(self):
        class NeedAuth(FakeSource):
            def fetch_daily(self, *a, **k):
                self._check_auth()
                return []
        src = NeedAuth()
        with pytest.raises(DataSourceAuthError):
            src.fetch_daily("T", None, None)


class TestDataManager:
    def test_register_and_default(self):
        dm = DataManager()
        assert dm.default is None
        src = FakeSource()
        dm.register("fake", src)
        assert dm.default is src

    def test_get_bars_cache(self):
        src = FakeSource()
        dm = DataManager({"fake": src})
        bars1 = dm.get_bars("A", date(2024,1,1), date(2024,1,31))
        bars2 = dm.get_bars("A", date(2024,1,1), date(2024,1,31))
        assert src.calls == 1
        assert bars1 is bars2

    def test_many_symbols(self):
        src = FakeSource()
        dm = DataManager({"fake": src})
        out = dm.get_many_bars(["A", "B"], date(2024,1,1), date(2024,1,31))
        assert set(out) == {"A", "B"}
        assert all(len(v) == 2 for v in out.values())

    def test_unregistered_source_raises(self):
        dm = DataManager({"fake": FakeSource()})
        with pytest.raises(KeyError):
            dm.get_bars("A", None, None, source="nope")

    def test_no_source_raises(self):
        dm = DataManager()
        with pytest.raises(ValueError):
            dm.get_bars("A", None, None)

    def test_clear_cache(self):
        src = FakeSource()
        dm = DataManager({"fake": src})
        dm.get_bars("A", date(2024,1,1), date(2024,1,31))
        dm.clear_cache()
        dm.get_bars("A", date(2024,1,1), date(2024,1,31))
        assert src.calls == 2
