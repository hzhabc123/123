"""
Quant V2 择时评分卡（增强模块：timing/scorer）

对应方法论文档第 3 节"增强评分卡（10 分制）"：
  ≥7 分 → 高概率区间，可分批操作
  5-6 分 → 关注，等待确认
  ≤4 分 → 信号不足，放弃或仅观察

Scorer 接收 SignalItem 列表，按类别聚合成"底部分 / 顶部分"，
再合并给出方向判定（哪边得分高）与置信分档。
支持可选自适应权重表（prod_mode），缺省每类 1 分。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from timing.signals import SignalItem


# 类别 → 文档评分卡中的权重（每类最多 1 分；多信号同类只计最高）
CATEGORY_KEYS = {
    "structure": "结构",
    "momentum": "动量",
    "volume": "量能",
    "volatility": "波动",
    "emotion": "情绪",
    "cross": "跨市场",
    "fundamental": "基本面",
    "options": "期权",
    "timing": "时间",
    "confirm": "确认",
}


@dataclass
class ScoreResult:
    """评分卡结果"""
    bottom_score: int = 0          # 底部得分（0-10）
    top_score: int = 0             # 顶部得分（0-10）
    direction: str = "观察"        # 看多/看空/观察
    level: str = "低"              # 高/中/低
    details: Dict[str, dict] = None

    def __post_init__(self):
        if self.details is None:
            self.details = {}

    def as_dict(self) -> dict:
        return {
            "bottom_score": self.bottom_score,
            "top_score": self.top_score,
            "direction": self.direction,
            "level": self.level,
            "details": self.details,
        }


def _categorize(item: SignalItem) -> str:
    """由信号名推断类别（返回中文类别名，与 CATEGORY_KEYS 值一致，如 '结构'）"""
    name = item.name
    for key, cn in CATEGORY_KEYS.items():
        if name.startswith(cn) or cn in name:
            return cn
    return "other"


class TimingScorer:
    """
    底部/顶部评分卡。

    用法：
      scorer = TimingScorer()
      result = scorer.score(signal_items)
    """

    def score(self, items: List[SignalItem],
              weights: Optional[Dict[str, float]] = None) -> ScoreResult:
        """
        底部/顶部评分卡。

        weights: 可选，自适应权重表 {"{类别}-{方向}": float}（如 {"动量-bottom": 1.3}）。
                 命中该类信号时按权重计分；缺省/缺键用 1.0。
        """
        weights = weights or {}
        # 每类别取最大 hit，记录 detail
        bottom_scores: Dict[str, dict] = {}
        top_scores: Dict[str, dict] = {}
        for it in items:
            cat = _categorize(it)
            # 判定该信号偏向底部还是顶部：按名称关键词
            bias = self._bias(it.name)
            if bias == "bottom":
                if it.hit and (cat not in bottom_scores or it.hit > bottom_scores[cat]["hit"]):
                    bottom_scores[cat] = {"hit": 1, "detail": it.detail, "name": it.name, "weight": weights.get(f"{cat}-bottom", 1.0)}
            elif bias == "top":
                if it.hit and (cat not in top_scores or it.hit > top_scores[cat]["hit"]):
                    top_scores[cat] = {"hit": 1, "detail": it.detail, "name": it.name, "weight": weights.get(f"{cat}-top", 1.0)}
        _s = lambda vals: int(sum(v["hit"] * v.get("weight", 1.0) for v in vals) + 0.5)
        bottom = _s(bottom_scores.values())
        top = _s(top_scores.values())
        # 方向与档位
        direction = "看多" if bottom > top else ("看空" if top > bottom else "观察")
        best = max(bottom, top)
        level = "高" if best >= 7 else ("中" if best >= 5 else "低")
        return ScoreResult(
            bottom_score=bottom,
            top_score=top,
            direction=direction,
            level=level,
            details={
                "bottom": {k: v for k, v in bottom_scores.items()},
                "top": {k: v for k, v in top_scores.items()},
            },
        )

    @staticmethod
    def _bias(name: str) -> str:
        """弱规则判断信号方向偏向：底部候选词 / 顶部候选词"""
        bottom_words = ["前低", "下轨", "超卖", "金叉", "地量", "阳线", "恐慌",
                        "收缩", "接近前低", "创新低", "跌破", "看涨", "回购",
                        "低估", "低分位", "低股息", "申购", "贴水", "成本",
                        "偏多", "做多", "回升", "回暖", "企稳", "反弹"]
        top_words = ["前高", "上轨", "超买", "死叉", "天量", "滞涨", "上影",
                     "狂热", "放大", "接近前高", "创新高", "突破", "看跌", "减持",
                     "高估", "高分位", "高股息", "赎回", "升水", "抛压"]
        for w in bottom_words:
            if w in name:
                return "bottom"
        for w in top_words:
            if w in name:
                return "top"
        return "neutral"