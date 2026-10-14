#!/usr/bin/env python3
"""closure_backtest 封顶测试：四策略对照（纯动量/原评分卡/买入持有/无条件做多）"""
import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
from scripts.closure_backtest import _buy_hold, _unconditional_long, _weights


def test_weights_momentum_only():
    """纯动量权重：只保留动量-bottom，其余 0（A型触发）"""
    w = _weights(keep_momentum=True)
    mom = [k for k, v in w.items() if v == 1.0]
    assert len(mom) == 1 and mom[0].endswith("动量-bottom"), w
    assert all(v == 0.0 for k, v in w.items() if not k.endswith("动量-bottom"))


def test_buy_hold_total_and_dd():
    """买入持有：首尾价差为总收益，最大回撤按峰值正确"""
    closes = np.array([100.0, 110.0, 90.0, 95.0])
    r = _buy_hold(closes)
    assert abs(r["total_return"] - (95 / 100 - 1)) < 1e-9   # -5%
    assert r["trades"] == 1
    # 峰值 110 → 谷 90 → 回撤 20/110 ≈ 18.18%
    assert abs(r["max_drawdown"] - (110 - 90) / 110) < 1e-9
    assert r["win_rate"] == 0.0


def test_buy_hold_short():
    """不足 2 根 bar 不崩溃"""
    r = _buy_hold(np.array([100.0]))
    assert r["total_return"] == 0.0 and r["trades"] == 1


def test_unconditional_long_reproducible():
    """相同 seed 结果可复现；交易次数受 max_start 约束"""
    rng_data = np.array([float(i) for i in range(100)])  # 100 根
    a = _unconditional_long(rng_data, n=10, seed=42, horizon=20)
    b = _unconditional_long(rng_data, n=10, seed=42, horizon=20)
    assert a["total_return"] == b["total_return"]
    assert a["n"] == b["n"] and a["n"] <= 80  # max_start = 100-20


def test_unconditional_long_bounds():
    """horizon 超长或 n=0 返回空统计"""
    r = _unconditional_long(np.array([1.0, 2.0]), n=5, seed=42, horizon=20)
    assert r["trades"] == 0 and r["n"] == 0


def test_closure_synthetic_roundtrip(tmp_path):
    """合成数据整段回测可运行并写出 JSON，含四行 + 核心字段"""
    from scripts.closure_backtest import closure_backtest
    out_path = str(tmp_path / "closure_syn.json")
    closure_backtest("SYN", lookback=30, out_path=out_path)
    with open(out_path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    assert len(data["rows"]) == 4
    for key in ("total_return", "max_drawdown", "trades", "win_rate", "plr"):
        assert key in data["rows"][0], key
    # 第三行应为买入持有（trades=1）
    assert data["rows"][2]["label"] == "买入持有茅台"
    assert data["rows"][2]["trades"] == 1
    assert "pure_trades" in data and "scorecard_trades" in data
