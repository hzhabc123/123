#!/usr/bin/env python3
"""
动量基线显著性核查（补 +2.03% 缺失的两个数字 + 触发定义澄清）

上一轮 pure_momentum_backtest 报了纯动量 fwd20=+2.03%，但缺三个关键对照，结论不可用：

  缺1：离散度 —— 31 个信号，fwd20 均值 +2.03%。若标准差 8% → 标准误≈1.4% → t≈1.4 不显著；
       若标准差 4% → t≈2.8 显著。只报均值不报 SD/SEM，无法判断是不是噪声。
  缺2：同期全样本基准 —— 纯动量 31 信号 vs 全因子 48 信号不是同一批 bar。要说明"纯动量更好"，
       必须对比同期茅台全部 bar 的 fwd20 均值（无条件基准）：若基准 +1.5%，+2.03% 只赢 0.5pp，
       只是选择偏差；若基准 −1%，才是真赢。
  缺3：触发定义歧义 —— 纯动量 = weights(仅动量1.0其余0) + min_score=1 → "只要动量满足就触发，
       总分不设门槛"。这不是"48 里只保留动量满足的 10 个"，而是阈值机制变了（min_score 3→1）
       的全新信号集，与 48 对比不公平。本脚本额外跑"48 信号里仅保留动量满足者"的真子集对照。

输出：
  1. 纯动量 31 信号：fwd20 均值/SD/SEM/t 值/bootstrap 95%CI，判定 +2.03% 显著性
  2. 同期全样本无条件基准：策略信号时间区间内茅台所有 bar 的 fwd20 均值 + 差异 significance
  3. 触发定义对照：A) 纯动量(min_score=1)  B) 现有48信号里仅保持动量满足的真子集（min_score=3）
     → 澄清 31 vs 48 是"新阈值信号集"还是"真子集"，+2.03% 属于哪种

用法:
    python3 scripts/momentum_baseline_check.py 600519
    python3 scripts/momentum_baseline_check.py 600519 --out outputs/momentum_baseline_600519.json
"""
import sys, os, json, random, math
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.momentum_significance import load_bars, bootstrap_diff


def _run_full(symbol, lookback=30):
    """跑引擎，返回全部 bottom_enter 事件 + 完整 closes + 数据源"""
    from strategy.timing_strategy import TimingStrategy
    from engine.backtest_engine import BacktestEngine
    from portfolio.portfolio import Portfolio
    from risk.risk_manager import RiskManager, RiskConfig
    from risk.position_sizer import PercentSizer
    import numpy as np

    bars, source = load_bars(symbol)
    strat = TimingStrategy(min_score=3, direction_mode="both", lookback=lookback)
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
    closes = np.array(list(strat.closes), dtype=float)
    return bottoms, closes, source


def _stats(f20):
    """均值/SD/SEM/t 统计；空数组返回占位 dict，单样本 t 置 0（不显著）"""
    n = len(f20)
    if n == 0:
        return {"n": 0, "mean": 0.0, "sd": 0.0, "sem": 0.0, "t": 0.0}
    mean = sum(f20) / n
    sd = math.sqrt(sum((x - mean) ** 2 for x in f20) / (n - 1)) if n > 1 else 0.0
    sem = sd / math.sqrt(n)
    t = mean / sem if sem > 0 else 0.0
    return {"n": n, "mean": mean, "sd": sd, "sem": sem, "t": t}


