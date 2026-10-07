"""
Quant V2 择时自适应权重（prod_mode：timing/adaptive）

把"个股真实命中率 → 评分类别权重"做成自动反馈闭环，让评分卡在新数据上
持续自校正（对应方法论文档"十三、动态权重：根据市场状态调整指标权重"）。

设计：
  - AdaptiveWeight 记录每个"类别-方向"（如 动量-bottom）的命中率历史。
  - 命中率 → 权重：充分采样后，命中率高于先验(0.5)给 >1 权重，低于给 <1，
    采样不足用默认权重 1.0（冷启动，避免小样本过激）。
  - TimingScorer.score(items, weights=...) 按权重计分，同类多信号仍只计最高。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional

from timing.scorer import TimingScorer, CATEGORY_KEYS


# 先验命中率（评分卡隐含：中档约 0.55，这里取统一先验用于权重映射）
PRIOR = 0.5
# 权重上下限，防止单类过度主导
WEIGHT_MIN, WEIGHT_MAX = 0.5, 1.5
# 采样下限：样本不足时用默认权重
MIN_SAMPLES = 8


@dataclass
class WeightItem:
    """单个类别-方向的统计"""
    hits: int = 0
    total: int = 0


class AdaptiveWeight:
    """
    按"类别-方向"维护命中率并映射为评分权重。
    key 形如 "{类别}-{方向}"，如 动量-bottom、量能-top。
    """

    def __init__(self, prior: float = PRIOR, min_samples: int = MIN_SAMPLES):
        self.prior = prior
        self.min_samples = min_samples
        self._stats: Dict[str, WeightItem] = {}

    def update(self, key: str, hit: bool):
        """记录一次信号(类别-方向)的命中与否"""
        st = self._stats.setdefault(key, WeightItem())
        st.total += 1
        if hit:
            st.hits += 1

    def hit_rate(self, key: str) -> Optional[float]:
        st = self._stats.get(key)
        if not st or st.total == 0:
            return None
        return st.hits / st.total

    def _weight_from_rate(self, rate: float) -> float:
        """命中率 → 权重，线性映射到 [WEIGHT_MIN, WEIGHT_MAX]"""
        if rate is None:
            return 1.0
        w = 1.0 + (rate - self.prior) * 1.0
        return max(WEIGHT_MIN, min(WEIGHT_MAX, w))

    def weight(self, key: str) -> float:
        """返回该类别-方向的权重；采样不足返回默认 1.0"""
        st = self._stats.get(key)
        if not st or st.total < self.min_samples:
            return 1.0
        return round(self._weight_from_rate(self.hit_rate(key)), 3)

    def weights(self) -> Dict[str, float]:
        """返回全部有足够采样的权重"""
        out = {}
        for key in self._stats:
            w = self.weight(key)
            if self._stats[key].total >= self.min_samples:
                out[key] = w
        return out

    def summary(self) -> dict:
        return {
            k: {"total": v.total, "hits": v.hits,
                "rate": round(v.hits / v.total, 3) if v.total else None,
                "weight": self.weight(k)}
            for k, v in self._stats.items()
        }


def weighted_score(scorer: TimingScorer, items, weights: Optional[Dict[str, float]] = None):
    """
    自适应加权计分入口：把 weights 并入 TimingScorer.score。
    weights 形如 {"动量-bottom": 1.3, "量能-top": 0.8}。
    """
    return scorer.score(items, weights=weights or {})


def update_from_backtest(aw: AdaptiveWeight, records) -> "AdaptiveWeight":
    """
    从 IntervalBacktest 的 HitRecord 列表批量更新权重（prod_mode 核心）。

    HitRecord.hit_categories 记录该方向信号命中的类目（如 "动量"/"量能"）。
    按命中的类目方向 key（"{类目}-bottom/top"）统计——与 score(weights=) 消费一致。
    """
    for r in records:
        direction = r.direction  # bottom/top
        cats = getattr(r, "hit_categories", None) or [f"{direction}"]
        for cat in cats:
            aw.update(f"{cat}-{direction}", r.hit)
    return aw