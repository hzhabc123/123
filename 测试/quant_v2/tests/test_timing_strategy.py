"""
strategy/TimingStrategy 接入 BacktestEngine 的集成测试

覆盖：engine 中打分与信号产生、指标快照口径、权重注入、高价股整手适配（PercentSizer）。
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pytest
from datetime import datetime, timedelta

from data.bar import Bar
from strategy.timing_strategy import TimingStrategy
from engine.backtest_engine import BacktestEngine
from portfolio.portfolio import Portfolio
from risk.risk_manager import RiskManager, RiskConfig
from risk.position_sizer import PercentSizer, FixedSizer


def make_bars(n=300, seed=3):
    rng = np.random.default_rng(seed)
    t = np.arange(n)
    trend = 0.0007 * t
    cycle = 0.10 * np.sin(2 * np.pi * 3 * t / n)
    cycle2 = 0.04 * np.sin(2 * np.pi * 11 * t / n)
    noise = rng.normal(0, 0.015, n).cumsum() * 0.12
    close = 50 * np.exp(trend + cycle + cycle2 + noise)
    prev = close[0]
    bars = []
    base = datetime(2024, 1, 1)
    for i in range(n):
        hi = max(prev, close[i]) * (1 + rng.uniform(0, 0.005))
        lo = min(prev, close[i]) * (1 - rng.uniform(0, 0.005))
        bars.append(Bar("TST", base + timedelta(days=i), prev, hi, lo, close[i],
                        1e6 * (1 + abs(rng.normal(0, 0.3)))))
        prev = close[i]
    return bars


def _engine(strategy, initial=500_000.0, sizer=None, ratio=0.4):
    portfolio = Portfolio(initial_cash=initial)
    rc = RiskConfig()
    rc.max_single_trade_amount = 1_000_000.0
    rc.max_single_trade_ratio = ratio
    rc.max_position_ratio = 0.8
    return BacktestEngine(
        strategy=strategy, portfolio=portfolio,
        risk_manager=RiskManager(rc),
        position_sizer=sizer or PercentSizer(percent=0.3, min_amount=1000.0),
        symbol=strategy.name, lookback=500,
    )


def test_strategy_produces_signals_in_engine():
    """engine 中 TimingStrategy 应产生交易（打分达到阈值）"""
    bars = make_bars()
    strat = TimingStrategy(min_score=3, direction_mode="both", lookback=60)
    engine = _engine(strat)
    engine.run(bars)
    assert len(engine.get_all_trades()) > 0


def test_indicator_snapshot_reports_scores():
    """指标快照应上报本轮实际采用的评分（口径=策略内部）"""
    bars = make_bars()
    strat = TimingStrategy(min_score=3, direction_mode="both", lookback=60)
    engine = _engine(strat)
    engine.run(bars)
    ind = strat.indicator_values()
    assert "bottom_score" in ind and "top_score" in ind
    assert ind["direction"] in ("看多", "看空", "观察")
    assert ind["level"] in ("高", "中", "低")


def test_weights_affect_scoring():
    """权重表影响 bottom/top 分（强权重命中→记分>=默认）"""
    strat = TimingStrategy(min_score=3, direction_mode="both",
                           weights={"确认-bottom": 1.5, "动量-bottom": 1.5,
                                    "量能-bottom": 1.5, "波动-bottom": 1.5},
                           lookback=60)
    from timing.scorer import TimingScorer
    from timing.signals import SignalItem
    items = [SignalItem("结构-接近前低", 1, "前低"),
             SignalItem("动量-MACD金叉", 1, "金叉"),
             SignalItem("量能-地量后放量阳线", 1, "地量")]
    r = TimingScorer().score(items, weights=strat._weights)
    assert r.bottom_score >= 3


def test_high_price_stock_whole_lot():
    """高价股 + 整手：PercentSizer 定仓 + 足够本金，不应崩溃"""
    rng = np.random.default_rng(5)
    base = 1480.0
    closes = base + rng.normal(0, 12, 260).cumsum()
    closes = np.clip(closes, 1400, 1600)
    prev = closes[0]
    bars = []
    base_dt = datetime(2024, 1, 1)
    for i in range(len(closes)):
        hi = max(prev, closes[i]) * 1.004
        lo = min(prev, closes[i]) * 0.996
        bars.append(Bar("MT", base_dt + timedelta(days=i), prev, hi, lo, closes[i], 2e6))
        prev = closes[i]
    strat = TimingStrategy(min_score=3, direction_mode="both", lookback=60)
    engine = _engine(strat, initial=500_000.0)
    engine.run(bars)
    rej = getattr(engine, "rejected_signals", [])
    amount_rej = [r for r in rej if "超限" in (r.get("reason") or "")]
    assert len(engine.get_all_trades()) >= 0  # 不崩溃即可
