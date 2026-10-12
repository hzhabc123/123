#!/usr/bin/env python3
"""
动量显著性检验（重建评分卡前必须先补的统计) 
上一轮 factor_discrimination 只报了差异(+3.3pp)却没报满足/不满足组内 n 也没做显著性——
5 个样本的 +3.3pp 和 30 个样本的 +3.3pp 是两件完全不同的事。本脚本补齐：

  1. 每个因子满足/不满足组内 n
  2. bootstrap 2000 次重采样：95%CI + P(差>0)，判定动量差异是否显著
  3. 状态分层（market_state 趋势/区间）重算差异——验证"结构因子反向=状态混淆"假设

结论决定下一步：动量显著→纯动量基线有意义；动量不显著→这套技术因子在 A 股日线上无效，
换因子池而非重建评分卡。

依赖：TimingStrategy 触发事件带 bottom_cats（命中底部类别集合），见 timing_strategy.py。

用法:
    python3 scripts/momentum_significance.py 600519
    python3 scripts/momentum_significance.py 600519 --out outputs/momentum_sig_600519.json
"""
import sys, os, json, random
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def load_bars(symbol=None):
    """与 factor_discrimination / review_triggers 一致：真实行情优先，否则合成"""
    if symbol:
        from datetime import date
        from data.akshare_source import AkshareDataSource
        try:
            src = AkshareDataSource()
            bars = src.fetch_daily_sorted(symbol, date(2023, 1, 1), date(2025, 1, 1))
            if bars and len(bars) > 120:
                return bars, f"真实行情 {symbol}"
        except Exception:
            pass
    import numpy as np
    from datetime import datetime, timedelta
    from data.bar import Bar
    n = 400
    rng = np.random.default_rng(11)
    t = np.arange(n)
    close = 50 * np.exp(0.0007 * t + 0.085 * np.sin(2 * np.pi * 3 * t / n)
                        + 0.04 * np.sin(2 * np.pi * 15 * t / n)
                        + rng.normal(0, 0.02, n).cumsum() * 0.14)
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


CATEGORY_ORDER = ["结构", "动量", "量能", "波动", "情绪", "跨市场", "基本面", "期权", "时间", "确认"]


def _run_bottom_events(symbol, lookback=30, min_score=3):
    """跑引擎，返回事件列表（带 bottom_cats + forward_return_20）+ 完整 closes + 数据源"""
    from strategy.timing_strategy import TimingStrategy
    from engine.backtest_engine import BacktestEngine
    from portfolio.portfolio import Portfolio
    from risk.risk_manager import RiskManager, RiskConfig
    from risk.position_sizer import PercentSizer
    import numpy as np

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
    closes = list(strat.closes)
    return bottoms, np.array(closes, dtype=float), source


# ---- bootstrap 显著性（2000 次重采样） ----
def bootstrap_significance(hit, miss, n_boot=2000, seed=42):
    """对"满足组均值 - 不满足组均值"做 bootstrap：返回 95%CI 与 P(差>0)。
    注意：只对组内样本各≥3 时调（否则 CI 无意义）。"""
    rng = random.Random(seed)
    diffs = []
    for _ in range(n_boot):
        hb = [rng.choice(hit) for _ in hit]
        mb = [rng.choice(miss) for _ in miss]
        diffs.append(sum(hb) / len(hb) - sum(mb) / len(mb))
    diffs.sort()
    lo = diffs[int(0.025 * n_boot)]
    hi = diffs[int(0.975 * n_boot) - 1]
    p_pos = sum(1 for d in diffs if d > 0) / n_boot
    return (lo, hi), p_pos


