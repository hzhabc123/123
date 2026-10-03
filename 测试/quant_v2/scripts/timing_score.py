#!/usr/bin/env python3
"""
Quant V2 择时增强模块端到端演示

链路：数据 -> indicators(指标) -> signals(10类信号) -> scorer(评分卡)
      -> probability(凯利仓位 + 概率校准 + 贝叶斯更新)

用法：
  python3 scripts/timing_score.py
"""

import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from timing.signals import build_signal_items, SignalInput
from timing.scorer import TimingScorer
from timing.probability import kelly_fraction, position_by_level, bayesian_update, ProbabilityCalibrator


def load_price_series(n=400, seed=42):
    """生成一段包含底部特征的演示价格序列（真实数据可替换）"""
    rng = np.random.default_rng(seed)
    prices = [100.0]
    segments = [(-0.006, 0.004, 90), (0.001, 0.003, 60), (0.006, 0.004, 100),
                (0.0, 0.006, 60), (-0.007, 0.004, 90)]
    for drift, vol, cnt in segments:
        for _ in range(cnt):
            prices.append(prices[-1] * (1 + rng.normal(drift, vol)))
        while len(prices) > n:
            prices.pop()
    return np.asarray(prices[:n])


def run():
    closes = load_price_series()[:400]
    r1 = np.random.default_rng(1); r2 = np.random.default_rng(2); r3 = np.random.default_rng(3)
    highs = closes * (1 + abs(r1.normal(0, 0.004, len(closes))))
    lows = closes * (1 - abs(r2.normal(0, 0.004, len(closes))))
    volumes = r3.integers(5000, 100000, len(closes)).astype(float)

    inp = SignalInput(closes=closes, highs=highs, lows=lows, volumes=volumes)
    externals = {
        "cross": {"name": "跨市场-风险偏好回升", "hit": 1, "detail": "股债汇同步回暖"},
        "fundamental": {"name": "基本面-估值低分位", "hit": 1, "detail": "PE处于历史20%分位"},
        "options": {"name": "期权-PCR偏高", "hit": 1, "detail": "看跌/看涨比率0.9"},
        "timing": {"name": "时间-财报落地", "hit": 0, "detail": "财报窗口已过"},
    }
    items = build_signal_items(inp, fear_greed=None, externals=externals)

    print("=" * 60); print("信号项明细"); print("=" * 60)
    for it in items:
        mark = "✓" if it.hit else "·"
        print(f"  [{mark}] {it.name:<26} {it.detail}")

    scorer = TimingScorer()
    result = scorer.score(items)
    print("\n" + "=" * 60); print("评分卡"); print("=" * 60)
    print(f"  底部得分 : {result.bottom_score}/10")
    print(f"  顶部得分 : {result.top_score}/10")
    print(f"  方向     : {result.direction}")
    print(f"  置信档位 : {result.level}")

    p = 0.65 if result.level == "高" else (0.55 if result.level == "中" else 0.42)
    b = 1.5
    kelly = kelly_fraction(p, b)
    pos = position_by_level(result.level)
    print("\n" + "=" * 60); print("仓位与风控"); print("=" * 60)
    print(f"  估算胜率   : {p}")
    print(f"  赔率       : {b}")
    print(f"  凯利比例   : {kelly.kelly_fraction:.2f} (风控后 {kelly.capped_fraction:.2f})")
    print(f"  建议仓位   : {pos*100:.0f}% (档位:{result.level})")
    print(f"  单笔止损   : 不超过总资金 2%")

    cal = ProbabilityCalibrator()
    for it in items:
        cal.record(it.name, bool(it.hit))
    print("\n" + "=" * 60); print("概率校准（信号命中率）"); print("=" * 60)
    for k, v in cal.all_rates().items():
        print(f"  {k:<26} 命中率 {v:.2f}")

    posterior = bayesian_update(0.5, p, evidence_weight=0.6)
    print(f"\n  贝叶斯: 先验0.50 + 信号{p:.2f} → 后验 {posterior:.2f}")
    return result


if __name__ == "__main__":
    run()
