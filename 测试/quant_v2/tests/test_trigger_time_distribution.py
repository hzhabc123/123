"""
scripts/trigger_time_distribution.py 测试：时间分布诊断（下跌段占比、季度打点、判定口径）。
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.trigger_time_distribution import _drift, render_md, analyze


def test_drift_negative_in_fall():
    """下跌段内信号 _drift < 0"""
    closes = [100 - i for i in range(60)]  # 持续下跌
    assert _drift(closes, 30) < 0


def test_drift_positive_in_rise():
    """上涨段内信号 _drift > 0"""
    closes = [100 + i for i in range(60)]  # 持续上涨
    assert _drift(closes, 30) > 0


def test_render_md_has_sections():
    """render_md：含下跌段占比、市场状态、判定口径"""
    reps = [{"symbol": "600519", "source": "s", "n_bottom": 10,
             "n_down_seg": 7, "down_ratio": 0.7,
             "by_state": {"趋势": 6, "区间": 4},
             "by_quarter": [{"quarter": "2023-Q1", "n": 4, "seg_dir": "跌",
                             "n_in_downseg": 3}]}]
    md = render_md(reps)
    assert "下跌段" in md
    assert "趋势过滤" in md
    assert "2023-Q1" in md
    assert "70%" in md


def test_analyze_handles_datetime_str():
    """analyze 能解析字符串 datetime（get_trigger_events 返回 ISO 字符串）"""
    # 用合成行情 + 真实引擎链路跑通（不依赖网络）
    import scripts.trigger_time_distribution as ttd
    ttd.load_bars = _synth_load
    from datetime import date
    # monotoonic 上升行情，min_score 应有底部信号
    r = analyze("SYN")
    assert "symbol" in r
    assert r["n_bottom"] >= 0
    assert "by_state" in r and "by_quarter" in r


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
