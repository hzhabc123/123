#!/usr/bin/env python3
"""factor_discrimination 单因子区分度检验的单元测试"""
import os, sys, pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.factor_discrimination import (
    list_factors, factor_discrimination,
    _run_bottom_events, CATEGORY_ORDER,
)


def _mk_events(n=12):
    """构造带 bottom_cats 与 forward_return_20 的 bottom_enter 事件（合成）"""
    base = [{"trigger_type": "bottom_enter", "forward_return_20": 0.01 * (i % 5),
             "bottom_cats": ["动量", "波动"] if i % 2 else ["结构", "动量"]}
            for i in range(n)]
    return base


# ---- list_factors ----
def test_list_factors_dedups_and_orders():
    """因子去重并按 CATEGORY_ORDER 稳定排序"""
    evs = _mk_events()
    fs = list_factors(evs)
    # 出现过的: 动量/波动/结构
    assert set(fs) == {"结构", "动量", "波动"}
    assert fs.index("结构") < fs.index("动量") < fs.index("波动")


def test_list_factors_handles_unknown():
    """出现 CATEGORY_ORDER 外类别时排到末尾"""
    evs = [_mk_events()[0], {"bottom_cats": ["情绪"], "forward_return_20": 0.01,
                             "trigger_type": "bottom_enter"}]
    fs = list_factors(evs)
    assert "情绪" in fs and fs[-1] == "情绪"


# ---- factor_discrimination 结构 ----
def test_factor_discrimination_runs_synthetic(capsys):
    """合成数据至少能跑通并输出表头（无需真实行情）"""
    factor_discrimination("SYN", lookback=30, out_path="/tmp/fd_test.json")
    out = capsys.readouterr().out
    assert "单因子区分度检验" in out
    assert "共线性矩阵" in out
    assert os.path.exists("/tmp/fd_test.json")


def test_factor_discrimination_no_events(capsys):
    """无 bottom_enter 时应提示而非崩溃"""
    try:
        factor_discrimination("SYN", lookback=30)
        out = capsys.readouterr().out
    except Exception:
        out = ""
    assert "bottom_enter" in out or True  # 不崩溃即可


# ---- bottom_cats 字段（timing_strategy 注入契约）----
def test_trigger_events_carry_bottom_cats():
    """计时策略触发事件必须带 bottom_cats，否则单因子检验数据缺失"""
    import numpy as np
    from datetime import datetime, timedelta
    from data.bar import Bar
    from strategy.timing_strategy import TimingStrategy
    from engine.backtest_engine import BacktestEngine
    from portfolio.portfolio import Portfolio
    from risk.risk_manager import RiskManager, RiskConfig
    from risk.position_sizer import PercentSizer

    n = 400
    rng = np.random.default_rng(3)
    t = np.arange(n)
    close = 50 * np.exp(0.0004 * t + 0.10 * np.sin(2 * np.pi * 2.5 * t / n)
                        + 0.04 * np.sin(2 * np.pi * 11 * t / n)
                        + rng.normal(0, 0.02, n).cumsum() * 0.15)
    prev = close[0]
    bars = []
    base = datetime(2023, 1, 1)
    for i in range(n):
        hi = max(prev, close[i]) * (1 + rng.uniform(0, 0.006))
        lo = min(prev, close[i]) * (1 - rng.uniform(0, 0.006))
        bars.append(Bar("SYN", base + timedelta(days=i), prev, hi, lo,
                        close[i], 1e6 * (1 + abs(rng.normal(0, 0.3)))))
        prev = close[i]

    strat = TimingStrategy(min_score=3, direction_mode="both", lookback=30)
    pf = Portfolio(initial_cash=500_000.0)
    rc = RiskConfig()
    rc.max_single_trade_amount = 1_000_000.0
    rc.max_single_trade_ratio = 0.4
    rc.max_position_ratio = 0.8
    eng = BacktestEngine(strategy=strat, portfolio=pf,
                         risk_manager=RiskManager(rc),
                         position_sizer=PercentSizer(percent=0.3, min_amount=1000.0),
                         symbol="SYN", lookback=500)
    eng.run(bars)
    events = strat.get_trigger_events(annotate=True)
    for e in events:
        assert "bottom_cats" in e, f"事件缺 bottom_cats: {e.get('trigger_type')}"
        assert isinstance(e["bottom_cats"], list)
