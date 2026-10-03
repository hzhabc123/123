"""
Quant V2 择时增强模块测试（timing/）

验证：指标计算、信号分类与聚合、档位边界、凯利、贝叶斯、方向偏向。
"""

import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pytest

from timing import indicators as ind
from timing.signals import SignalInput, structure_signal
from timing.scorer import TimingScorer
from timing.probability import kelly_fraction, ProbabilityCalibrator, bayesian_update, position_by_level


def _series(n=120, seed=5, drift=0.003, vol=0.006):
    rng = np.random.default_rng(seed)
    p = [100.0]
    for _ in range(n):
        p.append(p[-1] * (1 + rng.normal(drift, vol)))
    a = np.asarray(p[1:])
    return a, a * (1 + abs(rng.normal(0, 0.004, n))), a * (1 - abs(rng.normal(0, 0.004, n)))


# ---------------- 指标 ---------------- #

def test_sma():
    v = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    s = ind.sma(v, 3)
    assert np.isnan(s[0]) and np.isnan(s[1])
    assert s[2] == pytest.approx(2.0)
    assert s[4] == pytest.approx(4.0)


def test_rsi_bounds():
    v = np.array([1.0 + 0.1 * i for i in range(30)])
    r = ind.rsi(v, 14)
    valid = r[~np.isnan(r)]
    assert len(valid) > 0
    assert valid.max() <= 100.0 and valid.min() >= 0.0
    assert valid[-1] > 70


def test_atr_positive():
    h = np.full(30, 11.0); l = np.full(30, 9.0); c = np.linspace(10, 12, 30)
    a = ind.atr(h, l, c, 14)
    assert len(a[~np.isnan(a)]) > 0
    assert np.nanmin(a) > 0


def test_bollinger_mid_eq_sma():
    v = np.arange(1.0, 41.0)
    b = ind.bollinger(v, 20); s = ind.sma(v, 20)
    assert b.mid[-1] == pytest.approx(s[-1])
    assert b.upper[-1] > b.mid[-1] > b.lower[-1]


def test_vwap_between():
    t = np.full(10, 100.0); v = np.full(10, 1000.0)
    assert ind.vwap(t, v)[-1] == pytest.approx(100.0)


def test_volume_profile_poc_inside():
    h = np.full(50, 110.0); l = np.full(50, 90.0); v = np.full(50, 1000.0)
    vp = ind.volume_profile(h, l, v)
    assert vp is not None
    assert vp.val <= vp.poc <= vp.vah


# ---------------- 信号与评分卡 ---------------- #

def test_signal_input_requires_series():
    inp = SignalInput(closes=np.array([1.0, 2.0]))
    assert len(structure_signal(inp)) >= 1


def test_scorer_category_dedup():
    from timing.signals import SignalItem
    items = [
        SignalItem("结构-接近前低", 1, "a"), SignalItem("结构-前低支撑", 1, "b"),
        SignalItem("动量-RSI超卖", 1, "c"), SignalItem("量能-地量后放量阳线", 1, "d"),
    ]
    assert TimingScorer().score(items).bottom_score == 3


def test_scorer_level_boundary():
    from timing.signals import SignalItem
    base = [
        SignalItem("结构-接近前低", 1, ""), SignalItem("动量-RSI超卖", 1, ""),
        SignalItem("量能-地量后放量阳线", 1, ""), SignalItem("波动-布林下轨收回", 1, ""),
    ]
    assert TimingScorer().score(base).level == "低"
    items5 = base + [SignalItem("情绪-RSI恐慌(代理)", 1, "")]
    assert TimingScorer().score(items5).level == "中"
    items6 = items5 + [SignalItem("确认-收盘创新低", 1, "")]
    assert TimingScorer().score(items6).level == "中"
    items7 = items6 + [SignalItem("跨市场-股债汇共振偏多", 1, "")]
    assert TimingScorer().score(items7).level == "高"


def test_scorer_direction_top():
    from timing.signals import SignalItem
    items = [
        SignalItem("结构-接近前高", 1, ""), SignalItem("动量-MACD死叉", 1, ""),
        SignalItem("量能-天量滞涨", 1, ""), SignalItem("波动-布林上轨回落", 1, ""),
        SignalItem("情绪-RSI狂热(代理)", 1, ""), SignalItem("确认-收盘创新高", 1, ""),
        SignalItem("基本面-估值高分位", 1, ""),
    ]
    r = TimingScorer().score(items)
    assert r.top_score >= 5
    assert r.direction == "看空"


# ---------------- 概率模型 ---------------- #

def test_kelly_positive():
    r = kelly_fraction(p=0.6, b=1.0)
    assert r.kelly_fraction == pytest.approx(0.2)
    assert r.capped_fraction <= 0.5


def test_kelly_negative_expected():
    r = kelly_fraction(p=0.3, b=1.0)
    assert r.kelly_fraction == pytest.approx(0.0)
    assert r.capped_fraction == pytest.approx(0.0)


def test_kelly_cap():
    r = kelly_fraction(p=0.9, b=2.0, max_cap=0.5)
    assert r.capped_fraction == pytest.approx(0.5)


def test_bayesian_update_range():
    post = bayesian_update(0.5, 0.7, 0.5)
    assert 0.5 <= post <= 0.7
    assert post == pytest.approx(0.6)


def test_position_by_level():
    assert position_by_level("高") > position_by_level("中") > position_by_level("低")


def test_calibrator_records():
    cal = ProbabilityCalibrator()
    cal.record("a", True); cal.record("a", True); cal.record("a", False)
    assert cal.hit_rate("a") == pytest.approx(2 / 3)
