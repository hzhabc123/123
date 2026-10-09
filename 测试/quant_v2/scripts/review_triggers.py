#!/usr/bin/env python3
"""
TimingStrategy 触发点人工验收辅助工具（path A 收紧版）

把"20 个触发点合理/不合理"升级为"失败模式归类"，产出该修哪里的清单：
  过早      信号出现后价格继续跌/涨（阈值偏高或超卖条件太激进）
  过晚      信号出现时价格已反转一段（阈值偏低或确认条件太重）
  假突破    突破后快速收回（缺收盘价/量能二次确认）
  趋势中段  单边趋势中的中继震荡被当成顶/底（缺 ADX/趋势过滤）
  执行被卡  位置合理但被风控/整手卡住（执行层问题，非信号问题）
  hit       位置合理（预期方向收益成立）

默认做规则引擎**预判（全自动）**；--interactive 逐点确认/改标。
输出：分布表 + 按市场状态（趋势/区间/高波动）分组，喂给路径 B 分层设计。

用法:
    python3 scripts/review_triggers.py 600519                  # 预判分布（默认）
    python3 scripts/review_triggers.py 600519 --interactive    # 逐点人工确认
    python3 scripts/review_triggers.py 600519 --out report.json
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ---- 失败模式常量 ----
HIT, EARLY, LATE, FAKE, TREND_SEG, BLOCKED = \
    "hit", "过早", "过晚", "假突破", "趋势中段", "执行被卡"
MODE_LABELS = {HIT: "位置合理(hit)", EARLY: "过早", LATE: "过晚",
               FAKE: "假突破", TREND_SEG: "趋势中段误判", BLOCKED: "执行被卡"}


def load_bars(symbol=None):
    """与 plot_timing_signals 一致：真实行情优先，否则合成"""
    if symbol:
        from datetime import date
        from data.akshare_source import AkshareDataSource
        src = AkshareDataSource()
        bars = src.fetch_daily_sorted(symbol, date(2023, 1, 1), date(2025, 1, 1))
        if bars and len(bars) > 120:
            return bars, f"真实行情 {symbol}"
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


def market_state(closes, i, win=25, up_thr=0.02, vol_thr=0.03):
    """触发点所在市场段标签：趋势/区间/高波动（事后诊断，标注用）"""
    lo = max(0, i - win)
    hi = min(len(closes), i + win)
    seg = closes[lo:hi]
    if len(seg) < 20:
        return "区间"
    half = max(1, len(seg) // 2)
    pre = sum(seg[:half]) / half
    post = sum(seg[half:]) / (len(seg) - half)
    drift = post / pre - 1.0
    import numpy as np
    a = np.array(seg)
    vol = float(np.std(np.diff(a) / a[:-1])) if len(a) > 1 else 0.0
    state = "高波动" if vol > vol_thr and abs(drift) < up_thr else \
            ("趋势" if abs(drift) >= up_thr else "区间")
    return state


def predict_mode(ev, closes, late_rise=0.06):
    """
    规则预判失败模式。

    orientation: 买点期望涨(+1)，卖点期望跌(-1)，signed 收益应>0 为对。
    """
    direction = ev["trigger_type"]
    orientation = 1 if direction == "bottom_enter" else -1
    f5 = ev.get("forward_return_5")
    f20 = ev.get("forward_return_20")
    if f5 is None or f20 is None:
        return HIT, "数据不足(尾部触发，跳过人工复核)"
    s5 = orientation * f5
    s20 = orientation * f20

    if s5 > 0 and s20 > 0:
        i = ev["index"]
        win = closes[max(0, i - 20):i]
        if win:
            low20 = min(win)
            rise = closes[i] / low20 - 1.0 if low20 > 0 else 0.0
            if rise > late_rise:
                return LATE, f"触发价已距前低{rise*100:.1f}%"
        return HIT, f"s5={s5*100:+.1f}% s20={s20*100:+.1f}%"
    if s5 <= 0 < s20:
        return EARLY, f"先逆{s5*100:+.1f}%后转正{s20*100:+.1f}%"
    if s5 > 0 >= s20:
        return FAKE, f"先对{s5*100:+.1f}%后收回{s20*100:+.1f}%"
    return TREND_SEG, f"s5={s5*100:+.1f}% s20={s20*100:+.1f}% 同向下跌"


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    interactive = "--interactive" in sys.argv
    out_path = None
    if "--out" in sys.argv:
        out_path = sys.argv[sys.argv.index("--out") + 1]
    symbol = args[0] if args else None

    from strategy.timing_strategy import TimingStrategy
    from engine.backtest_engine import BacktestEngine
    from portfolio.portfolio import Portfolio
    from risk.risk_manager import RiskManager, RiskConfig
    from risk.position_sizer import PercentSizer

    bars, source = load_bars(symbol)
    closes = [float(b.close) for b in bars]
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
    if not events:
        print("无触发事件"); return

    print(f"===== 触发点失败模式归类（{source}，{len(events)} 事件）=====")
    tname = {"bottom_enter": "底部做多", "top_exit": "顶部了结", "top_no_pos": "顶空仓"}
    results = []
    for n, e in enumerate(events):
        mode, note = predict_mode(e, closes)
        st = market_state(closes, e["index"])
        verdict = mode
        if interactive:
            print(f"\n[{n+1}/{len(events)}] {e['datetime']} | {tname[e['trigger_type']]} "
                  f"@{e['price_at_signal']:.2f} | 底分{e['bottom_score']} 顶分{e['top_score']} | 市场:{st}")
            f5, f10, f20 = (e.get(f"forward_return_{h}") for h in (5, 10, 20))
            print(f"  fwd5={f5*100:+.1f}% fwd10={f10*100:+.1f}% fwd20={f20*100:+.1f}%  预判[{MODE_LABELS[mode]}] {note}")
            vals = {k: str(i) for i, k in enumerate([HIT, EARLY, LATE, FAKE, TREND_SEG, BLOCKED])}
            ans = input(f"  确认或改标 [{HIT}(0)]: ").strip()
            if ans:
                for k, v in vals.items():
                    if ans in (v, k):
                        verdict = k; break
        results.append({**e, "market_state": st, "mode": verdict,
                        "mode_note": note, "source": source})

    from collections import Counter
    dist = Counter(r["mode"] for r in results)
    print("\n===== 失败模式分布 =====")
    hit_n = dist.get(HIT, 0)
    hit_rate = hit_n / len(results)
    for m, c in dist.most_common():
        print(f"  {MODE_LABELS[m]:<16} {c:>3}  ({c/len(results)*100:4.1f}%)")
    print(f"  命中率(hit占比): {hit_rate*100:.1f}%  ({hit_n}/{len(results)})")

    print("\n===== 按市场状态分组 =====")
    by_state = {}
    for r in results:
        by_state.setdefault(r["market_state"], []).append(r["mode"])
    for st, modes in by_state.items():
        d = Counter(modes)
        h = d.get(HIT, 0)
        print(f"  {st:<5} n={len(modes):>2}  hit={h}/{len(modes)} "
              f"({h/len(modes)*100:.0f}%)  " +
              "  ".join(f"{MODE_LABELS[m][:4]}={c}" for m, c in d.most_common()[:4]))

    if out_path:
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, default=str, indent=2)
        print(f"\n已存: {out_path}")


if __name__ == "__main__":
    main()
