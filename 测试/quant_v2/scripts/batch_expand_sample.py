#!/usr/bin/env python3
"""
扩样本：策略 / 随机空仓 / 固定低仓位 三列对照（batch_expand_sample v2）

背景：封顶测试确认纯动量 +2.16% 可被空仓 beta 解释（86.8% 空仓），但原评分卡 +2.77% 不能
（62.2% 时间持仓）；两者都无统计显著 alpha，但原因不同。要回答"框架是普遍无效，还是普遍只有
低仓位 beta"，必须加两个对照区分"低仓位本身"与"择时时机"：

  1. 随机空仓对照  : 同样平均空仓比例，但空仓时点随机 → 检验择时时机
  2. 固定低仓位对照: 始终按该策略的平均持仓比例持仓、不择时 → 检验"低仓位 vs 动态仓位"

判断逻辑（用户裁定 v2）：
  · 策略 > 随机空仓均值(1000次抽样) → 择时时机有效
  · 策略 > 固定低仓位 → 动态择时优于静态低仓位
  · 策略 ≈ 固定低仓位 → 正超额就是低仓位 beta，不是择时

v2 修正：随机空仓从**单次抽样改为 1000 次抽样分布**（均值/中位数/5-95% 区间）。单次抽样方差
大到不能当对照（512880 单次抽到 +25.49% 是运气不是规律），"3/4 跑赢"是空心计数。均值才是与
固定低仓位（同 exposure 无随机性稳定基准）可比的对照。同时补 **vs 买入持有列** 与
**净超额(vs固定低仓位)合计**。

输出表头：标的、时段、市场状态、策略收益、随机空仓均值[5-95%]、固定低仓位收益、买入持有、
超额(vs随机)、超额(vs固定)、超额(vs买入持有)。

用法:
    python3 scripts/batch_expand_sample.py 600519 300750 512880 588000
    python3 scripts/batch_expand_sample.py --symbols 600519,300750
    python3 scripts/batch_expand_sample.py 600519 --mode momentum --out outputs/expand_600519.json
"""
import sys, os, json, random, math
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _load(symbol):
    from scripts.momentum_significance import load_bars
    bars, source = load_bars(symbol)
    import numpy as np
    closes = np.array([b.close for b in bars], dtype=float)
    return bars, closes, source


def _run_engine(bars, min_score, weights, lookback=30):
    """跑 TimingStrategy 连续回测，返回 (summary, metrics, trades, engine)"""
    from strategy.timing_strategy import TimingStrategy
    from engine.backtest_engine import BacktestEngine
    from portfolio.portfolio import Portfolio
    from risk.risk_manager import RiskManager, RiskConfig
    from risk.position_sizer import PercentSizer
    from performance.analyzer import PerformanceAnalyzer

    strat = TimingStrategy(min_score=min_score, direction_mode="both",
                           lookback=lookback,
                           weights=(weights or {}) if weights is not None else None)
    portfolio = Portfolio(initial_cash=500_000.0)
    rc = RiskConfig()
    rc.max_single_trade_amount = 1_000_000.0
    rc.max_single_trade_ratio = 0.4
    rc.max_position_ratio = 0.8
    engine = BacktestEngine(strategy=strat, portfolio=portfolio,
                            risk_manager=RiskManager(rc),
                            position_sizer=PercentSizer(percent=0.3, min_amount=1000.0),
                            symbol=strat.name, lookback=500)
    summary = engine.run(bars)
    m = PerformanceAnalyzer(engine.get_equity_curve(), portfolio.trades).compute()
    return summary, m, portfolio.trades, engine


def _avg_exposure(engine):
    """从 equity_curve 算平均持仓比例"""
    curve = engine.get_equity_curve()
    if not curve:
        return 0.0
    ratios = []
    for pt in curve:
        eq = pt.get("equity") or 0.0
        mv = pt.get("market_value") or 0.0
        ratios.append(mv / eq if eq > 0 else 0.0)
    return sum(ratios) / len(ratios) if ratios else 0.0


