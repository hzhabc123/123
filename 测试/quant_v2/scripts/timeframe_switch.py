#!/usr/bin/env python3
"""
周线框架验证 v2（timeframe_switch）：同一因子逻辑，日线/周线双跑 + 按年份分层

背景：v1（2026-10-17）只跑 2023–2024·4 标的，周线信号极端稀疏（momentum 8 / scorecard 4），
样本不足无法定论。用户裁定修正第 2 步（扩时间跨度）设计，关键修正：
  - **环境混淆必须分层**：2019–2024 跨 牛(2019-20)/结构市(2021)/熊(2022)/震荡(2023-24)，
    六年合成一个均值没有解释力。改为 **按年份分层输出矩阵**（2019/2020/…/2024 各一行），
    看"净超额是否随年份/状态变化"，**不汇总总体均值**。
  - **周线只跑纯动量**（评分卡周线信号更稀，直接放弃，不扩）。
  - **周线硬门槛 ≥50 信号才做统计推断**，不足就标"样本不足"。
  - **复权统一后复权 hfq**（前复权跨 6 年随时间漂移）。
  - 先小规模试跑（3–4 只 × 2019–2024 纯动量周线）看信号量到不到阈值，再决定扩标的。

用法:
    # v2 默认：2019-2024、后复权、纯动量周线、按年份分层
    python3 scripts/timeframe_switch.py 600519 300750 512880 588000 --yearly-breakdown --min-signals 50
    # 只跑信号量试算（小规模、快速看周线到不到 50）
    python3 scripts/timeframe_switch.py 600519 300750 512880 588000 --min-signals 50
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from collections import defaultdict
from datetime import datetime, date

# 复用 batch_expand_sample 的对照结构（不新建框架）
from scripts.batch_expand_sample import (
    _avg_exposure, _hold_return, _random_flat_dist, _buy_hold_return,
    classify_market_state,
)
from scripts.pure_momentum_backtest import _weights

DEFAULT_START = date(2019, 1, 1)
DEFAULT_END   = date(2025, 1, 1)
DEFAULT_ADJUST = "hfq"   # 后复权（跨 6 年前复权会漂移）
DEFAULT_MIN_SIGNALS = 50  # 周线硬门槛：总信号数 ≥ 此值才做统计推断


def _run_engine_hfq(bars, min_score, weights, lookback=30):
    """跑 TimingStrategy，账户规模与风控适配 hfq 高价股。
    背景：hfq 后复权把价格放大到 7928–19782 元（如茅台）。若用现实小资金(50万)，
    风控按权益比例(上限40%)拦截会把 158–331% 单笔比例的建仓全部拒掉 → 高价标的全空仓、
    净超额恒 0（伪结论）。本函数把初始资金放大到 2000 万（覆盖茅台 1 手~200万 × 30% 仓位）、
    单笔金额上限放大到 1000 万、单笔比例上限 0.4，保证"信号→仓位→净超额"不被资金尺度
    天花板扭曲；收益率口径与资金规模无关（同比例仓位收益一致）。
    返回与 batch_expand._run_engine 相同的 (summary, metrics, trades, engine)。"""
    from strategy.timing_strategy import TimingStrategy
    from engine.backtest_engine import BacktestEngine
    from portfolio.portfolio import Portfolio
    from risk.risk_manager import RiskManager, RiskConfig
    from risk.position_sizer import PercentSizer
    from performance.analyzer import PerformanceAnalyzer

    strat = TimingStrategy(min_score=min_score, direction_mode="both",
                           lookback=lookback,
                           weights=(weights or {}) if weights is not None else None)
    portfolio = Portfolio(initial_cash=20_000_000.0)   # 与 hfq 价格尺度匹配
    rc = RiskConfig()
    rc.max_single_trade_amount = 10_000_000.0   # 覆盖 hfq 高价单笔
    rc.max_single_trade_ratio = 0.4
    rc.max_position_ratio = 0.8
    engine = BacktestEngine(strategy=strat, portfolio=portfolio,
                            risk_manager=RiskManager(rc),
                            position_sizer=PercentSizer(percent=0.3, min_amount=1000.0),
                            symbol=strat.name, lookback=500)
    summary = engine.run(bars)
    m = PerformanceAnalyzer(engine.get_equity_curve(), portfolio.trades).compute()
    return summary, m, portfolio.trades, engine


def _load_range(symbol, start=DEFAULT_START, end=DEFAULT_END, adjust=DEFAULT_ADJUST):
    """拉指定时间范围 + 指定复权方式的日线（不依赖 load_bars 的硬编码 2023-25/qfq）。
    失败或数据不足返回 None（由调用方决定降级）。"""
    from data.akshare_source import AkshareDataSource
    from utils.compat import patch_imp_importer
    patch_imp_importer()
    try:
        src = AkshareDataSource()
        bars = src.fetch_daily_sorted(symbol, start, end, adjust=adjust)
        if not bars or len(bars) < 120:
            return None
        return bars
    except Exception:
        return None


def aggregate_weekly(daily_bars):
    """把日线 bars 聚合成周线 bars（按 ISO 周：周一到周日为同一周）。"""
    from data.bar import Bar
    groups = defaultdict(list)
    for b in sorted(daily_bars, key=lambda x: x.datetime):
        iso = b.datetime.isocalendar()
        groups[(iso[0], iso[1])].append(b)
    weekly = []
    for key in sorted(groups):
        g = sorted(groups[key], key=lambda x: x.datetime)
        weekly.append(Bar(
            symbol=g[0].symbol,
            datetime=g[-1].datetime,
            open=g[0].open,
            high=max(x.high for x in g),
            low=min(x.low for x in g),
            close=g[-1].close,
            volume=sum(x.volume for x in g),
            amount=sum(x.amount for x in g),
            flags=g[-1].flags,
            adj_factor=g[-1].adj_factor,
            open_interest=g[-1].open_interest,
        ))
    return weekly


def run_timeframe(bars, min_score, weights, lookback=30, label=""):
    """在一套指定周期 bars 上跑 策略+两对照，返回行记录。"""
    closes = [b.close for b in bars]
    _, m, trades, engine = _run_engine_hfq(bars, min_score, weights, lookback)
    strat_ret = m.total_return
    exposure = _avg_exposure(engine)
    flat_ratio = 1.0 - exposure

    hold_ret = _hold_return(closes, exposure)
    rand_dist = _random_flat_dist(closes, flat_ratio)
    rand_mean = rand_dist["mean"]
    bh_ret = _buy_hold_return(closes)

    events = engine.strategy.get_trigger_events(annotate=True)
    bottoms = [e for e in events if e["trigger_type"] == "bottom_enter"
               and e.get("forward_return_20") is not None]
    fwd20 = [e["forward_return_20"] for e in bottoms]
    fwd20_mean = sum(fwd20) / len(fwd20) if fwd20 else None

    period = f"{bars[0].datetime:%Y-%m-%d}~{bars[-1].datetime:%Y-%m-%d}"
    mkt = classify_market_state(bh_ret)
    return {
        "timeframe": label, "bars": len(closes), "period": period,
        "market_state": mkt, "trades": len(trades), "win_rate": m.win_rate,
        "bottom_signals": len(bottoms), "fwd20_mean": fwd20_mean,
        "avg_exposure": exposure, "flat_ratio": flat_ratio,
        "strat_return": strat_ret, "hold_low_return": hold_ret,
        "rand_flat_result": rand_dist, "buy_hold_return": bh_ret,
        "rand_flat_return": rand_mean,
        "excess_vs_rand": strat_ret - rand_mean,
        "excess_vs_holdlow": strat_ret - hold_ret,
        "excess_vs_buyhold": strat_ret - bh_ret,
    }


def _net_excess_stat(excess_list):
    """标的<10 净超额汇总：只给 均值+区间（5-95 经验分位），不报 X/N。
    计数不是统计量——标的样本太少时任何 X/N 都不构成结论，只给分布口径。"""
    if not excess_list:
        return None
    n = len(excess_list)
    vals = sorted(excess_list)
    lo = vals[max(0, int(0.05 * n) - 1)]
    hi = vals[min(n - 1, int(0.95 * n))]
    return {"n": n, "mean_pp": sum(vals) / n * 100,
            "lo_pp": lo * 100, "hi_pp": hi * 100}


def _yearly_slices(daily_bars):
    """按年份切分日线 -> {year: [bars]}。每段独立跑（环境分层）。"""
    slices = defaultdict(list)
    for b in daily_bars:
        slices[b.datetime.year].append(b)
    return {y: sorted(v, key=lambda x: x.datetime) for y, v in slices.items()}


def _yearly_breakdown_from_engine(engine, bars, min_score, weights, lookback):
    """全量运行引擎后按年份归因：
    - 信号：从触发事件按 datetime.year 归档计数（不预切分，保留跨年空仓→触底→持仓上下文）
    - 净超额(vs固定低仓位)：按 equity_curve 年份切片，每年 = 该年策略收益 − 该年平均持仓×该年基准首尾收益
    """
    curve = engine.get_equity_curve()
    close_by_date = {b.datetime.date(): b.close for b in bars}
    events = engine.strategy.get_trigger_events(annotate=True)
    bottom_events = [e for e in events if e["trigger_type"] == "bottom_enter"]

    by_year = defaultdict(lambda: {"strat_ret": None, "exposure": 0.0, "n_pts": 0,
                                    "base_first": None, "base_last": None, "signals": 0,
                                    "hold_ret": None, "excess": None})
    for ev in bottom_events:
        y = ev["datetime"].year
        by_year[y]["signals"] += 1

    # 按年分 equity 与基准收盘
    for pt in curve:
        d = pt.get("date") or pt.get("datetime")
        if hasattr(d, "date"):
            d = d.date()
        y = d.year
        eq = pt.get("equity") or 0.0
        mv = pt.get("market_value") or 0.0
        ratio = mv / eq if eq > 0 else 0.0
        base_c = close_by_date.get(d)
        row = by_year[y]
        row["n_pts"] += 1
        row["exposure"] += ratio
        if row["base_first"] is None:
            row["base_first"] = base_c
        row["base_last"] = base_c
        if row["strat_ret"] is None:
            row["strat_ret"] = eq
        row["strat_ret"] = eq  # 保留该年末权益（用于算年收益）

    out = []
    for y in sorted(by_year):
        row = by_year[y]
        if row["n_pts"] < 2 or row["strat_ret"] is None or row["base_first"] is None:
            continue
        # 首位权益：从 curve 取该年首末
        yr_curve = [p for p in curve if (p.get("date") or p.get("datetime")).year == y]
        if len(yr_curve) < 2:
            continue
        eq_first = yr_curve[0]["equity"]; eq_last = yr_curve[-1]["equity"]
        strat_ret = eq_last / eq_first - 1.0 if eq_first else 0.0
        exp = row["exposure"] / row["n_pts"]
        base_ret = row["base_last"] / row["base_first"] - 1.0 if row["base_first"] else 0.0
        hold_ret = exp * base_ret
        out.append({"year": y, "signals": row["signals"],
                    "strat_return": strat_ret, "hold_low_return": hold_ret,
                    "excess_vs_holdlow": strat_ret - hold_ret,
                    "avg_exposure": exp, "base_return": base_ret})
    return out


def run_symbol(sym, mode, lookback, start, end, adjust, yearly):
    """对单一标的：拉日线 -> 聚合周线 -> 各自全量运行引擎（保留跨年上下文）。
    日线按 mode 跑对照；周线只跑纯动量（用户裁定：评分卡周线信号太稀放弃）。
    yearly=True 时按事件年份归档信号 + 按 equity 年份切片算净超额，不预切分数据。"""
    daily = _load_range(sym, start, end, adjust)
    if daily is None:
        # 真实数据不可用（含 SYN 测试标的）：回退到合成行情（仅冒烟/测试语义）
        from scripts.momentum_significance import load_bars
        daily, _src = load_bars(sym)
        if daily is None:
            return {"symbol": sym, "error": "数据不足(<120根)"}
    res = {"symbol": sym}
    # 日线全量
    eff_weights = _weights(keep_momentum=True) if mode == "momentum" else None
    _ms = 1 if mode == "momentum" else 3
    d_row, _, _, d_eng = _run_engine_hfq(daily, _ms, eff_weights, lookback)
    d = run_timeframe(daily, _ms, eff_weights, lookback, label="日线")
    res["daily"] = d
    # 周线：只跑纯动量（全量聚合，保留跨年上下文）
    weekly = aggregate_weekly(daily)
    w_row, _, _, w_eng = _run_engine_hfq(weekly, 1, _weights(keep_momentum=True), lookback)
    w = run_timeframe(weekly, 1, _weights(keep_momentum=True), lookback, label="周线")
    res["weekly"] = w
    res["weekly_bottom_signals"] = w["bottom_signals"]
    if yearly:
        res["weekly_yearly"] = _yearly_breakdown_from_engine(
            w_eng, weekly, 1, _weights(keep_momentum=True), lookback)
    return res


def timeframe_switch(symbols, mode="momentum", lookback=30, out_path=None,
                     start=DEFAULT_START, end=DEFAULT_END, adjust=DEFAULT_ADJUST,
                     yearly_breakdown=False, min_signals=DEFAULT_MIN_SIGNALS):
    """标注：周线只跑纯动量，是否按年份分层。"""
    # 周线只跑纯动量：强制 mode 语义为 momentum 用于周线
    print(f"===== 周线框架验证 v2（周线=纯动量 only，lb={lookback}，复权={adjust}）=====")
    print(f"标的数={len(symbols)}（<10 → 只报净超额均值+区间，不报 X/N）")
    print(f"时间范围 {start}~{end}，按年份分层={yearly_breakdown}，周线门槛 ≥{min_signals} 信号才推断")
    rows = []
    for sym in symbols:
        r = run_symbol(sym, mode, lookback, start, end, adjust, yearly_breakdown)
        rows.append(r)
        if "error" in r:
            print(f"  {r['symbol']}: {r['error']}")
            continue
        wsig = r["weekly_bottom_signals"]
        tag = "✅ 门槛达标" if wsig >= min_signals else "⚠️ 样本不足"
        print(f"| {r['symbol']} 日线信号{r['daily']['bottom_signals']:3d} "
              f"vs固定{r['daily']['excess_vs_holdlow']*100:+6.2f}pp | "
              f"周线信号{wsig:3d} {tag} |")

    # 按年份分层矩阵
    if yearly_breakdown and rows:
        print("\n===== 年份×标的 矩阵（周线=纯动量，全量运行后按年份归因，不汇总总体均值）=====")
        all_years = set()
        for r in rows:
            if "error" in r:
                continue
            for y in r.get("weekly_yearly", []):
                all_years.add(y["year"])
        years = sorted(all_years)
        hdr = "标的".ljust(8) + "".join(f"{y:>10}" for y in years)
        print(hdr)
        for r in rows:
            if "error" in r:
                continue
            line = r["symbol"].ljust(8)
            for y in years:
                cell = "—"
                for yy in r.get("weekly_yearly", []):
                    if yy["year"] == y:
                        cell = f"{yy['excess_vs_holdlow']*100:+5.1f}pp({yy['signals']})"
                line += f"{cell:>12}"
            print(line)
        # 年份信号量汇总（判断是否到门槛）
        yearly_sig = defaultdict(int)
        for r in rows:
            if "error" in r:
                continue
            for y in r.get("weekly_yearly", []):
                yearly_sig[y["year"]] += y["signals"]
        print("\n各年份周线底信号总数：")
        for y in years:
            s = yearly_sig[y]
            print(f"  {y}: {s} 个 {'✅' if s>=min_signals else '⚠️'}")
        tot = sum(yearly_sig.values())
        print(f"\n周线底信号合计 {tot}（门槛 {min_signals}）→ {'达标，可推断' if tot>=min_signals else '⚠️ 样本不足，不推断'}")

    # 全量模式（非 yearly）仍给归纳
    elif rows:
        w_sig = sum(r.get("weekly_bottom_signals", 0) for r in rows)
        w_fit = w_sig >= min_signals
        print(f"\n周线底信号合计 {w_sig}（门槛 {min_signals}）→ "
              f"{'达标，可推断' if w_fit else '⚠️ 样本不足，不推断（须先扩标的再扩时间，别一次性全量跑）'}")
        if w_fit:
            w_net = [r["weekly"]["excess_vs_holdlow"] for r in rows if "weekly" in r]
            if w_net:
                mv = sum(w_net) / len(w_net) * 100
                print(f"周线净超额均值 {mv:+.2f}pp（仅当达标时才有推断意义）")

    if out_path:
        payload = {"mode": mode, "lookback": lookback, "adjust": adjust,
                   "start": str(start), "end": str(end),
                   "yearly_breakdown": yearly_breakdown, "min_signals": min_signals,
                   "rows": rows}
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
        print(f"\n已写出: {out_path}")


def main():
    argv = sys.argv[1:]
    skip_next = False
    symbols = []
    flags = ("--lb", "--out", "--mode", "--symbols", "--start", "--end", "--adjust",
             "--min-signals")
    for i, a in enumerate(argv):
        if skip_next:
            skip_next = False
            continue
        if a in flags:
            skip_next = True
            continue
        if a.startswith("--"):
            continue
        symbols.append(a)
    lookback = 30
    if "--lb" in argv:
        lookback = int(argv[argv.index("--lb") + 1])
    out_path = None
    if "--out" in argv:
        out_path = argv[argv.index("--out") + 1]
    mode = "momentum"
    if "--mode" in argv and argv[argv.index("--mode") + 1] in ("momentum", "both"):
        mode = argv[argv.index("--mode") + 1]
    start = DEFAULT_START
    if "--start" in argv:
        start = datetime.strptime(argv[argv.index("--start") + 1], "%Y-%m-%d").date()
    end = DEFAULT_END
    if "--end" in argv:
        end = datetime.strptime(argv[argv.index("--end") + 1], "%Y-%m-%d").date()
    adjust = DEFAULT_ADJUST
    if "--adjust" in argv:
        adjust = argv[argv.index("--adjust") + 1]
    min_signals = DEFAULT_MIN_SIGNALS
    if "--min-signals" in argv:
        min_signals = int(argv[argv.index("--min-signals") + 1])
    yearly = "--yearly-breakdown" in argv
    if "--symbols" in argv:
        symbols = [s.strip() for s in argv[argv.index("--symbols") + 1].split(",") if s.strip()]
    if not symbols:
        print("用法: python3 scripts/timeframe_switch.py <symbols...> "
              "[--mode momentum|both] [--lb N] [--start YYYY-MM-DD] [--end YYYY-MM-DD] "
              "[--adjust qfq|hfq] [--yearly-breakdown] [--min-signals N] [--out f.json]")
        return
    timeframe_switch(symbols, mode=mode, lookback=lookback, out_path=out_path,
                     start=start, end=end, adjust=adjust,
                     yearly_breakdown=yearly, min_signals=min_signals)


if __name__ == "__main__":
    main()