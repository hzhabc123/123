#!/usr/bin/env python3
"""
真实行情多标的区间命中率扫描 —— 概率校准的真实数据依据

对多只标的、跨年度跑 IntervalBacktest，汇总各"方向-档位"的真实命中率，
与评分卡档位先验（高/中/低）对比，判断评分卡是否校准；据此给出动态仓位建议。

用法:
    python3 scripts/timing_realscan.py                # 内置标的池（默认2022-2024）
    python3 scripts/timing_realscan.py 600519 000858   # 指定标的（空格分隔）
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import date
from collections import defaultdict

from timing.backtest import IntervalBacktest
from timing.scorer import TimingScorer
from timing.probability import (bayesian_update, kelly_fraction,
                                position_by_level)

# 沪深主板代表标的（白酒/银行/新能源/医药等不同风格）
DEFAULT_POOL = ["600519", "000858", "600036", "601318",
                "300750", "600900", "000333", "600030", "601899", "603259"]

# 各档位的方法论先验（评分卡隐含概率，用于对比校准）
LEVEL_PRIOR = {"高": 0.7, "中": 0.55, "低": 0.4}


def fetch(src, symbol, start, end):
    try:
        return src.fetch_daily_sorted(symbol, start, end)
    except Exception as e:  # 单票失败不中断整体
        print(f"  [!] {symbol} 取数失败: {e}")
        return None


def main():
    symbols = sys.argv[1:] or DEFAULT_POOL
    spans = [(date(2022, 1, 1), date(2024, 12, 31)),   # 3年长周期
             (date(2023, 1, 1), date(2025, 12, 31))]   # 近3年
    # 用最近一次能覆盖的区间（简化：取第一个完整区间）

    from data.akshare_source import AkshareDataSource
    src = AkshareDataSource()

    # 累计各方向-档位
    agg = defaultdict(lambda: {"hits": 0, "total": 0})
    per_symbol = {}

    for sym in symbols:
        bars = fetch(src, sym, spans[0][0], spans[0][1])
        if not bars or len(bars) < 120:
            print(f"[{sym}] 跳过（样本不足 {len(bars) if bars else 0} 根）")
            continue
        bt = IntervalBacktest(scorer=TimingScorer(), lookback=60, min_score=5,
                              horizon=20, target_pct=0.05, stop_pct=0.03)
        res = bt.run(bars)
        per_symbol[sym] = dict(res.level_stats)
        for key, st in res.level_stats.items():
            agg[key]["hits"] += st["hits"]
            agg[key]["total"] += st["total"]
        print(f"[{sym}] {len(bars)}根 触发{[s for s in res.level_stats]}")
        for k, st in sorted(res.level_stats.items()):
            r = st["hits"] / st["total"] if st["total"] else 0
            print(f"      {k:<12} n={st['total']:<4} hit={st['hits']:<4} rate={r:.1%}")

    print("\n========== 全标的汇总命中率（真实数据） ==========")
    print(f"{'类别':<14}{'样本':<6}{'命中率':<9}{'先验':<7}{'偏差'}")
    summary = {}
    for key in sorted(agg):
        st = agg[key]
        rate = st["hits"] / st["total"] if st["total"] else 0
        lvl = key.split("-")[-1]
        prior = LEVEL_PRIOR[lvl]
        delta = rate - prior
        summary[key] = rate
        flag = "校准" if abs(delta) < 0.1 else ("偏乐观" if delta < 0 else "偏保守")
        print(f"{key:<14}{st['total']:<6}{rate:<9.1%}{prior:<7.1%}{delta:+.1%} ({flag})")

    print("\n========== 校准后动态仓位（按真实命中率） ==========")
    for key in sorted(summary):
        emp = summary[key]
        direction, lvl = key.split("-")
        base = position_by_level(lvl)
        posterior = bayesian_update(LEVEL_PRIOR[lvl], emp, 0.7)
        kelly = kelly_fraction(posterior, b=1.5)
        final = 0.5 * base + 0.5 * kelly.capped_fraction
        print(f"{key:<14} 经验{emp:.0%} 后验{posterior:.0%} 凯利{kelly.capped_fraction:.0%} "
              f"档位基准{base:.0%} → 建议{final:.0%}")

    print("\n========== 结论 ==========")
    if agg:
        high_key = max((k for k in agg if k.endswith("-高")), key=lambda k: agg[k]["hits"]/max(agg[k]["total"],1), default=None)
        if high_key:
            print(f"高置信度档位 [{high_key}] 实测命中率 {summary.get(high_key,0):.1%}，"
                  f"样本 {agg[high_key]['total']}。实盘宜以真实命中率替代默认先验做仓位依据。")
    print("注: 命中判定(未来20根±5%)为固定口径，不同参数结论会变；本结果用于方法验证与校准演示。")


if __name__ == "__main__":
    main()