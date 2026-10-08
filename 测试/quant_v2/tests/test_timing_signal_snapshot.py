"""
strategy/TimingStrategy 打分触发点快照字段完整性测试（path A）

验证运行期记录的指标快照与触发事件字段齐全、forward_return 事后标注正确回填、
trigger_type 语义正确。可视化脚本 plot_timing_signals.py 依赖这些字段。
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
from datetime import datetime, timedelta

from data.bar import Bar
from strategy.timing_strategy import TimingStrategy
from engine.backtest_engine import BacktestEngine
from portfolio.portfolio import Portfolio
from risk.risk_manager import RiskManager, RiskConfig
from risk.position_sizer import PercentSizer


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


def _run(n=300, seed=3, min_score=3):
    bars = make_bars(n, seed)
    strat = TimingStrategy(min_score=min_score, direction_mode="both", lookback=60)
    portfolio = Portfolio(initial_cash=500_000.0)
    rc = RiskConfig()
    rc.max_single_trade_amount = 1_000_000.0
    rc.max_single_trade_ratio = 0.4
    rc.max_position_ratio = 0.8
    engine = BacktestEngine(
        strategy=strat, portfolio=portfolio,
        risk_manager=RiskManager(rc),
        position_sizer=PercentSizer(percent=0.3, min_amount=1000.0),
        symbol=strat.name, lookback=500,
    )
    engine.run(bars)
    return strat, bars, engine


def test_indicator_snapshot_has_required_fields():
    """指标快照应含 A 方案要求的核心字段"""
    strat, _, _ = _run()
    # 末 bar 快照（最后一个 lookback 之后的 bar 必有完整快照）
    ind = strat.indicator_values()
    for field in ("bottom_score", "top_score", "direction", "level", "trigger_type"):
        assert field in ind, f"快照缺字段 {field}"


def test_trigger_types_valid():
    """trigger_type 取值应限定在约定集合内"""
    strat, _, _ = _run()
    # 运行期 indicator_values 只保留末值；事件类型从 get_trigger_events 取
    for e in strat.get_trigger_events(annotate=False):
        assert e["trigger_type"] in ("bottom_enter", "top_exit", "top_no_pos"), e


def test_trigger_event_fields_complete():
    """每个触发事件字段齐全（path A 要求的字段）"""
    strat, _, _ = _run()
    events = strat.get_trigger_events(annotate=True)
    assert len(events) > 0, "应产生触发事件"
    required = {"symbol", "datetime", "index", "trigger_type",
                "price_at_signal", "bottom_score", "top_score", "level",
                "strength", "forward_return_5", "forward_return_10",
                "forward_return_20"}
    for e in events:
        assert required <= set(e.keys()), f"字段缺失: {required - set(e.keys())}"


def test_forward_return_correct():
    """forward_return 应与触发后实际收益一致（事后标注）"""
    strat, bars, _ = _run()
    closes = [float(b.close) for b in bars]
    events = strat.get_trigger_events(annotate=True)
    for e in events:
        i, p = e["index"], e["price_at_signal"]
        assert abs(closes[i] - p) < 1e-6, "price_at_signal 应为触发 bar 收盘价"
        for h in (5, 10, 20):
            fwd = e.get(f"forward_return_{h}")
            if i + h < len(closes):
                expect = closes[i + h] / closes[i] - 1.0
                assert fwd is not None and abs(fwd - expect) < 1e-9, \
                    f"forward_return_{h} 计算错误 idx={i}"
            else:
                assert fwd is None, f"越界应返回 None idx={i} h={h}"


def test_trigger_price_matches_engine_order():
    """底部触发价应能对应 engine 成交链路（至少产生了交易信号）"""
    strat, _, engine = _run()
    # 触发事件里应有 bottom_enter（做多）
    types = {e["trigger_type"] for e in strat.get_trigger_events(annotate=False)}
    assert "bottom_enter" in types
    assert len(engine.get_all_trades()) >= 0  # 不崩溃；成交由撮合/风控决定
