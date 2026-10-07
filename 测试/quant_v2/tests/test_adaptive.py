"""
timing/adaptive 自适应权重测试

覆盖：命中率→权重映射、冷启动默认、采样下限、加权计分生效、从回测更新闭环。
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from timing.adaptive import AdaptiveWeight, update_from_backtest
from timing.scorer import TimingScorer
from timing.backtest import HitRecord


def test_weight_maps_above_prior():
    """命中率高于先验 → 权重 > 1；冷启动 → 默认 1.0"""
    aw = AdaptiveWeight(min_samples=1)
    for _ in range(10):
        aw.update("动量-bottom", True)   # 全命中 100%
    assert aw.weight("动量-bottom") > 1.0


def test_weight_below_prior_downgrades():
    aw = AdaptiveWeight(min_samples=1)
    for _ in range(10):
        aw.update("量能-top", False)     # 全未命中 0%
    assert aw.weight("量能-top") < 1.0


def test_cold_start_default():
    """无样本或样本不足 → 默认权重 1.0"""
    aw = AdaptiveWeight(min_samples=8)
    aw.update("结构-bottom", True)
    aw.update("结构-bottom", False)      # 只有2样本 < min 8
    assert aw.weight("结构-bottom") == 1.0
    assert aw.weight("不存在-key") == 1.0


def test_weight_bounds():
    """权重限制在 [0.5, 1.5]"""
    aw = AdaptiveWeight(min_samples=1)
    for _ in range(100):
        aw.update("确认-top", True)
    assert 0.5 <= aw.weight("确认-top") <= 1.5


def test_weighted_score_changes_result():
    """高权重类别命中 → 加权后得分更高"""
    scorer = TimingScorer()
    from timing.signals import SignalItem
    items = [
        SignalItem("结构-接近前低", 1, "前低"),       # bottom, 结构
        SignalItem("动量-MACD金叉", 1, "金叉"),       # bottom, 动量
        SignalItem("量能-地量后放量阳线", 1, "地量"), # bottom, 量能
        SignalItem("波动-布林下轨收回", 1, "下轨"),   # bottom, 波动
    ]
    r_default = scorer.score(items)                    # 无权重, 4 类各 1 → 4
    weights = {"结构-bottom": 1.5, "动量-bottom": 1.5,
               "量能-bottom": 1.5, "波动-bottom": 1.5}
    r_w = scorer.score(items, weights=weights)         # 全部 1.5
    assert r_default.bottom_score == 4
    assert r_w.bottom_score >= r_default.bottom_score
    assert r_w.level in ("中", "高")


def test_low_weight_can_keep_low_level():
    """多数类别命中确不>高权重：用少量高权重衡量能否升档"""
    scorer = TimingScorer()
    from timing.signals import SignalItem
    items = [SignalItem("结构-接近前低", 1, "前低"),
             SignalItem("动量-MACD金叉", 1, "金叉")]
    r = scorer.score(items, weights={"结构-bottom": 1.5})
    assert r.bottom_score == 3


def test_update_from_backtest():
    """从带 class 的 HitRecord 批量更新权重：落在类目级 key"""
    aw = AdaptiveWeight(min_samples=3)
    records = [HitRecord(0, None, "bottom", "中", 10.0, True, 11.0,
                         hit_categories=["动量", "量能"]),
               HitRecord(1, None, "bottom", "中", 10.0, True, 11.5,
                         hit_categories=["动量"]),
               HitRecord(2, None, "bottom", "中", 10.0, False, 9.0,
                         hit_categories=["动量", "结构"])]
    update_from_backtest(aw, records)
    assert aw.hit_rate("动量-bottom") == pytest.approx(2 / 3)
    assert aw.hit_rate("量能-bottom") == pytest.approx(1.0)
    assert aw.weight("动量-bottom") > 1.0