def _hold_return(closes, hold_ratio):
    """固定低仓位对照：始终按 hold_ratio 比例持仓、不择时。
    近似 = 持仓比例 × 首尾收益（无择时、无交易成本；比例恒定即"静态低仓位"）。"""
    if len(closes) < 2:
        return 0.0
    return hold_ratio * (closes[-1] / closes[0] - 1.0)


def _random_flat_return(closes, flat_ratio, seed=42):
    """随机空仓对照（单次抽样）：平均空仓比例 = flat_ratio，但空仓/持仓时点随机。
    二值化 —— 随机挑选一部分交易日全仓、其余空仓，使全仓日占比 ≈ exposure=1-flat_ratio；
    收益 = 选中全仓日的复利累加。⚠️ 单次抽样方差大，只作内部单位测试用；
    实际对照须用 _random_flat_dist（多抽样分布），勿用本函数下结论。"""
    dist = _random_flat_dist(closes, flat_ratio, n_samples=1, seed=seed)
    return dist["mean"]


def _random_flat_dist(closes, flat_ratio, n_samples=1000, seed=42):
    """随机空仓对照（多抽样分布）：对同一 exposure 随机时点抽样 n_samples 次，
    返回 均值/中位数/5%-95% 区间。均值才是与固定低仓位（同 exposure 无随机性）可比的
    稳定基准；单次抽样会把时点运气误读成策略优势。"""
    if len(closes) < 2:
        return {"mean": 0.0, "median": 0.0, "lo": 0.0, "hi": 0.0}
    daily = [closes[i + 1] / closes[i] - 1.0 for i in range(len(closes) - 1)]
    hold_ratio = 1.0 - flat_ratio
    n_hold = int(round(hold_ratio * len(daily)))
    rng = random.Random(seed)
    rets = []
    for _ in range(n_samples):
        hold_days = rng.sample(range(len(daily)), n_hold)
        ret = 1.0
        for i in hold_days:
            ret *= 1.0 + daily[i]
        rets.append(ret - 1.0)
    rets.sort()
    lo = rets[int(0.05 * n_samples)]
    hi = rets[int(0.95 * n_samples) - 1]
    mean = sum(rets) / len(rets)
    median = rets[n_samples // 2]
    return {"mean": mean, "median": median, "lo": lo, "hi": hi}


def _buy_hold_return(closes):
    if len(closes) < 2:
        return 0.0
    return closes[-1] / closes[0] - 1.0


def classify_market_state(bh_ret):
    """按买入持有收益粗分市场状态：下跌 / 震荡 / 上涨"""
    if bh_ret < -0.05:
        return "下跌"
    if bh_ret > 0.05:
        return "上涨"
    return "震荡"


def expand_one(symbol, min_score, weights, lookback=30):
    """单标的：跑策略 + 两个对照，返回一行记录。weights=None 用默认全因子。"""
    from scripts.pure_momentum_backtest import _weights

    bars, closes, source = _load(symbol)
    eff_weights = _weights(keep_momentum=True) if weights == "momentum" else None
    _min_score = 1 if weights == "momentum" else (min_score or 3)

    _, m, trades, engine = _run_engine(bars, _min_score, eff_weights, lookback)
    strat_ret = m.total_return
    exposure = _avg_exposure(engine)          # 该策略在本标的的平均持仓
    flat_ratio = 1.0 - exposure               # 平均空仓比例

    hold_ret = _hold_return(closes, exposure)               # 固定低仓位
    rand_dist = _random_flat_dist(closes, flat_ratio)       # 随机空仓 1000 次分布
    rand_mean = rand_dist["mean"]
    bh_ret = _buy_hold_return(closes)                       # 买入持有
    period = f"{bars[0].datetime:%Y-%m-%d}~{bars[-1].datetime:%Y-%m-%d}"
    mkt = classify_market_state(bh_ret)

    return {
        "symbol": symbol, "source": source, "bars": len(closes),
        "period": period, "market_state": mkt,
        "trades": len(trades), "win_rate": m.win_rate,
        "avg_exposure": exposure, "flat_ratio": flat_ratio,
        "strat_return": strat_ret, "hold_low_return": hold_ret,
        "rand_flat_result": rand_dist, "buy_hold_return": bh_ret,
        "rand_flat_return": rand_mean,          # 兼容键：随机空仓均值，勿再当单次
        "excess_vs_rand": strat_ret - rand_mean,
        "excess_vs_holdlow": strat_ret - hold_ret,
        "excess_vs_buyhold": strat_ret - bh_ret,
        "verdict_rand": "择时时机有效" if strat_ret > rand_mean else "≤随机空仓均值",
        "verdict_holdlow": ("动态择时>静态" if strat_ret > hold_ret
                            else "≈低仓位beta(非择时)"),
        "verdict_buyhold": ("vs买入持有胜" if strat_ret > bh_ret
                            else "vs买入持有输(上涨踏空/下跌避跌)"),
    }


def batch_expand(symbols, min_score=3, mode="both", lookback=30, out_path=None):
    """批量跑多标的：策略/随机空仓/固定低仓位 三列对照。mode='momentum' 跑纯动量。"""
    print(f"===== 扩样本三列对照（mode={mode}，lb={lookback}）=====")
    rows = []
    for sym in symbols:
        try:
            r = expand_one(sym, min_score, mode, lookback)
        except Exception as e:
            print(f"  {sym}: 失败 {e}")
            continue
        rows.append(r)
        rd = r["rand_flat_result"]
        print(f"| {r['symbol']} | {r['period']} | {r['market_state']} | {r['trades']:3d} | "
              f"{r['strat_return']*100:+6.2f}% | "
              f"随机均{rd['mean']*100:+6.2f}%[5-95: {rd['lo']*100:+.1f}~{rd['hi']*100:+.1f}] | "
              f"{r['hold_low_return']*100:+6.2f}% | {r['buy_hold_return']*100:+6.2f}% | "
              f"{r['excess_vs_rand']*100:+6.2f}pp | {r['excess_vs_holdlow']*100:+6.2f}pp | "
              f"{r['verdict_rand']} / {r['verdict_holdlow']} |")

    print("\n===== 归纳 =====")
    if rows:
        rand_ok = sum(1 for r in rows if r["strat_return"] > r["rand_flat_return"])
        hold_ok = sum(1 for r in rows if r["strat_return"] > r["hold_low_return"])
        bh_ok = sum(1 for r in rows if r["strat_return"] > r["buy_hold_return"])
        net_exc = sum(r["excess_vs_holdlow"] for r in rows)
        print(f"  {len(rows)} 标的中：\n"
              f"    跑赢随机空仓均值 {rand_ok} 个 → 择时时机有信号的标的数(1000次抽样)\n"
              f"    跑赢固定低仓位 {hold_ok} 个 → 动态择时优于静态低仓位的标的数\n"
              f"    vs买入持有 {bh_ok} 个 → 真跑赢持有(免于上涨踏空)的标的数\n"
              f"    净超额(vs固定低仓位)合计 {net_exc*100:+.2f}pp\n"
              f"  （负净超额 → 扣仓位后无 alpha，纯空仓 beta；"
              f"正净超额才须复核显著性）")

    if out_path:
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump({"mode": mode, "lookback": lookback, "rows": rows},
                      fh, ensure_ascii=False, indent=2)
        print(f"  已写出: {out_path}")


def main():
    argv = sys.argv[1:]
    # 收集非 flag、非 flag 值的参数作为 symbols
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
    if "--mode" in argv and argv[argv.index("--mode") + 1] in ("momentum", "scorecard"):
        mode = "momentum" if argv[argv.index("--mode") + 1] == "momentum" else "both"
    if "--symbols" in argv:
        symbols = [s.strip() for s in argv[argv.index("--symbols") + 1].split(",") if s.strip()]
    if not symbols:
        print("用法: python3 scripts/batch_expand_sample.py <symbols...> [--mode momentum|both] "
              "[--lb N] [--out f.json]")
        return
    batch_expand(symbols, mode=mode, lookback=lookback, out_path=out_path)


if __name__ == "__main__":
    main()