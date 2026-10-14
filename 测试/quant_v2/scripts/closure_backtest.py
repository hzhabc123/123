#!/usr/bin/env python3
"""
封顶测试：纯动量 / 原评分卡 / 买入持有 / 无条件做多 四对照回测

背景：用户判定这是"封顶测试"（milestone 7c-3），目的不是"决定是否落纯动量为基线"
（显著性核查已答：+2.03% 不显著，不该落），而是把"纯动量、原评分卡在茅台上都不成立"
这句话钉死成结论并归档。跑完无论结果，下一步都是「换因子池 或 扩样本」，
不再"加过滤/调参/换阈值"（那是第 N 轮循环）。

对照（同一把尺子，BacktestEngine 现有接口，不新建框架）：
  1. 纯动量(A型)   : TimingStrategy(min_score=1, weights=仅动量-bottom:1.0) →
                       "只要动量满足就触发"，降阈值放量，如实反映
  2. 原评分卡      : TimingStrategy(min_score=3, 默认全类别权重) → 48 信号基线
  3. 买入持有茅台  : 首 bar 全仓买入持有到尾（closes 直接算，交易次数=1）
  4. 无条件做多    : 与纯动量相同信号次数 n，随机选 n 个 bar 各持有 20 根
                     （同频随机进出，控样本期/频率偏差，随机种子固定可复现）

输出五指标：总收益 / 最大回撤 / 交易次数 / 胜率 / 盈亏比。
四行数字若全部接近 → 择时在茅台上不产生信息（框架根子上不 work，归档）。

用法:
    python3 scripts/closure_backtest.py 600519
    python3 scripts/closure_backtest.py 600519 --out outputs/closure_600519.json
"""
import sys, os, json, random
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.momentum_significance import load_bars
from scripts.pure_momentum_backtest import _weights


def _run_engine(symbol, min_score, weights, lookback=30):
    """跑 TimingStrategy 连续回测，返回 (summary, metrics)"""
    from strategy.timing_strategy import TimingStrategy
    from engine.backtest_engine import BacktestEngine
    from portfolio.portfolio import Portfolio
    from risk.risk_manager import RiskManager, RiskConfig
    from risk.position_sizer import PercentSizer
    from performance.analyzer import PerformanceAnalyzer

    bars, source = load_bars(symbol)
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
    return summary, m, portfolio.trades, closes_of(bars), source


def closes_of(bars):
    import numpy as np
    return np.array([b.close for b in bars], dtype=float)


def _buy_hold(closes):
    """买入持有：首 bar 收盘买入，末 bar 收盘卖出（无交易成本）"""
    if len(closes) < 2:
        return {"total_return": 0.0, "max_drawdown": 0.0, "trades": 1,
                "win_rate": 0.0, "plr": 0.0}
    total = closes[-1] / closes[0] - 1.0
    peak = closes[0]
    max_dd = 0.0
    for c in closes:
        if c > peak:
            peak = c
        else:
            dd = (peak - c) / peak if peak else 0.0
            max_dd = max(max_dd, dd)
    return {"total_return": total, "max_drawdown": max_dd, "trades": 1,
            "win_rate": 0.0, "plr": 0.0}


def _unconditional_long(closes, n, seed=42, horizon=20):
    """无条件做多：随机选 n 个入场点各持有 horizon 根，统计收益分布"""
    rng = random.Random(seed)
    if len(closes) <= horizon or n <= 0:
        return {"total_return": 0.0, "max_drawdown": 0.0, "trades": 0,
                "win_rate": 0.0, "plr": 0.0, "n": 0}
    max_start = len(closes) - horizon
    starts = sorted(rng.sample(range(max_start), min(n, max_start)))
    rets = [closes[s + horizon] / closes[s] - 1.0 for s in starts]
    wins = sum(1 for r in rets if r > 0)
    avg = sum(rets) / len(rets)
    # 简化盈亏比：平均盈利 / 平均亏损（去掉 0）
    pos = [r for r in rets if r > 0]
    neg = [r for r in rets if r < 0]
    plr = (sum(pos) / len(pos) / abs(sum(neg) / len(neg))) if pos and neg else float("inf") if pos else 0.0
    return {"total_return": avg, "max_drawdown": 0.0, "trades": len(starts),
            "win_rate": wins / len(rets), "plr": plr, "n": len(starts)}