def momentum_baseline_check(symbol, lookback=30, out_path=None):
    # 全因子引擎（min_score=3）拿到全部48信号 + closes
    full, closes, source = _run_full(symbol, lookback)
    # 纯动量引擎（min_score=1, 仅动量）
    from scripts.pure_momentum_backtest import _weights, _run
    pure, _ = _run(symbol, 1, _weights(keep_momentum=True), lookback)

    f20_full = [e["forward_return_20"] for e in full]
    f20_pure = [e["forward_return_20"] for e in pure]

    print(f"===== 动量基线显著性核查（{source}，lb={lookback}）=====")

    # ---- 1) 纯动量 31 信号离散度/显著性 ----
    print("\n[1] 纯动量信号 fwd20 显著性")
    st = _stats(f20_pure)
    print(f"  n={st['n']}  mean={st['mean']*100:+.2f}%  SD={st['sd']*100:.2f}%  "
          f"SEM={st['sem']*100:.2f}%  t={st['t']:.2f}")
    if st['n'] >= 10:
        _, (lo, hi), p_pos = bootstrap_diff(f20_pure, [0.0] * st["n"], n_bs=2000)
        print(f"  bootstrap 95%CI(mean vs 0)=[{lo*100:+.2f}, {hi*100:+.2f}]  "
              f"P(mean>0)={p_pos:.2f}")
        sig = "显著 >0" if lo > 0 else "不显著（CI 含 0）"
    else:
        sig = f"样本仅 {st['n']}，不判显著性"
    print(f"  → +2.03% 显著性判定：{sig}")

    # ---- 2) 同期全样本无条件基准 ----
    print("\n[2] 同期全样本无条件基准（同时间段茅台所有 bar 的 fwd20）")
    if full:
        i0 = min(e["index"] for e in full)
        i1 = max(e["index"] for e in pure) if pure else max(e["index"] for e in full)
    else:
        i0, i1 = 0, len(closes) - 1
    # 全区间(可算 fwd20 的所有 bar) 无条件基准
    all_fwd = []
    c = closes
    for i in range(len(c) - 20):
        all_fwd.append(c[i + 20] / c[i] - 1.0)
    # 信号时间区间内的无条件基准（更严格，控制时间选择偏差）
    span_fwd = all_fwd[i0:i1 + 1] if i1 < len(all_fwd) else all_fwd[i0:]
    ast = _stats(span_fwd)
    pst = _stats(f20_pure)
    print(f"  信号时间区间: bar[{i0}:{i1}+1]，共 {len(span_fwd)} 根 bar")
    print(f"  区间无条件基准: mean={ast['mean']*100:+.2f}%  SD={ast['sd']*100:.2f}%  "
          f"n={ast['n']}")
    if pst and ast and ast['n'] >= 10 and pst['n'] >= 10:
        _, (dlo, dhi), d_p = bootstrap_diff(f20_pure, span_fwd, n_bs=2000)
        diff = (pst['mean'] - ast['mean']) * 100
        print(f"  纯动量 − 无条件基准 = {diff:+.2f}pp  "
              f"bootstrap CI=[{dlo*100:+.2f}, {dhi*100:+.2f}]  P(>0)={d_p:.2f}")
        print(f"  → 若 CI 不含 0：+2.03% 是真赢（不是选择偏差）；否则不显著")
    else:
        diff = (pst['mean'] - ast['mean']) * 100 if pst and ast else None
        print(f"  纯动量 − 无条件基准 = {diff:+.2f}pp（样本不足，参考）" if diff is not None
              else "  样本不足")

    # ---- 3) 触发定义对照 ----
    print("\n[3] 触发定义澄清（31 vs 48 是什么关系）")
    print("  确认：纯动量 = weights(仅动量1.0) + min_score=1 → '只要动量满足就触发，总分不设门槛'")
    print("  = 全新阈值信号集，不是 '48 里只保留动量满足的 10 个'。")
    # 公平对照：48 信号里仅保留动量满足者（真子集，min_score=3 不变，只看动量类别在不在）
    sub_mom = [e for e in full if "动量" in (e.get("bottom_cats") or [])]
    sub_st = _stats([e["forward_return_20"] for e in sub_mom])
    print(f"  A) 纯动量(min_score=1, 新阈值): n={pst['n']}, fwd20={pst['mean']*100:+.2f}%")
    print(f"  B) 现有48里仅动量满足者(真子集,min_score=3): n={sub_st['n'] if sub_st else 0}, "
          f"fwd20={(sub_st['mean']*100 if sub_st else 0):+.2f}%")
    print(f"  → 31 vs 48 属 A（新阈值信号集），非 B（真子集）。"
          f"若 A 与 B 差异大，说明 +2.03% 主要来自降阈值而非动量本身。")

    # 结论
    print("\n===== 结论 =====")
    if st and st['t'] is not None:
        print(f"  纯动量均值显著性：t={st['t']:.2f}，" +
              ("显著" if abs(st['t']) >= 2 else "不显著") + "（|t|<2 默认不可靠）")
    if out_path:
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump({
                "symbol": symbol, "n_full": len(full), "n_pure": len(pure),
                "pure_stats": st, "baseline_span": ast,
                "diff_pure_minus_baseline_pp": diff,
                "trigger_def": "pure=momentum_satisfied_min_score1; full=min_score3",
            }, fh, ensure_ascii=False, indent=2)
        print(f"  已写出: {out_path}")


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
        print("用法: python3 scripts/momentum_baseline_check.py <symbol> [--lb N] [--out f.json]")
        return
    momentum_baseline_check(symbol, lookback=lookback, out_path=out_path)


if __name__ == "__main__":
    main()
