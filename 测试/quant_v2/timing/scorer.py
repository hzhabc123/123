"""
Quant V2 择时评分卡（增强模块：timing/scorer）

对应方法论文档第 3 节"增强评分卡（10 分制）"：
  ≥7 分 → 高概率区间，可分批操作
  5-6 分 → 关注，等待确认
  ≤4 分 → 信号不足，放弃或仅观察

Scorer 接收 SignalItem 列表，按类别聚合成"底部分 / 顶部分"。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

from timing.signals import SignalItem


CATEGORY_KEYS = {
    "structure": "结构", "momentum": "动量", "volume": "量能",
    "volatility": "波动", "emotion": "情绪", "cross": "跨市场",
    "fundamental": "基本面", "options": "期权", "timing": "时间",
    "confirm": "确认",
}


@dataclass
class ScoreResult:
    bottom_score: int = 0
    top_score: int = 0
    direction: str = "观察"
    level: str = "低"
    details: Dict[str, dict] = None

    def __post_init__(self):
        if self.details is None:
            self.details = {}

    def as_dict(self) -> dict:
        return {
            "bottom_score": self.bottom_score, "top_score": self.top_score,
            "direction": self.direction, "level": self.level, "details": self.details,
        }


def _categorize(item: SignalItem) -> str:
    name = item.name
    for key, cn in CATEGORY_KEYS.items():
        if name.startswith(cn) or cn in name:
            return key
    return "other"


class TimingScorer:
    """底部/顶部评分卡"""

    def score(self, items: List[SignalItem]) -> ScoreResult:
        bottom_scores: Dict[str, dict] = {}
        top_scores: Dict[str, dict] = {}
        for it in items:
            cat = _categorize(it)
            bias = self._bias(it.name)
            dest = bottom_scores if bias == "bottom" else (top_scores if bias == "top" else None)
            if dest is None:
                continue
            if it.hit and (cat not in dest or it.hit > dest[cat]["hit"]):
                dest[cat] = {"hit": 1, "detail": it.detail, "name": it.name}
        bottom = sum(1 for v in bottom_scores.values() if v["hit"])
        top = sum(1 for v in top_scores.values() if v["hit"])
        direction = "看多" if bottom > top else ("看空" if top > bottom else "观察")
        best = max(bottom, top)
        level = "高" if best >= 7 else ("中" if best >= 5 else "低")
        return ScoreResult(bottom, top, direction, level, details={
            "bottom": {k: v for k, v in bottom_scores.items()},
            "top": {k: v for k, v in top_scores.items()},
        })

    @staticmethod
    def _bias(name: str) -> str:
        bottom_words = ["前低", "下轨", "超卖", "金叉", "地量", "阳线", "恐慌",
                        "收缩", "接近前低", "创新低", "跌破", "看涨", "回购",
                        "低估", "低分位", "低股息", "申购", "贴水", "成本",
                        "偏多", "做多", "回升", "回暖", "企稳", "反弹"]
        top_words = ["前高", "上轨", "超买", "死叉", "天量", "滞涨", "上影",
                     "狂热", "放大", "接近前高", "创新高", "突破", "看跌", "减持",
                     "高估", "高分位", "高股息", "赎回", "升水", "抛压",
                     "偏空", "做空", "回落", "降温", "见顶", "下跌"]
        for w in bottom_words:
            if w in name:
                return "bottom"
        for w in top_words:
            if w in name:
                return "top"
        return "neutral"
