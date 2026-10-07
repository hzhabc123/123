"""
Quant V2 择时增强模块（timing/）

把 docs/12_market_timing_booster.md 的方法论固化为可执行代码：
- indicators    向量化指标库（ATR/RSI/MACD/布林/VolumeProfile/VWAP/ZScore）
- signals      10 类信号的 0/1 打分器（结构/动量/量能/波动/情绪/确认 + 外部注入）
- scorer       底部/顶部评分卡（≥7高/5-6中/≤4低）
- probability  凯利仓位 + 概率校准 + 贝叶斯更新

原则：只算概率，不给绝对保证；输出必须带仓位与风控。
"""

from timing.scorer import TimingScorer, ScoreResult
from timing.probability import (
    kelly_fraction, ProbabilityCalibrator, bayesian_update, position_by_level
)
from timing.adaptive import AdaptiveWeight

__all__ = [
    "TimingScorer", "ScoreResult",
    "kelly_fraction", "ProbabilityCalibrator", "bayesian_update", "position_by_level",
    "AdaptiveWeight",
]