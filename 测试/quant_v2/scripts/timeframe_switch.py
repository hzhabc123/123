#!/usr/bin/env python3
"""
周线框架验证（timeframe_switch）：同一因子逻辑，日线/周线双跑

背景：扩样本 v2 已封顶（纯动量 vs固定低仓位净超额 -9.64pp、评分卡 -19.10pp，两路径都不成立）。
但四标的共享同一段 2023–2024 宏观环境，独立状态样本只有 1 个；日线无效是"时间尺度错配"还是
"因子无信息"尚未区分。换因子池/换框架之前，先做最便宜的检验：只把日线聚合到周线、同一逻辑重跑。

回答：
  - 周线信号数 vs 日线（是否周线更稳定/更少噪声）
  - 周线 fwd20 vs 日线（同一根信号窗口、不同周期下收益质量）
  - 周线 vs固定低仓位净超额 vs 日线（周期错配是否改变"净额负"结论）

关键口径：
  - 同一 lookback 根数（默认 30 根）——策略逻辑只按"根"采样，不关心时间单位；
    这正是检验"因子无信息 vs 周期错配"的正确方式：同样 30 根窗口，每根换成周K。
  - lookback 与周期无关（TimingStrategy 按 closes 数组长度/根数取窗口），故可直接喂周线 bars。
  - 标的数 < 10 时**只报净超额均值 + 区间**，不报"X/N 跑赢"（用户裁定：计数不是统计量）。

用法:
    python3 scripts/timeframe_switch.py 600519 300750 512880 588000
    python3 scripts/timeframe_switch.py --symbols 600519,300750 --lb 30 --out outputs/timeframe_switch.json
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from collections import defaultdict
from datetime import datetime

# 复用 batch_expand_sample 的对照结构（不新建框架）
from scripts.batch_expand_sample import (
    _load, _run_engine, _avg_exposure,
    _hold_return, _random_flat_dist, _buy_hold_return, classify_market_state,
)
from scripts.pure_momentum_backtest import _weights


def aggregate_weekly(daily_bars):
    """把日线 bars 聚合成周线 bars（按 ISO 周：周一到周日为同一周）。
    聚合口径：open=首日open, high=周内max, low=周内min, close=末日close, volume=周内sum。
    datetime 用周内最后一个交易日。返回 List[Bar] 升序。"""
    from data.bar import Bar
    groups = defaultdict(list)
    for b in sorted(daily_bars, key=lambda x: x.datetime):
        iso = b.datetime.isocalendar()
        key = (iso[0], iso[1])          # (年, ISO周) 作分组键
        groups[key].append(b)
    weekly = []
    for key in sorted(groups):
        g = sorted(groups[key], key=lambda x: x.datetime)
        weekly.append(Bar(
            symbol=g[0].symbol,
            datetime=g[-1].datetime,                          # 周内最后交易日
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
    """在一套指定周期 bars 上跑 策略+两对照，返回行记录（复用 batch_expand 的对照结构）。"""
    closes = [b.close for b in bars]
    _, m, trades, engine = _run_engine(bars, min_score, weights, lookback)
    strat_ret = m.total_return
    exposure = _avg_exposure(engine)
    flat_ratio = 1.0 - exposure

    hold_ret = _hold_return(closes, exposure)               # 固定低仓位
    rand_dist = _random_flat_dist(closes, flat_ratio)       # 随机空仓 1000 次分布
    rand_mean = rand_dist["mean"]
    bh_ret = _buy_hold_return(closes)                       # 买入持有

    # 信号数 + fwd20（来自策略触发事件，附 annotate=True 回填）
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
    """标的<10 时的净超额汇总：只给均值 + 区间（跨标的 5-95 经验分位），不报 X/N。"""
    if not excess_list:
        return None
    n = len(excess_list)
    vals = sorted(excess_list)
    lo = vals[max(0, int(0.05 * n) - 1)]
    hi = vals[min(n - 1, int(0.95 * n))]
    return {"n": n, "mean_pp": sum(vals) / n * 100,
            "lo_pp": lo * 100, "hi_pp": hi * 100}


def timeframe_switch(symbols, mode="both", lookback=30, out_path=None):
    """对每标的拉日线 -> 聚合周线 —— 两周期各跑一遍，输出对照。"""
    print(f"===== 周线框架验证（mode={mode}，lb={lookback}）=====")
    print(f"标的数={len(symbols)}（<10 → 稳定用量净超额均值+区间，不报 X/N）")
    rows = []
    daily_net, weekly_net = [], []
    for sym in symbols:
        daily_bars, _, _ = _load(sym)
        weekly_bars = aggregate_weekly(daily_bars)
        eff_weights = _weights(keep_momentum=True) if mode == "momentum" else None
        _min_score = 1 if mode == "momentum" else 3
        try:
            d = run_timeframe(daily_bars, _min_score, eff_weights, lookback, label="日线")
            w = run_timeframe(weekly_bars, _min_score, eff_weights, lookback, label="周线")
        except Exception as e:
            print(f"  {sym}: 失败 {e}")
            continue
        rows.append({"symbol": sym, "daily": d, "weekly": w})
        daily_net.append(d["excess_vs_holdlow"])
        weekly_net.append(w["excess_vs_holdlow"])

        for r in (d, w):
            rd = r["rand_flat_result"]
            f20 = f"{r['fwd20_mean']*100:+.2f}%" if r["fwd20_mean"] is not None else "—"
            print(f"| {sym} {r['timeframe']} | {r['bars']:4d}根 | {r['market_state']} | "
                  f"信号{r['bottom_signals']:3d} | fwd20 {f20} | 策略{r['strat_return']*100:+6.2f}% | "
                  f"随机均{rd['mean']*100:+6.2f}%[5-95:{rd['lo']*100:+.1f}~{rd['hi']*100:+.1f}] | "
                  f"固定{r['hold_low_return']*100:+6.2f}% | 买入{r['buy_hold_return']*100:+6.2f}% | "
                  f"vs固定{r['excess_vs_holdlow']*100:+6.2f}pp |")

    print("\n===== 归纳（标的<10 → 只报净超额均值+区间，不报 X/N）=====")
    d_stat = _net_excess_stat(daily_net)
    w_stat = _net_excess_stat(weekly_net)
    # 信号总数门槛：周线信号过少时均值会被个别信号牵引，只作提示不定论
    d_sig = sum(r["daily"]["bottom_signals"] for r in rows) if rows else 0
    w_sig = sum(r["weekly"]["bottom_signals"] for r in rows) if rows else 0
    w_reliable = w_sig >= 10
    if d_stat and w_stat:
        print(f"  日线 vs固定低仓位 净超额：均值 {d_stat['mean_pp']:+.2f}pp，"
              f"跨标的区间 [{d_stat['lo_pp']:+.2f}, {d_stat['hi_pp']:+.2f}]pp（n={d_stat['n']}）")
        print(f"  周线 vs固定低仓位 净超额：均值 {w_stat['mean_pp']:+.2f}pp，"
              f"跨标的区间 [{w_stat['lo_pp']:+.2f}, {w_stat['hi_pp']:+.2f}]pp（n={w_stat['n']}）")
        if not w_reliable:
            print(f"  ⚠️ 周线信号总数仅 {w_sig}（<10），均值极易被个别信号牵引，"
                  f"以下周期错配判定只作方向提示，**不作结论**。须扩标的/扩样本后复核。")
        drift = w_stat["mean_pp"] - d_stat["mean_pp"]
        verdc = ("日线封顶可能=周期错配，保留因子池改框架（待复核）"
                 if w_stat["mean_pp"] > 0 else
                 "周期错配假说不成立，因子池本身无信息，可换因子池（待复核）")
        print(f"  周线相对日线净超额漂移 {drift:+.2f}pp  → {verdc}")
    else:
        print("  无可用净超额数据")

    # 信号数 + fwd20 对照（判断噪声尺度）
    if rows:
        d_f = [r["daily"]["fwd20_mean"] for r in rows if r["daily"]["fwd20_mean"] is not None]
        w_f = [r["weekly"]["fwd20_mean"] for r in rows if r["weekly"]["fwd20_mean"] is not None]
        print(f"  bottom_enter 信号总数：日线 {d_sig} vs 周线 {w_sig}")
        if d_f:
            print(f"  日线 fwd20 均值（跨标的平均）：{sum(d_f)/len(d_f)*100:+.2f}%")
        if w_f:
            print(f"  周线 fwd20 均值（跨标的平均）：{sum(w_f)/len(w_f)*100:+.2f}%")

    if out_path:
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump({"mode": mode, "lookback": lookback,
                       "daily_net": d_stat, "weekly_net": w_stat, "rows": rows},
                      fh, ensure_ascii=False, indent=2)
        print(f"  已写出: {out_path}")


def main():
    argv = sys.argv[1:]
    skip_next = False
    symbols = []
    flags = ("--lb", "--out", "--mode", "--symbols")
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
    mode = "both"
    if "--mode" in argv and argv[argv.index("--mode") + 1] == "momentum":
        mode = "momentum"
    if "--symbols" in argv:
        symbols = [s.strip() for s in argv[argv.index("--symbols") + 1].split(",") if s.strip()]
    if not symbols:
        print("用法: python3 scripts/timeframe_switch.py <symbols...> [--mode momentum|both] "
              "[--lb N] [--out f.json]")
        return
    timeframe_switch(symbols, mode=mode, lookback=lookback, out_path=out_path)


if __name__ == "__main__":
    main()