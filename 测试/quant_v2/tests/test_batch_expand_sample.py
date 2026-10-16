#!/usr/bin/env python3
"""扩样本三列对照 batch_expand_sample 的单元测试（v2：随机空仓分布式）。"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.batch_expand_sample import (
    _hold_return, _random_flat_return, _random_flat_dist, _buy_hold_return,
    classify_market_state,
)


def _series(gains):
    c = [100.0]
    for g in gains:
        c.append(c[-1] * (1 + g))
    return c


def _varying_series(n=40):
    """交替 +2%/-1% 的变化序列（真实行情风格，避免等幅导致无方差）"""
    return _series([0.02 if i % 2 == 0 else -0.01 for i in range(n)])


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


def test_random_flat_dist_mean_close_to_hold():
    # 多抽样均值应落在固定低仓位(同 exposure 无随机性的稳定基准)附近；
    # 单次抽样方差大不可用(用户裁定)。等幅序列会使每天收益相同→无方差，
    # 用变化序列(交替+2%/-1%)才能反映真实行情。
    up = _varying_series()
    hold = _hold_return(up, 0.5)
    dist = _random_flat_dist(up, 0.5, n_samples=2000)
    assert abs(dist["mean"] - hold) < 0.02
    assert dist["median"] <= dist["hi"] and dist["lo"] <= dist["median"]


def test_random_flat_dist_has_spread():
    # 单次抽样方差必须被量化为区间宽度；无宽度说明退化为固定比例(同固定低仓位)。
    up = _varying_series()
    dist = _random_flat_dist(up, 0.5, n_samples=2000)
    assert dist["hi"] - dist["lo"] > 0.01


def test_random_flat_dist_has_wider_spread_than_single():
    # 单次抽样 vs 分布：单次落在分布内，且分布均值远稳定于单次
    up = _varying_series()
    hold = _hold_return(up, 0.5)
    dist = _random_flat_dist(up, 0.5, n_samples=2000)
    single = _random_flat_dist(up, 0.5, n_samples=1)["mean"]
    assert dist["lo"] <= single <= dist["hi"]
    assert abs(dist["mean"] - hold) <= abs(single - hold) + 1e-9


def test_random_flat_dist_reproducible():
    up = _varying_series()
    assert _random_flat_dist(up, 0.5, n_samples=100, seed=7) == \
        _random_flat_dist(up, 0.5, n_samples=100, seed=7)


def test_random_flat_dist_short_guard():
    empty = _random_flat_dist([100.0], 0.5)
    assert empty["mean"] == 0.0 and empty["median"] == 0.0


def test_classify_market_state():
    assert classify_market_state(-0.10) == "下跌"
    assert classify_market_state(-0.049) == "震荡"
    assert classify_market_state(0.0) == "震荡"
    assert classify_market_state(0.049) == "震荡"
    assert classify_market_state(0.10) == "上涨"