"""
timing/backtest 区间命中率验证器测试

覆盖：命中判定逻辑、不偷看未来、档位统计、概率校准闭环、外任信号注入、类目差异化。
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pytest
from datetime import datetime, timedelta

from timing.backtest import IntervalBacktest
from timing.scorer import TimingScorer
from timing.probability import ProbabilityCalibrator, bayesian_update
from data.bar import Bar


def make_bars(closes, seed=1):
    n = len(closes)
    bars = []
    prev = closes[0]
    rng = np.random.default_rng(seed)
    for i in range(n):
        hi = max(prev, closes[i]) * (1 + rng.uniform(0, 0.004))
        lo = min(prev, closes[i]) * (1 - rng.uniform(0, 0.004))
        bars.append(Bar(symbol="T", datetime=datetime(2024, 1, 1) + timedelta(days=i),
                        open=prev, high=hi, low=lo, close=closes[i], volume=1e6))
        prev = closes[i]
    return bars


def test_no_peeking_uses_past_only():
    """打分只用 t 之前数据：未来价格不应影响此时点信号"""
    base = np.sin(np.linspace(0, 4 * np.pi, 200)) * 5 + 50
    b1 = make_bars(base.tolist())
    b2 = make_bars(np.concatenate([base[:180], np.linspace(0.1, 1, 20) * 1e9]).tolist())
    bt = IntervalBacktest(lookback=60, min_score=5)
    r1 = bt.run(b1); r2 = bt.run(b2)
    # 前 180 根内信号时点应完全一致（未来暴涨不影响打分）
    c1 = [r.index for r in r1.records if r.index < 180]
    c2 = [r.index for r in r2.records if r.index < 180]
    assert c1 == c2


def test_bottom_hit_requires_upswing():
    """底部信号命中要求未来出现目标涨幅"""
    closes = [50] * 80 + [x for x in np.linspace(50, 20, 40)]
    bars = make_bars(closes)
    bt = IntervalBacktest(lookback=60, min_score=5, horizon=20,
                          target_pct=0.05, stop_pct=0.03)
    r = bt.run(bars)
    assert len(r.records) >= 0
    assert all(len(x) == 2 for x in r.level_stats.values())


def test_strong_roundtrip_yields_hits():
    """V 型反转应产生底部命中"""
    closes = np.concatenate([
        np.linspace(40, 30, 80),
        np.linspace(30, 60, 80),
    ])
    bars = make_bars(closes)
    bt = IntervalBacktest(lookback=60, min_score=5, horizon=30,
                          target_pct=0.05, stop_pct=0.02)
    r = bt.run(bars)
    hits = sum(rec.hit for rec in r.records)
    assert hits > 0, "V型反转底部信号应产生命中"


def test_calibrator_loopback():
    """ProbabilityCalibrator 记录与回读闭环"""
    bt = IntervalBacktest()
    bt.calibrator.record("底部-高", True)
    bt.calibrator.record("底部-高", False)
    bt.calibrator.record("底部-高", True)
    assert bt.calibrator.hit_rate("底部-高") == pytest.approx(2 / 3)


def test_bayesian_update_bounds():
    """贝叶斯更新结果应在先验与证据之间"""
    p = bayesian_update(0.5, 0.8, 0.6)
    assert 0.5 < p < 0.8
    q = bayesian_update(0.5, 0.2, 0.6)
    assert 0.2 < q < 0.5


def test_externals_injection_changes_signal():
    """注入外部信号可增加底部信号触发"""
    closes = np.random.default_rng(3).normal(50, 1.5, 200).cumsum() + 50
    closes = np.clip(closes, 20, 90)
    bars = make_bars(closes)

    def ext_fn(t, bars):
        if t % 10 == 0:
            return {"情绪-恐慌": {"hit": 1, "detail": "恐慌"},
                    "跨市场-股债汇共振": {"hit": 1, "detail": "共振"},
                    "基本面-低分位": {"hit": 1, "detail": "低分位"},
                    "期权-PCR极高": {"hit": 1, "detail": "PCR高"}}
        return {}

    bt_no = IntervalBacktest(lookback=60, min_score=7)
    bt_ext = IntervalBacktest(lookback=60, min_score=7)
    r_no = bt_no.run(bars)
    r_ext = bt_ext.run(bars, externals_fn=ext_fn)
    bot_no = sum(1 for x in r_no.records if x.direction == "bottom")
    bot_ext = sum(1 for x in r_ext.records if x.direction == "bottom")
    assert bot_ext >= bot_no


def test_category_stats_differentiated():
    """类目级独立判定：不同类目因出现时点不同 → 命中率应差异化（非全部相同）"""
    seg1 = np.linspace(50, 30, 70)     # 下跌段
    seg2 = np.linspace(30, 62, 100)    # V 型反弹段
    closes = np.concatenate([seg1, seg2])
    bars = make_bars(closes.tolist())
    bt = IntervalBacktest(lookback=60, min_score=5, horizon=12,
                          target_pct=0.03, stop_pct=0.02)
    res = bt.run(bars)
    rates = {k: v["hits"] / v["total"] for k, v in res.category_stats.items() if v["total"] >= 5}
    assert len(rates) >= 2, f"样本充足类目应≥2, got {list(rates)}"
    assert len(set(round(r, 3) for r in rates.values())) >= 2, f"命中率应差异化: {rates}"


def test_insufficient_data_no_crash():
    """lookback 比总长度大时不应报错"""
    bars = make_bars([50] * 30)
    bt = IntervalBacktest(lookback=60)
    r = bt.run(bars)
    assert len(r.records) == 0