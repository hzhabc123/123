#!/usr/bin/env python3
"""
单因子区分度检验（TimingStrategy 评分卡重建的前置诊断）

背景：合成评分（所有底部因子加总）已被证明无区分度（茅台 lb=30：42/48 压死 score=4，
forward_return_20 最高箱−最低箱仅 +2.4pp）。重建评分卡之前必须知道：到底哪个因子（类别）
单独与未来 20 日收益相关。如果所有因子单独都无区分度，问题不在评分卡而在因子池本身
（这套技术因子在 A 股日线、这批标的上与未来收益无关），重建就是徒劳。

本脚本对 lb=30 的全部 bottom_enter 事件，逐个底部类别拆开：
  因子         满足组fwd20   不满足组fwd20   差异(n满足/n不满足)
  RSI/动量     ...          ...            ...(+/-pp, n/n)
  ...
回答三个问题：
  1. 单因子有区分度（差异 >3pp）？→ 重建有意义，按它加权
  2. 所有因子都无区分度？→ 因子池本身无信息，换因子类别/换时间框架
  3. 因子高度共线（满足A必满足B）？→ 分数聚集必然，换独立维度因子而非调权重

事件字段依赖：TimingStrategy._record_trigger 自 2026-10 起记录 bottom_cats（命中的底部类别集合）。

用法:
    python3 scripts/factor_discrimination.py 600519            # 单因子对照表 + 共线性矩阵（lb=30）
    python3 scripts/factor_discrimination.py 600519 --lb 60    # 指定 lookback
    python3 scripts/factor_discrimination.py 600519 --out f.json
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from collections import defaultdict


def load_bars(symbol=None):
    """与 review_triggers / plot_timing_signals 一致：真实行情优先，否则合成"""
    if symbol:
        from datetime import date
        from data.akshare_source import AkshareDataSource
        try:
            src = AkshareDataSource()
            bars = src.fetch_daily_sorted(symbol, date(2023, 1, 1), date(2025, 1, 1))
            if bars and len(bars) > 120:
                return bars, f"真实行情 {symbol}"
        except Exception:
            pass  # 落到合成行情
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
    base = datetime(2024, 1, 1)
    for i in range(n):
        hi = max(prev, close[i]) * (1 + rng.uniform(0, 0.005))
        lo = min(prev, close[i]) * (1 - rng.uniform(0, 0.005))
        bars.append(Bar(symbol or "SYN", base + timedelta(days=i), prev, hi, lo,
                        close[i], 1e6 * (1 + abs(rng.normal(0, 0.3)))))
        prev = close[i]
    return bars, f"合成行情 {symbol or 'SYN'}"


# 底部类别展示顺序（与 scorer.CATEGORY_KEYS 一致的稳定顺序）
CATEGORY_ORDER = ["结构", "动量", "量能", "波动", "情绪", "跨市场", "基本面", "期权", "时间", "确认"]


def _run_bottom_events(symbol, lookback=30, min_score=3):
    """跑引擎，返回带 bottom_cats 与 forward_return_20 的 bottom_enter 事件列表"""
    from strategy.timing_strategy import TimingStrategy
    from engine.backtest_engine import BacktestEngine
    from portfolio.portfolio import Portfolio
    from risk.risk_manager import RiskManager, RiskConfig
    from risk.position_sizer import PercentSizer

    bars, source = load_bars(symbol)
    strat = TimingStrategy(min_score=min_score, direction_mode="both", lookback=lookback)
    portfolio = Portfolio(initial_cash=500_000.0)
    rc = RiskConfig()
    rc.max_single_trade_amount = 1_000_000.0
    rc.max_single_trade_ratio = 0.4
    rc.max_position_ratio = 0.8
    engine = BacktestEngine(strategy=strat, portfolio=portfolio,
                            risk_manager=RiskManager(rc),
                            position_sizer=PercentSizer(percent=0.3, min_amount=1000.0),
                            symbol=strat.name, lookback=500)
    engine.run(bars)
    events = strat.get_trigger_events(annotate=True)
    bottoms = [e for e in events if e["trigger_type"] == "bottom_enter"
               and e.get("forward_return_20") is not None]
    return bottoms, source


def list_factors(bottoms):
    """出现过的底部类别，按 CATEGORY_ORDER 稳定排序"""
    seen = {c for e in bottoms for c in (e.get("bottom_cats") or [])}
    order = [c for c in CATEGORY_ORDER if c in seen]
    extras = sorted(seen - set(CATEGORY_ORDER))
    return order + extras


def factor_discrimination(symbol, lookback=30, min_score=3, out_path=None):
    """单因子区分度：每个底部类别，满足组 vs 不满足组的 forward_return_20 均值差异"""
    bottoms, source = _run_bottom_events(symbol, lookback, min_score)
    n = len(bottoms)
    print(f"===== 单因子区分度检验（{source}，bottom_enter={n}，lb={lookback} "
          f"min_score={min_score}）=====")
    if n == 0:
        print("无 bottom_enter 事件")
        return
    if n < 10:
        print(f"⚠️ 样本仅 {n}（<10），结果仅为提示，不据此下结论")

    factors = list_factors(bottoms)
    rows = []
    for f in factors:
        hit = [e for e in bottoms if f in (e.get("bottom_cats") or [])]
        miss = [e for e in bottoms if f not in (e.get("bottom_cats") or [])]
        mh = sum(e["forward_return_20"] for e in hit) / len(hit) if hit else None
        mm = sum(e["forward_return_20"] for e in miss) / len(miss) if miss else None
        diff = (mh - mm) * 100 if (mh is not None and mm is not None) else None
        rows.append({
            "factor": f, "hit_n": len(hit), "miss_n": len(miss),
            "hit_mean": mh, "miss_mean": mm, "diff_pp": diff,
        })

    print(f"| 因子(类别) | 满足组fwd20 | n满足 | 不满足组fwd20 | n不满足 | 差异(pp) | 判定 |")
    print(f"|-----------|------------|-------|--------------|---------|---------|------|")
    for r in rows:
        f_mean = f"{r['hit_mean']*100:+.1f}%" if r["hit_mean"] is not None else "  -  "
        m_mean = f"{r['miss_mean']*100:+.1f}%" if r["miss_mean"] is not None else "  -  "
        diff = r["diff_pp"]
        judge = "—"
        if diff is not None and r["hit_n"] >= 3 and r["miss_n"] >= 3:
            judge = ("✓ 有区分度" if diff > 3
                     else "✗ 反向" if diff < -3
                     else "≈ 无区分度")
        print(f"| {r['factor']} | {f_mean} | {r['hit_n']} | {m_mean} | {r['miss_n']} | "
              f"{diff if diff is None else f'{diff:+.1f}'} | {judge} |")

    # 结论
    strong = [r["factor"] for r in rows
              if r["diff_pp"] is not None and r["diff_pp"] > 3
              and r["hit_n"] >= 3 and r["miss_n"] >= 3]
    print()
    if strong:
        print(f"✓ 有 {len(strong)} 个因子单独有区分度（差异>3pp）：{', '.join(strong)} → 重建有意义，按它加权")
    else:
        print("⚠️ 所有因子单独均无区分度（|差异|≤3pp 或组样本<3）→ 问题可能在因子池本身，"
              "重建评分卡可能是徒劳，需先考虑换因子类别/时间框架")

    # 共线性矩阵：P(行因子命中 | 列因子命中) —— 行×列同时命中的占比
    print("\n===== 共线性矩阵（P(行因子命中 | 列因子亦命中)）=====")
    print("  值越接近 1.0，两因子越同步命中 → 分数必然聚集，需换独立维度因子")
    header = "因子".ljust(4) + "".join(f"{f:>8}" for f in factors)
    print(header)
    n_ev = len(bottoms)
    for fa in factors:
        hit_a = {id(e) for e in bottoms if fa in (e.get("bottom_cats") or [])}
        line = fa.ljust(4)
        for fb in factors:
            if fa == fb:
                line += f"{'—':>8}"
                continue
            hit_b = {id(e) for e in bottoms if fb in (e.get("bottom_cats") or [])}
            if not hit_b:
                line += f"{'0':>8}"
                continue
            both = len(hit_a & hit_b) / len(hit_b)
            line += f"{both:>8.2f}"
        print(line)

    if out_path:
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump({"symbol": symbol, "n_bottom": n, "rows": rows}, fh,
                      ensure_ascii=False, indent=2)
        print(f"\n已写出: {out_path}")


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    symbol = args[0] if args else None
    lookback = 30
    if "--lb" in sys.argv:
        lookback = int(sys.argv[sys.argv.index("--lb") + 1])
    out_path = None
    if "--out" in sys.argv:
        out_path = sys.argv[sys.argv.index("--out") + 1]
    if not symbol:
        print("用法: python3 scripts/factor_discrimination.py <symbol> [--lb N] [--out f.json]")
        return
    factor_discrimination(symbol, lookback=lookback, out_path=out_path)


if __name__ == "__main__":
    main()
