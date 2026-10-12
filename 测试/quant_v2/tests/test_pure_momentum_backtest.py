#!/usr/bin/env python3
"""pure_momentum_backtest 纯动量基线 vs 现有评分卡的单元测试"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.pure_momentum_backtest import _weights, _hit_rate, _run


def test_weights_only_momentum():
    """纯动量权重：只保留动量-bottom，其余类别为 0"""
    w = _weights(keep_momentum=True)
    mom = [k for k, v in w.items() if v == 1.0]
    assert len(mom) == 1 and mom[0].endswith("动量-bottom"), w
    assert all(v == 0.0 for k, v in w.items() if not k.endswith("动量-bottom"))


def test_weights_exclude_optional_categories():
    """keep_momentum=False 时全部类别权重为 0（用于对照空白）"""
    w = _weights(keep_momentum=False)
    assert all(v == 0.0 for v in w.values())


def test_hit_rate_basic():
    """fwd20>0 命中率计算"""
    evs = [{"forward_return_20": 0.01}, {"forward_return_20": -0.02},
           {"forward_return_20": 0.05}]
    rate, n = _hit_rate(evs)
    assert n == 3
    assert abs(rate - 2 / 3) < 1e-9


def test_hit_rate_empty():
    """无信号时命中率 0、n=0"""
    rate, n = _hit_rate([])
    assert rate == 0.0 and n == 0


def test_run_synthetic_returns_bottoms_and_source():
    """合成数据至少能跑通引擎并返回事件 + 数据源标识"""
    bottoms, source = _run("SYN", min_score=1, weights=_weights(True), lookback=30)
    assert isinstance(bottoms, list)
    assert "行情" in source
