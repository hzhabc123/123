#!/usr/bin/env python3
"""
纯动量基线 vs 现有评分卡对照（打破"为噪声做工程"的循环）

单因子诊断显示只有动量显著（bootstrap P=0.98, 95%CI=[+0.1,+6.6]），其余是噪声/反向/设计 bug。
那"多因子评分卡"当前形态可能等价于"一个动量指标 + 一堆噪声"。与其重建复杂评分卡，
先测纯动量：只保留动量类别作为信号，跑 lb=30 回测，和现有评分卡对照。

机制：bottom_score = 各命中底部类别权重加总（scorer.score 按类别聚合）。
  - 现有评分卡 = 全类别默认权重 1.0，min_score=3（触发需 ≥3 类同时命中）
  - 纯动量 = 只给动量类别 1.0、其余 0，min_score=1（动量一命中即触发）

回答：纯动量信号质量（fwd20 均值/命中率）是否 ≈ 或 > 现有评分卡？
  纯动量 ≈ 现有 → 评分卡复杂度没产出，新因子增量测试才有意义
  纯动量明显更差 → 现有评分卡还有别的信息（但 bootstrap 说没有，需复核）

用法:
    python3 scripts/pure_momentum_backtest.py 600519
    python3 scripts/pure_momentum_backtest.py 600519 --lb 30
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.momentum_significance import load_bars


def _weights(keep_momentum=True):
    """权重表：keep_momentum=True 只保留 动量-bottom（其余类别 0）；False 全 0（对照空白）"""
    from timing.scorer import CATEGORY_KEYS
    w = {}
    for key, cn in CATEGORY_KEYS.items():
        w[f"{cn}-bottom"] = 1.0 if (cn == "动量" and keep_momentum) else 0.0
    return w


def _run(symbol, min_score, weights, lookback=30):
    """跑引擎返回 bottom_enter 事件（带 fwd20）"""
    from strategy.timing_strategy import TimingStrategy
    from engine.backtest_engine import BacktestEngine
    from portfolio.portfolio import Portfolio
    from risk.risk_manager import RiskManager, RiskConfig
    from risk.position_sizer import PercentSizer

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
    engine.run(bars)
    events = strat.get_trigger_events(annotate=True)
    bottoms = [e for e in events if e["trigger_type"] == "bottom_enter"
               and e.get("forward_return_20") is not None]
    return bottoms, source


def _hit_rate(bottoms):
    """fwd20>0 占比（简化对照指标；完整 ATR 命中判定在 review_triggers）"""
    if not bottoms:
        return 0.0, 0
    return sum(1 for e in bottoms if e["forward_return_20"] > 0) / len(bottoms), len(bottoms)


def pure_momentum_backtest(symbol, lookback=30):
    from strategy.timing_strategy import TimingStrategy  # noqa: 保证 TimingScorer 加载

    print(f"===== 纯动量基线 vs 现有评分卡（{symbol}，lb={lookback}）=====")
    configs = [
        ("现有评分卡(min_score=3, 全因子默认权重)", 3, None),
        ("纯动量 (min_score=1, 仅动量)", 1, _weights(keep_momentum=True)),
    ]
    print("| 策略 | bottom_enter | fwd20均值 | fwd20>0比例 |")
    print("|------|-------------|-----------|------------|")
    for label, ms, w in configs:
        bottoms, source = _run(symbol, ms, w, lookback)
        if not bottoms:
            print(f"| {label} | 0 | — | — |")
            continue
        f20 = [e["forward_return_20"] for e in bottoms]
        mean = sum(f20) / len(f20)
        pos = sum(1 for x in f20 if x > 0) / len(f20)
        print(f"| {label} | {len(bottoms)} | {mean*100:+.2f}% | {pos*100:.1f}% |")

    print("\n[信号重合度] 现有评分卡 vs 纯动量 的 bottom_enter 时间点对比：")
    cur, _ = _run(symbol, 3, None, lookback)
    pure, _ = _run(symbol, 1, _weights(True), lookback)
    cur_idx = {e["index"] for e in cur}
    pure_idx = {e["index"] for e in pure}
    both = cur_idx & pure_idx
    only_cur = cur_idx - pure_idx
    only_pure = pure_idx - cur_idx
    print(f"  现有评分卡信号数={len(cur)}，纯动量信号数={len(pure)}")
    print(f"  两者都触发(重合)={len(both)}，仅现有={len(only_cur)}，仅纯动量={len(only_pure)}")


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    symbol = args[0] if args else None
    lookback = 30
    if "--lb" in sys.argv:
        lookback = int(sys.argv[sys.argv.index("--lb") + 1])
    if not symbol:
        print("用法: python3 scripts/pure_momentum_backtest.py <symbol> [--lb N]")
        return
    pure_momentum_backtest(symbol, lookback=lookback)


if __name__ == "__main__":
    main()
