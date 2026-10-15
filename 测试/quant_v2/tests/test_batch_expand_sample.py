#!/usr/bin/env python3
"""扩样本三列对照 batch_expand_sample 的单元测试。"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.batch_expand_sample import (
    _hold_return, _random_flat_return, _buy_hold_return,
    classify_market_state,
)


def _series(gains):
    c = [100.0]
    for g in gains:
        c.append(c[-1] * (1 + g))
    return c


def test_buy_hold_return():
    assert abs(_buy_hold_return([100.0, 110.0]) - 0.10) < 1e-9
    assert abs(_buy_hold_return([100.0, 90.0]) + 0.10) < 1e-9


def test_buy_hold_short_guard():
    assert _buy_hold_return([100.0]) == 0.0
    assert _buy_hold_return([]) == 0.0


def test_hold_return_is_ratio_scaled():
    # 固定低仓位 = 持仓比例 × 首尾收益（静态、不择时）
    up = _series([0.01] * 20)  # ~+22%
    bh = _buy_hold_return(up)
    assert abs(_hold_return(up, 0.5) - 0.5 * bh) < 1e-9
    assert abs(_hold_return(up, 1.0) - bh) < 1e-9
    # 满仓 === 买入持有
    assert _hold_return(up, 1.0) == _buy_hold_return(up)


def test_hold_return_short_guard():
    assert _hold_return([100.0], 0.5) == 0.0


def test_random_flat_is_binary_not_smooth():
    # 随机空仓是二值化：随机挑部分日全仓。full hold（flat=0）应≈买入持有；
    # flat>0 时与"固定低仓位"不相等（否则就是同一机制，对照退化）。
    up = _series([0.01] * 20)
    bh = _buy_hold_return(up)
    assert abs(_random_flat_return(up, 0.0) - bh) < 1e-9
    assert _random_flat_return(up, 0.5) != _hold_return(up, 0.5)


def test_random_flat_reproducible():
    up = _series([0.01] * 20)
    assert _random_flat_return(up, 0.5, seed=42) == _random_flat_return(up, 0.5, seed=42)


def test_random_flat_bounds():
    # 随机空仓全部空仓（flat=1）→ 收益 0；全仓 → 首尾收益
    up = _series([0.01] * 20)
    assert _random_flat_return(up, 1.0, seed=42) == 0.0


def test_random_flat_short_guard():
    assert _random_flat_return([100.0], 0.5, seed=42) == 0.0


def test_classify_market_state():
    assert classify_market_state(-0.10) == "下跌"
    assert classify_market_state(-0.049) == "震荡"
    assert classify_market_state(0.0) == "震荡"
    assert classify_market_state(0.049) == "震荡"
    assert classify_market_state(0.10) == "上涨"