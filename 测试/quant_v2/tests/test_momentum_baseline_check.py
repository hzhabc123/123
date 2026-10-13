#!/usr/bin/env python3
"""momentum_baseline_check 纯动量基线显著性核查：SD/SEM/t + 同期全样本基准 + 触发定义澄清"""
import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
from scripts.momentum_baseline_check import _stats, _run_full


def test_stats_mean_sd_sem():
    """_stats 计算均值/SD/SEM/t 正确"""
    arr = np.array([1.0, 2.0, 3.0, 4.0])
    st = _stats(arr)
    assert abs(st["mean"] - 2.5) < 1e-9
    assert abs(st["sd"] - np.std(arr, ddof=1)) < 1e-9
    assert abs(st["sem"] - st["sd"] / np.sqrt(4)) < 1e-9
    assert abs(st["t"] - st["mean"] / st["sem"]) < 1e-9


def test_stats_empty_guard():
    """空数组不崩溃，返回占位统计"""
    st = _stats([])
    assert st["n"] == 0


def test_stats_single():
    """单样本 SD 为 0，t 为 0（不显著保护）"""
    st = _stats([5.0])
    assert st["sd"] == 0.0 and st["t"] == 0.0


def test_run_full_synthetic_struct():
    """合成数据跑通引擎，返回 (bottoms, closes, source) 三元组且结构完整"""
    bottoms, closes, source = _run_full("SYN", lookback=30)
    assert isinstance(bottoms, list)
    assert isinstance(closes, (list, np.ndarray))
    assert "行情" in source
    # 事件应含 forward_return_20 供统计
    if bottoms:
        assert "forward_return_20" in bottoms[0]


def test_baseline_check_synthetic_roundtrip(tmp_path):
    """合成数据下整段核查可运行并写出 JSON，含三段核心字段"""
    from scripts.momentum_baseline_check import momentum_baseline_check
    out_path = str(tmp_path / "mbc_syn.json")
    momentum_baseline_check("SYN", lookback=30, out_path=out_path)
    with open(out_path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    for key in ("n_full", "n_pure", "pure_stats", "baseline_span",
                "diff_pure_minus_baseline_pp", "trigger_def"):
        assert key in data, key
    # pure_stats 含共用的统计字段
    for key in ("mean", "sd", "sem", "t"):
        assert key in data["pure_stats"], key
