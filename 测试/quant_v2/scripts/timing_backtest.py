#!/usr/bin/env python3
"""
择时区间命中率回测脚本 —— timing 模块验证入口

把 TimingScorer 接入历史数据（真实 akshare 或合成序列），验证评分卡档位
与实际概率是否一致，并据此做概率校准与动态仓位建议。

用法:
    python3 scripts/timing_backtest.py
    python3 scripts/timing_backtest.py 600519 20240101 20241231
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime

import numpy as np

from timing.scorer import TimingScorer
from timing.backtest import IntervalBacktest
from timing.probability import (ProbabilityCalibrator, kelly_fraction,
                                bayesian_update, position_by_level)


def load_akshare(symbol, start, end):
    from data.akshare_source import AkshareDataSource
    from data.data_manager import DataManager
    dm = DataManager(AkshareDataSource())
    bars = dm.get_bars(symbol=symbol, start_date=start, end_date=end)
    if not bars:
        raise SystemExit(f"未取到 {symbol} 行情，请检查代码/网络")
    return bars


def load_synthetic(n=400, seed=7, drift=0.0006, vol=0.018, trend_cycles=3):
    rng = np.random.default_rng(seed)
    t = np.arange(n)
    trend = drift * t
    cycle = 0.09 * np.sin(2 * np.pi * trend_cycles * t / n)
    cycle2 = 0.035 * np.sin(2 * np.pi * 13 * t / n)
    noise = rng.normal(0, vol, n).cumsum() * 0.15
    close = 50 * np.exp(trend + cycle + cycle2 + noise)
    open_ = np.empty(n); high = np.empty(n); low = np.empty(n); vol_ = np.empty(n)
    open_[0] = close[0]
    for i in range(1, n):
        open_[i] = close[i - 1]
        hi = max(open_[i], close[i])
        lo = min(open_[i], close[i])
        high[i] = hi * (1 + rng.uniform(0, 0.005))
        low[i] = lo * (1 - rng.uniform(0, 0.005))
        vol_[i] = 1e6 * (1 + abs(rng.normal(0, 0.3)))
    from data.bar import Bar
    from datetime import timedelta
    base = datetime(2024, 1, 1)
    return [Bar(symbol="SYN", datetime=base + timedelta(days=i),
                open=open_[i], high=high[i], low=low[i], close=close[i],
                volume=vol_[i]) for i in range(n)]


def main():
    if len(sys.argv) >= 4:
        bars = load_akshare(sys.argv[1], sys.argv[2], sys.argv[3])
        print(f"使用真实行情 {sys.argv[1]}，共 {len(bars)} 根")
    else:
        bars = load_synthetic()
        print(f"使用合成行情，共 {len(bars)} 根（未接入网络）")

    scorer = TimingScorer()
    bt = IntervalBacktest(scorer=scorer, lookback=60, min_score=5,
                          horizon=20, target_pct=0.05, stop_pct=0.03)
    result = bt.run(bars)

    print("\n===== 区间命中率回测 =====")
    print(f"触发区间信号总数: {len(result.records)}")
    print(f"{'类别':<14}{'样本':<6}{'命中':<6}{'命中率':<8}")
    for key, st in sorted(result.level_stats.items()):
        rate = st["hits"] / st["total"] if st["total"] else 0
        print(f"{key:<14}{st['total']:<6}{st['hits']:<6}{rate:<8.2%}")

    print("\n===== 概率校准 =====")
    cal = bt.calibrator
    all_rates = cal.all_rates()
    for k, v in sorted(all_rates.items()):
        print(f"  {k}: 经验命中率 {v:.2%}")

    print("\n===== 校准后动态仓位建议 =====")
    best_key = max(all_rates, key=lambda k: all_rates[k]) if all_rates else None
    if best_key:
        emp = all_rates[best_key]
        direction, level = best_key.split("-")
        base = position_by_level(level)
        prior = 0.5
        posterior = bayesian_update(prior, emp, 0.6)
        kelly = kelly_fraction(posterior, b=1.5)
        final_rate = 0.5 * base + 0.5 * kelly.capped_fraction
        print(f"  最优信号: {best_key} (经验命中率 {emp:.2%})")
        print(f"  档位基准仓位 by {level}: {base:.0%}")
        print(f"  贝叶斯后验: {prior:.0%} -> {posterior:.2%}")
        print(f"  凯利仓位(截断): {kelly.capped_fraction:.1%}")
        print(f"  融合建议仓位: {final_rate:.1%}")
        print("  实盘前须用真实数据校准，本结果为方法论闭环演示")
    else:
        print("  无足够样本，需更长历史")


if __name__ == "__main__":
    main()