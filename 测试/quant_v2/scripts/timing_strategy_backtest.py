#!/usr/bin/env python3
"""
TimingStrategy 接入 BacktestEngine 端到端演示

用真实行情（akshare）+ TimingStrategy + 自适应权重跑完整回测：
每 bar 用 TimingScorer(当期权重) 打分，产生带 strength 的区间信号。

用法:
    python3 scripts/timing_strategy_backtest.py              # 合成行情（免网络）
    python3 scripts/timing_strategy_backtest.py 600519       # 指定标的真实行情
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime

from engine.backtest_engine import BacktestEngine
from portfolio.portfolio import Portfolio
from risk.risk_manager import RiskManager, RiskConfig
from risk.position_sizer import PercentSizer


def load_bars(symbol=None):
    """真实行情优先；无 symbol 时用合成行情"""
    if symbol:
        from data.akshare_source import AkshareDataSource
        from datetime import date
        src = AkshareDataSource()
        bars = src.fetch_daily_sorted(symbol, date(2023, 1, 1), date(2025, 1, 1))
        if bars and len(bars) > 120:
            return bars, f"真实行情 {symbol}"
    # 合成行情
    import numpy as np
    from data.bar import Bar
    from datetime import timedelta
    n = 400
    rng = np.random.default_rng(7)
    t = np.arange(n)
    trend = 0.0006 * t
    cycle = 0.09 * np.sin(2 * np.pi * 3 * t / n)
    cycle2 = 0.035 * np.sin(2 * np.pi * 13 * t / n)
    noise = rng.normal(0, 0.018, n).cumsum() * 0.15
    close = 50 * np.exp(trend + cycle + cycle2 + noise)
    prev = close[0]
    bars = []
    base = datetime(2024, 1, 1)
    for i in range(n):
        hi = max(prev, close[i]) * (1 + rng.uniform(0, 0.005))
        lo = min(prev, close[i]) * (1 - rng.uniform(0, 0.005))
        bars.append(Bar(symbol=symbol or "SYN", datetime=base + timedelta(days=i),
                        open=prev, high=hi, low=lo, close=close[i],
                        volume=1e6 * (1 + abs(rng.normal(0, 0.3)))))
        prev = close[i]
    return bars, f"合成行情 {symbol or 'SYN'}"


def main():
    symbol = sys.argv[1] if len(sys.argv) > 1 else None
    bars, source = load_bars(symbol)

    from strategy.timing_strategy import TimingStrategy
    from timing.adaptive import AdaptiveWeight

    # 1) 自适应权重（示意注入；真实场景用 timing_realscan 命中率训练）
    aw = AdaptiveWeight(min_samples=8)
    aw.update("动量-bottom", True); aw.update("动量-bottom", True); aw.update("动量-bottom", False)
    aw.update("情绪-top", True);   aw.update("情绪-top", True);   aw.update("情绪-top", True)
    weights = aw.weights()
    if not weights:
        weights = {"确认-bottom": 1.1, "动量-bottom": 1.1, "量能-bottom": 1.0,
                   "波动-bottom": 0.9}

    strategy = TimingStrategy(min_score=3, direction_mode="both",
                              weights=weights, lookback=60)

    # 2) 组装回测环境（PercentSizer 定仓；高价股需足够本金，否则整手100股超比例上限）
    portfolio = Portfolio(initial_cash=500_000.0)
    risk_cfg = RiskConfig()
    risk_cfg.max_single_trade_amount = 1_000_000.0   # 演示放宽容许
    risk_cfg.max_single_trade_ratio = 0.4            # 单笔最多占 40% 资金
    risk_cfg.max_position_ratio = 0.8
    engine = BacktestEngine(
        strategy=strategy, portfolio=portfolio,
        risk_manager=RiskManager(risk_cfg),
        position_sizer=PercentSizer(percent=0.3, min_amount=1000.0),
        symbol=strategy.name, lookback=500,
    )
    result = engine.run(bars)

    print(f"===== TimingStrategy 接入 BacktestEngine（{source}）=====")
    print(f"bars={len(bars)}  策略={strategy.name}")
    print(f"交易数={len(engine.get_all_trades())}")
    eq = engine.get_equity_curve()
    if eq:
        last = eq[-1]
        print(f"净值末值={last['equity'] if isinstance(last, dict) and 'equity' in last else last:,.2f}")
    for k, v in (result or {}).items():
        if isinstance(v, (int, float, str)):
            print(f"  {k}: {v}")

    print("\n策略本 bar 指标快照（末值）:", strategy.indicator_values())
    print("权重表:", {k: round(v, 3) for k, v in weights.items()})


if __name__ == "__main__":
    main()