def closure_backtest(symbol, lookback=30, out_path=None):
    print(f"===== 封顶测试：四策略对照（{symbol}，lb={lookback}）=====")

    # 1) 纯动量(A型)  + 2) 原评分卡 —— 引擎连续回测
    pure_sum, pure_m, pure_trades, closes, source = _run_engine(
        symbol, 1, _weights(keep_momentum=True), lookback)
    cur_sum, cur_m, cur_trades, _, _ = _run_engine(
        symbol, 3, None, lookback)

    # 3) 买入持有
    bh = _buy_hold(closes)

    # 4) 无条件做多：与纯动量同频（同信号次数）
    uncond = _unconditional_long(closes, n=len(pure_trades), seed=42, horizon=20)

    rows = [
        ("纯动量(A型, min_score=1)", pure_m.total_return, pure_m.max_drawdown,
         len(pure_trades), pure_m.win_rate, pure_m.profit_loss_ratio),
        ("原评分卡(min_score=3)", cur_m.total_return, cur_m.max_drawdown,
         len(cur_trades), cur_m.win_rate, cur_m.profit_loss_ratio),
        ("买入持有茅台", bh["total_return"], bh["max_drawdown"], bh["trades"],
         bh["win_rate"], bh["plr"]),
        ("无条件做多(同频随机, seed=42)", uncond["total_return"], 0.0,
         uncond["trades"], uncond["win_rate"], uncond["plr"]),
    ]

    print(f"\n| 策略 | 总收益 | 最大回撤 | 交易次数 | 胜率 | 盈亏比 |")
    print(f"|------|--------|---------|---------|------|--------|")
    for label, tr, dd, t, wr, plr in rows:
        print(f"| {label} | {tr*100:+.2f}% | "
              f"{('−' if dd < 0 else '')}{(dd)*100:.2f}% | {t} | "
              f"{wr*100:.1f}% | {plr if plr == float('inf') else f'{plr:.2f}'} |")

    # 判定
    print("\n===== 判定 =====")
    trs = [r[1] for r in rows[:2]]
    if all(abs(t) < 0.05 for t in trs) and abs(bh["total_return"]) < 0.05:
        print("  纯动量 & 原评分卡 & 买入持有 总收益均 <±5%，框架在茅台上几乎零信息。")
    elif abs(trs[0] - bh["total_return"]) < 0.05 and abs(trs[1] - bh["total_return"]) < 0.05:
        print("  纯动量/评分卡总收益与买入持有接近 → 择时无超额（可能只是跟随了上涨）。")
    else:
        print("  存在差异，但需结合显著性核查（+2.03% 不显著）谨慎解读，不据此优化。")
    print("  封顶测试定位：无论结果，下一步 = 换因子池 或 扩样本，不再调参/加过滤。")

    if out_path:
        data = {
            "symbol": symbol, "lookback": lookback, "source": source,
            "rows": [{"label": l, "total_return": tr, "max_drawdown": dd,
                      "trades": t, "win_rate": wr, "plr": plr}
                     for l, tr, dd, t, wr, plr in rows],
            "pure_trades": len(pure_trades), "scorecard_trades": len(cur_trades),
            "unconditional_long_n": uncond.get("n", 0),
        }
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
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
        print("用法: python3 scripts/closure_backtest.py <symbol> [--lb N] [--out f.json]")
        return
    closure_backtest(symbol, lookback=lookback, out_path=out_path)


if __name__ == "__main__":
    main()
