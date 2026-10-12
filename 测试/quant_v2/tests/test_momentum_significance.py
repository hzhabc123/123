#!/usr/bin/env python3
"""momentum_significance 动量显著性检验的单元测试"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.momentum_significance import bootstrap_significance


def test_bootstrap_identical_groups_p_high():
    """两组分布相同 → P(差>0) 应接近 0.5（不显著）"""
    rng = __import__("random").Random(0)
    hit = [rng.gauss(0.0, 0.02) for _ in range(30)]
    miss = [rng.gauss(0.0, 0.02) for _ in range(30)]
    (lo, hi), p = bootstrap_significance(hit, miss, n_boot=500)
    assert lo < 0 < hi, f"相同分布 CI 应含 0，实际 [{lo}, {hi}]"
    assert 0.25 < p < 0.75, f"相同分布 P(差>0) 应接近 0.5，实际 {p}"


def test_bootstrap_hit_shifted_positive():
    """满足组均值高 → P(差>0) 应接近 1，CI 不含 0"""
    rng = __import__("random").Random(1)
    hit = [rng.gauss(0.03, 0.02) for _ in range(25)]
    miss = [rng.gauss(0.0, 0.02) for _ in range(25)]
    (lo, hi), p = bootstrap_significance(hit, miss, n_boot=500)
    assert lo > 0, f"正向偏移 CI 应不含 0，实际 [{lo}, {hi}]"
    assert p > 0.9, f"P(差>0) 应接近 1，实际 {p}"


def test_bootstrap_hit_shifted_negative():
    """满足组均值低 → P(差>0) 应接近 0，CI 不含 0"""
    rng = __import__("random").Random(2)
    hit = [rng.gauss(-0.03, 0.02) for _ in range(25)]
    miss = [rng.gauss(0.0, 0.02) for _ in range(25)]
    (lo, hi), p = bootstrap_significance(hit, miss, n_boot=500)
    assert hi < 0, f"负向偏移 CI 应不含 0，实际 [{lo}, {hi}]"
    assert p < 0.1, f"P(差>0) 应接近 0，实际 {p}"


def test_bootstrap_deterministic_seed():
    """同 seed 输出稳定（可复现）"""
    hit = [0.01, 0.02, -0.01, 0.03, 0.0, 0.015, -0.02, 0.025]
    miss = [0.0, -0.01, 0.005, -0.02, 0.01, -0.005, 0.0, -0.015]
    (lo1, hi1), p1 = bootstrap_significance(hit, miss, n_boot=400, seed=7)
    (lo2, hi2), p2 = bootstrap_significance(hit, miss, n_boot=400, seed=7)
    assert (lo1, hi1, p1) == (lo2, hi2, p2)
