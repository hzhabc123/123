"""Performance 模块测试"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from datetime import datetime

from core.enums import Side
from portfolio.trade import Trade
from performance.analyzer import PerformanceAnalyzer
from performance.report import ReportGenerator


def make_equity_curve(values):
    return [{"datetime": datetime(2024, 1, 1 + i), "equity": v, "cash": v, "market_value": 0, "close": v} for i, v in enumerate(values)]


def make_trade(side, price, qty, trade_id="T1"):
    return Trade(trade_id=trade_id, order_id="O1", symbol="TEST", side=side, price=price, qty=qty, commission=5.0, trade_time=datetime(2024, 1, 2))


class TestPerformanceAnalyzer:
    def test_positive_return(self):
        analyzer = PerformanceAnalyzer(make_equity_curve([100000, 105000, 110000]), [])
        m = analyzer.compute()
        assert m.total_return == pytest.approx(0.10, abs=1e-4)
        assert m.total_trades == 0

    def test_constant_curve_zero_sharpe(self):
        analyzer = PerformanceAnalyzer(make_equity_curve([100000]*10), [])
        m = analyzer.compute()
        assert m.total_return == 0.0
        assert m.sharpe_ratio == 0.0

    def test_win_rate(self):
        trades = [make_trade(Side.BUY, 10, 100, "T1"), make_trade(Side.SELL, 12, 100, "T2"), make_trade(Side.BUY, 10, 100, "T3"), make_trade(Side.SELL, 9, 100, "T4")]
        analyzer = PerformanceAnalyzer(make_equity_curve([100000, 100100]), trades)
        m = analyzer.compute()
        assert m.total_trades == 4
        assert m.win_rate == pytest.approx(0.5)

    def test_max_drawdown(self):
        analyzer = PerformanceAnalyzer(make_equity_curve([100, 120, 90, 110]), [])
        m = analyzer.compute()
        assert m.max_drawdown == pytest.approx(0.25)

    def test_sharpe_of_steady_growth_positive(self):
        curve = [100000, 100200, 100400, 100600, 100800, 101000]
        analyzer = PerformanceAnalyzer(make_equity_curve(curve), [])
        m = analyzer.compute()
        assert m.sharpe_ratio > 0

    def test_metrics_to_dict_keys(self):
        analyzer = PerformanceAnalyzer(make_equity_curve([100000, 105000]), [])
        d = analyzer.metrics_to_dict()
        assert "sharpe_ratio" in d and "max_drawdown" in d and "total_return" in d
        assert len(d) == 16

    def test_to_dataframe(self):
        analyzer = PerformanceAnalyzer(make_equity_curve([100000, 102000]), [])
        df = analyzer.to_dataframe()
        import pandas as pd
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 2
        assert set(["datetime", "equity", "daily_return", "drawdown"]).issubset(df.columns)

    def test_empty_curve(self):
        analyzer = PerformanceAnalyzer([], [])
        m = analyzer.compute()
        assert m.total_return == 0.0

    def test_benchmark_beta(self):
        strategy = make_equity_curve([100000, 101000, 102000, 103000, 104000, 105000])
        bench = make_equity_curve([100000, 100900, 101800, 102700, 103600, 104500])
        analyzer = PerformanceAnalyzer(strategy, [], benchmark_curve=bench)
        m = analyzer.compute()
        assert 0.5 < m.beta < 2.0


class TestReportGenerator:
    def test_export_equity_csv(self, tmp_path):
        analyzer = PerformanceAnalyzer(make_equity_curve([100000, 102000]), [])
        gen = ReportGenerator(analyzer, [], make_equity_curve([100000, 102000]))
        out = tmp_path / "equity.csv"
        gen.export_equity_csv(str(out))
        assert out.exists()
        content = out.read_text()
        assert "equity" in content

    def test_generate_html(self, tmp_path):
        analyzer = PerformanceAnalyzer(make_equity_curve([100000, 105000, 110000]), [])
        gen = ReportGenerator(analyzer, [], make_equity_curve([100000, 105000, 110000]))
        out = tmp_path / "report.html"
        gen.generate_html(str(out))
        assert out.exists()
        html = out.read_text(encoding="utf-8")
        assert "Quant V2 回测报告" in html
        assert "无成交" in html
        assert "echarts" in html
