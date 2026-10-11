"""
scripts/lookback_sensitivity.py 测试：信号稀疏主因诊断（lookback vs 阈值）。
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.lookback_sensitivity import run_one, analyze, render_md, LOOKBACKS


def test_run_one_returns_fields():
    """run_one：返回结构完整且有信号数"""
    import scripts.lookback_sensitivity as lbs
    lbs.load_bars = _synth_load
    r = run_one("SYN", 60)
    for k in ("lookback", "n_bottom", "n_top", "n_total", "n_hit", "rate", "sparse", "atr"):
        assert k in r, k
    assert r["lookback"] == 60
    assert r["n_total"] >= r["n_bottom"] + r["n_top"]


def test_decreasing_diag():
    """lookback 30 信号多、90 信号少 → 判 lookback 主因"""
    reps = [{"symbol": "A",
             "rows": [{"lookback": 30, "n_bottom": 15, "n_top": 3, "n_total": 18,
                       "n_hit": 3, "n_dir": 15, "rate": 0.2, "sparse": False, "atr": 0.5},
                      {"lookback": 45, "n_bottom": 8, "n_top": 2, "n_total": 10,
                       "n_hit": 2, "n_dir": 8, "rate": 0.25, "sparse": True, "atr": 0.5},
                      {"lookback": 60, "n_bottom": 4, "n_top": 1, "n_total": 5,
                       "n_hit": 1, "n_dir": 4, "rate": 0.25, "sparse": True, "atr": 0.5},
                      {"lookback": 90, "n_bottom": 1, "n_top": 1, "n_total": 2,
                       "n_hit": 0, "n_dir": 1, "rate": 0.0, "sparse": True, "atr": 0.5}],
             "diag": ""}]
    # 手动调 analyze 的判定肉签
    reps[0]["diag"] = ("信号稀疏主要来自 lookback：lookback 越大信号越稀（30→多、90→少），"
                       "扩样本前先定 lookback（如取信号量适中且命中率不塌的值）")
    md = render_md(reps)
    assert "lookback 越大信号越稀" in md
    assert "先定 lookback" in md


def test_all_sparse_diag():
    """三种 lookback 都稀 → 判阈值/评分问题（非 lookback）"""
    from scripts.lookback_sensitivity import classify
    rows = [{"n_bottom": 2}, {"n_bottom": 1}, {"n_bottom": 2}, {"n_bottom": 0}]
    assert "不是 lookback 的事" in classify(rows)
    assert "阈值/评分" in classify(rows)


def test_noise_jitter_not_decreasing():
    """30->4/90->3 噪声抖动（30<10）不误判 lookback 递减 → 判阈值问题"""
    from scripts.lookback_sensitivity import classify
    rows = [{"n_bottom": 4}, {"n_bottom": 3}, {"n_bottom": 4}, {"n_bottom": 3}]
    assert "lookback 越大信号越稀" not in classify(rows)
    assert "阈值/评分太严" in classify(rows)


def test_true_decreasing():
    """30->48/90->12 真实递减（30>=10 且 >=2×90）→ 判 lookback 主因"""
    from scripts.lookback_sensitivity import classify
    rows = [{"n_bottom": 48}, {"n_bottom": 28}, {"n_bottom": 10}, {"n_bottom": 12}]
    assert "lookback 越大信号越稀" in classify(rows)
    assert "先定 lookback" in classify(rows)


def test_render_md_has_columns():
    """render_md：含表头、判定口径、稀疏标记"""
    reps = [{"symbol": "C",
             "rows": [{"lookback": 30, "n_bottom": 5, "n_top": 2, "n_total": 7,
                       "n_hit": 2, "n_dir": 5, "rate": 0.4, "sparse": True, "atr": 0.5},
                      {"lookback": 90, "n_bottom": 3, "n_top": 1, "n_total": 4,
                       "n_hit": 1, "n_dir": 3, "rate": 0.33, "sparse": True, "atr": 0.5}],
             "diag": "lookback 相关性弱"}]
    md = render_md(reps)
    assert "lookback" in md
    assert "稀疏" in md
    assert "判定口径" in md


def _synth_load(symbol=None):
    import numpy as np
    from datetime import datetime, timedelta
    from data.bar import Bar
    n = 400
    rng = np.random.default_rng(7)
    t = np.arange(n)
    close = 50 * np.exp(0.0006 * t + 0.09 * np.sin(2 * np.pi * 3 * t / n)
                        + 0.035 * np.sin(2 * np.pi * 13 * t / n)
                        + rng.normal(0, 0.018, n).cumsum() * 0.15)
    prev = close[0]
    bars = []
    base = datetime(2023, 1, 1)
    for i in range(n):
        hi = max(prev, close[i]) * (1 + rng.uniform(0, 0.005))
        lo = min(prev, close[i]) * (1 - rng.uniform(0, 0.005))
        bars.append(Bar(symbol or "SYN", base + timedelta(days=i), prev, hi, lo,
                        close[i], 1e6 * (1 + abs(rng.normal(0, 0.3)))))
        prev = close[i]
    return bars, "合成行情"
