# -*- coding: utf-8 -*-
"""
bottom_enter 触发信号的时间分布诊断（比人工复核更快指向"调过滤 or 调阈值"岔路口）。

回答的核心问题：策略在下跌段是否仍频繁发做多信号？
  - 若是 → 加趋势过滤（ADX / 均线方向 / 市场状态门控），调打分阈值没用
  - 若信号稀少且分散在各状态 → 才是阈值/位置偏早偏晚问题

用法:
    python3 scripts/trigger_time_distribution.py 600519 300750 512880 588000
    python3 scripts/trigger_time_distribution.py 600519 --out report.md

对每个标的：
  - 重跑 TimingStrategy(min_score=3)，取所有 bottom_enter 触发事件
  - 按季度打点：每季度 bottom_enter 数、该季度前视收益（20 根）、段内漂移（是否下跌段）
  - 按 market_state 打点：趋势/区间/高波动下各发多少，下跌段占比
"""
import sys, os, json
from collections import defaultdict
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.review_triggers import load_bars, market_state


def _drift(closes, i, win=25):
    """触发点前后 win 根的价格漂移（post/pre - 1），<0 表示该段下跌中"""
    lo = max(0, i - win)
    hi = min(len(closes), i + win)
    seg = closes[lo:hi]
    if len(seg) < 20:
        return 0.0
    half = max(1, len(seg) // 2)
    pre = sum(seg[:half]) / half
    post = sum(seg[half:]) / (len(seg) - half)
    return (post / pre - 1.0) if pre else 0.0


def analyze(symbol):
    bars, source = load_bars(symbol)
    closes = [float(b.close) for b in bars]
    datetimes = [b.datetime for b in bars]

    from strategy.timing_strategy import TimingStrategy
    from engine.backtest_engine import BacktestEngine
    from portfolio.portfolio import Portfolio
    from risk.risk_manager import RiskManager, RiskConfig
    from risk.position_sizer import PercentSizer

    strat = TimingStrategy(min_score=3, direction_mode="both", lookback=60)
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

    bottom = [e for e in events if e["trigger_type"] == "bottom_enter"]

    # ---- 按季度 ----
    by_q = defaultdict(list)
    for e in bottom:
        dt = e.get("datetime") or datetimes[e["index"]]
        if isinstance(dt, str):
            dt = dt[:10]  # "YYYY-MM-DD HH:MM:SS" -> "YYYY-MM-DD"
            from datetime import datetime as _dt
            dt = _dt.strptime(dt, "%Y-%m-%d")
        q = f"{dt.year}-Q{(dt.month - 1) // 3 + 1}"
        by_q[q].append((e, _drift(closes, e["index"])))
    # 区间价格基准（每季度段终点，判断该季整体方向）
    quarter_price = defaultdict(list)
    for i, c in enumerate(closes):
        dt = datetimes[i]
        quarter_price[f"{dt.year}-Q{(dt.month - 1) // 3 + 1}"].append(c)

    q_rows = []
    for q in sorted(by_q):
        evs = by_q[q]
        seg_prices = quarter_price[q]
        seg_down = seg_prices[-1] < seg_prices[0] if len(seg_prices) > 1 else None
        n_down_seg = sum(1 for _, d in evs if d < 0)
        q_rows.append({"quarter": q, "n": len(evs),
                       "seg_dir": "跌" if seg_down else ("涨" if seg_down is False else "?"),
                       "n_in_downseg": n_down_seg})

    # ---- 按市场状态 ----及下跌段占比
    by_state = defaultdict(int)
    n_down = 0
    for e in bottom:
        st = market_state(closes, e["index"])
        by_state[st] += 1
        if _drift(closes, e["index"]) < 0:
            n_down += 1

    return {"symbol": symbol, "source": source, "n_bottom": len(bottom),
            "n_down_seg": n_down, "down_ratio": (n_down / len(bottom)) if bottom else 0.0,
            "by_state": dict(by_state), "by_quarter": q_rows}


def render_md(reports):
    L = []
    L.append("## 触发信号时间分布（bottom_enter 是否集中在下跌段）")
    L.append("")
    for r in reports:
        L.append(f"### {r['symbol']}（{r['source']}，bottom_enter={r['n_bottom']}）")
        L.append("")
        L.append(f"- 落在**下跌段**的做多信号：{r['n_down_seg']}/{r['n_bottom']} "
                 f"= {r['down_ratio']*100:.0f}%")
        L.append(f"- 按市场状态："
                 + "、".join(f"{k} {v}" for k, v in sorted(r["by_state"].items())))
        L.append("")
        qs = r["by_quarter"]
        if qs:
            L.append("| 季度 | bottom_enter 数 | 季度方向 | 其中下跌段信号 |")
            L.append("|------|---------------|---------|---------------|")
            for q in qs:
                L.append(f"| {q['quarter']} | {q['n']} | {q['seg_dir']} | {q['n_in_downseg']} |")
        else:
            L.append("（该标的本窗口无 bottom_enter）")
        L.append("")
    L.append("### 判定口径")
    L.append("")
    L.append("- **下跌段信号占比高（如 >50%）→ 加趋势过滤（ADX/均线/市场状态门控），"
             "调打分阈值无用**——阈值再严，信号仍落在下跌段。")
    L.append("- 信号稀少且各状态分散、位置偏早/偏晚 → 才是阈值/确认条件问题。")
    L.append("- 本脚本回答\"信号方向对不对\"，比 --interactive 人工复核（回答判定标准准不准）更根本，故优先级更高。")
    return "\n".join(L)


if __name__ == "__main__":
    out = None
    args = []
    i = 1
    while i < len(sys.argv):
        a = sys.argv[i]
        if a == "--out" and i + 1 < len(sys.argv):
            out = sys.argv[i + 1]; i += 2; continue
        if not a.startswith("--"):
            args.append(a)
        i += 1
    if not args:
        print(__doc__); sys.exit(0)
    reports = [analyze(s) for s in args]
    md = render_md(reports)
    if out:
        open(out, "w", encoding="utf-8").write(md)
        print(f"已存: {out}")
    else:
        print(md)
