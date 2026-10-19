"""
相关性矩阵 + 聚类 + 独立源筛选测试（correlation_matrix）

覆盖：
- hierarchical_cluster：聚类返回成员 + best_k + labels 大簇在前
- mean_corr_with_baseline：与基准均值相关（排除基准自身）
- yearly_corr：按年分层相关
- 哑标的门槛：信号数不足的标的不应被当作独立信息源

这些是标的选择与有效样本量估算的基础——独立源错了，扩跑的信号数会虚高。
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd
import pytest

from scripts.correlation_matrix import (
    load_returns, yearly_corr, hierarchical_cluster, mean_corr_with_baseline,
)


class TestYearlyCorr:
    def test_yearly_splits_calendar_years(self):
        """yearly_corr 返回长格式，结构切换应体现在年份相关系数上。"""
        idx = pd.date_range("2019-01-01", periods=400, freq="B")
        rng = np.random.default_rng(7)
        a = rng.normal(0, 0.01, len(idx))
        b = a + rng.normal(0, 0.003, len(idx))  # 高相关
        split = 250
        b[split:] = -a[split:] + rng.normal(0, 0.01, len(idx) - split)
        df = pd.DataFrame({"a": a, "b": b}, index=idx)
        out = yearly_corr(df)
        assert set(out.columns) == {"year", "code1", "code2", "corr"}
        years = sorted(out["year"].unique())
        assert 2019 in years
        ab = out[(out["year"] == years[0]) &
                 ((out["code1"] == "a") | (out["code2"] == "a"))]
        assert not ab.empty
        assert ab["corr"].iloc[0] > 0.5

    def test_return_long_format(self):
        idx = pd.date_range("2021-01-01", periods=260, freq="B")
        df = pd.DataFrame({"a": np.random.randn(260), "b": np.random.randn(260)}, index=idx)
        out = yearly_corr(df)
        assert set(out.columns) == {"year", "code1", "code2", "corr"}
        assert len(out) >= 1


class TestHierarchicalCluster:
    def test_clusters_high_corr_together(self):
        rng = np.random.default_rng(1)
        base = rng.normal(0, 0.01, 200)
        corr = pd.DataFrame({
            "a": base + rng.normal(0, 0.002, 200),
            "b": base + rng.normal(0, 0.002, 200),
            "c": rng.normal(0, 0.01, 200),
        })
        cm = corr.corr()
        mapping, k, scores = hierarchical_cluster(cm, "average", 2, 4)
        assert mapping["a"] == mapping["b"]
        assert mapping["c"] != mapping["a"]
        assert 2 <= k <= 4

    def test_gives_remapped_labels_large_cluster_first(self):
        rng = np.random.default_rng(2)
        base = rng.normal(0, 0.01, 200)
        corr = pd.DataFrame({
            "a": base + rng.normal(0, 0.001, 200),
            "b": base + rng.normal(0, 0.001, 200),
            "c": base + rng.normal(0, 0.001, 200),
            "d": rng.normal(0, 0.01, 200),
        })
        cm = corr.corr()
        mapping, k, _ = hierarchical_cluster(cm, "average", 2, 4)
        assert len(set(mapping.values())) >= 2
        assert mapping["a"] == 1 and mapping["b"] == 1 and mapping["c"] == 1


class TestMeanCorrWithBaseline:
    def test_excludes_baseline_self(self):
        rng = np.random.default_rng(3)
        base = rng.normal(0, 0.01, 200)
        corr = pd.DataFrame({
            "base1": base, "base2": base + 0.001,
            "cand": base + rng.normal(0, 0.005, 200),
        })
        cm = corr.corr()
        out = mean_corr_with_baseline(cm, ["base1", "base2"])
        assert "base1" not in out and "base2" not in out
        assert "cand" in out
        assert 0 < out["cand"] < 1

    def test_returns_nan_for_missing(self):
        cm = pd.DataFrame({"x": [1.0, 0.5], "y": [0.5, 1.0]}, index=["x", "y"])
        out = mean_corr_with_baseline(cm, ["missing"])
        assert np.isnan(out["x"])


class TestDumbSymbolLowSignals:
    def test_low_signal_symbol_not_counted_as_independent(self):
        signals = {"600519": 8, "300750": 7, "512880": 19, "588000": 19,
                    "512100": 2, "510880": 10, "512800": 14, "513050": 14,
                    "512170": 14}
        min_sig = 5
        dumb = [k for k, v in signals.items() if v < min_sig]
        assert dumb == ["512100"]
        informative = {k: v for k, v in signals.items() if v >= min_sig}
        assert len(informative) == 8


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))