def momentum_significance(symbol, lookback=30, out_path=None):
    """输出：每因子 n + 差异 + bootstrap + 状态分层差异"""
    bottoms, closes, source = _run_bottom_events(symbol, lookback)
    n = len(bottoms)
    print(f"===== 动量显著性检验（{source}，bottom_enter={n}，lb={lookback}）=====")
    if n == 0:
        print("无 bottom_enter 事件")
        return
    if n < 10:
        print(f"⚠️ 样本仅 {n}（<10），结果仅为提示，不据此下结论")

    # 状态分层（复用 review_triggers 的 market_state）
    from scripts.review_triggers import market_state

    def status_of(i):
        # market_state(closes, i) → 趋势/区间等
        return market_state(closes, i) if i < len(closes) else "?"

    seen = {c for e in bottoms for c in (e.get("bottom_cats") or [])}
    order = [c for c in CATEGORY_ORDER if c in seen] + sorted(seen - set(CATEGORY_ORDER))

    results = []
    print("\n| 因子 | 满足n | 不满n | 差异(pp) | bootstrap 95%CI | P(差>0) | 判定 |")
    print("|------|------|------|---------|----------------|---------|------|")
    for f in order:
        hit = [e["forward_return_20"] for e in bottoms if f in (e.get("bottom_cats") or [])]
        miss = [e["forward_return_20"] for e in bottoms if f not in (e.get("bottom_cats") or [])]
        mh = sum(hit) / len(hit) if hit else None
        mm = sum(miss) / len(miss) if miss else None
        diff = (mh - mm) * 100 if (mh is not None and mm is not None) else None
        judge = "—"
        ci_str = p_str = "—"
        if diff is not None and len(hit) >= 3 and len(miss) >= 3:
            (lo, hi), p_pos = bootstrap_significance(hit, miss)
            ci_str = f"[{lo*100:+.1f}, {hi*100:+.1f}]"
            p_str = f"{p_pos:.2f}"
            if lo > 0:
                judge = "✓ 显著为正（95%CI 不含 0）"
            elif hi < 0:
                judge = "✗ 显著为负"
            else:
                judge = "≈ 不显著（CI 含 0）"
        elif not miss:
            judge = "恒满足（定义 bug?）"
        print(f"| {f} | {len(hit)} | {len(miss)} | {diff if diff is None else f'{diff:+.1f}'} | "
              f"{ci_str} | {p_str} | {judge} |")
        results.append({"factor": f, "hit_n": len(hit), "miss_n": len(miss),
                        "diff_pp": diff, "ci": ci_str, "p_pos": p_str, "judge": judge})

    # 单因子显著结论 + 恒满足设计 bug 警告
    sig = [r for r in results if r["judge"].startswith("✓")]
    print()
    if sig:
        print(f"✓ {len(sig)} 个因子 bootstrap 显著（样本充分且95%CI不含0）："
              f"{', '.join(r['factor'] for r in sig)}")
        print("  → 该因子显著为正：重建评分卡有地基，可加权重（但仍需纯动量基线对照）")
    else:
        print("⚠️ 无因子 bootstrap 显著 → 这套技术因子在 A 股日线、这批标的上可能无效，"
              "重建评分卡是徒劳，应先考虑换因子池/时间框架")
    always = [r["factor"] for r in results if r["factor"] and r["miss_n"] == 0]
    if always:
        print(f"⚠️ 恒满足因子（不满足组空）：{', '.join(always)} ——这些是'新低/触底'类同步定义，".replace('——', '——21'))
        print()
        print(f"⚠️ 恒满足因子（不满足组空，无法做满足/不满对照）：{', '.join(always)}")
        print("  → '新低/触底'类同步定义在底部场景天然恒满足，属设计 bug 而非'零信息'；")
        print("    应重写为右侧确认信号（放量阳线/突破颈线/收回布林下轨）而非降级为门槛")

    # 状态分层：对每个因子按趋势/区间重算差异（验证状态混淆）
    print("\n===== 状态分层差异（市场状态 × 因子）=====")
    states_seen = sorted({status_of(e["index"]) for e in bottoms})
    print(f"状态分布：{states_seen}")
    for f in order:
        line_parts = []
        for st in states_seen:
            sub = [e for e in bottoms if status_of(e["index"]) == st]
            hit = [e["forward_return_20"] for e in sub if f in (e.get("bottom_cats") or [])]
            miss = [e["forward_return_20"] for e in sub if f not in (e.get("bottom_cats") or [])]
            if not hit or not miss:
                line_parts.append(f"{st}: n请={len(sub)} ✗ 单组空")
                continue
            d = (sum(hit) / len(hit) - sum(miss) / len(miss)) * 100
            line_parts.append(f"{st}: {d:+.1f}pp(h{len(hit)}/m{len(miss)})")
        print(f"{f}: {' | '.join(line_parts)}")

    if out_path:
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump({"symbol": symbol, "n_bottom": n, "rows": results},
                      fh, ensure_ascii=False, indent=2)
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
        print("用法: python3 scripts/momentum_significance.py <symbol> [--lb N] [--out f.json]")
        return
    momentum_significance(symbol, lookback=lookback, out_path=out_path)


if __name__ == "__main__":
    main()
