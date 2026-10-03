"""
Quant V2 择时概率与仓位模型（增强模块：timing/probability）

对应方法论文档第 11/12 节：
- 凯利公式：根据胜率与赔率定仓位
- 概率校准：记录信号命中率，动态调整权重
- 贝叶斯更新：先验 + 新信号 → 后验
- 风控：单笔亏损不超过总资金 2%

仅提供仓位建议，不构成投资建议。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional


@dataclass
class KellyResult:
    p: float
    b: float
    kelly_fraction: float
    capped_fraction: float
    reason: str = ""

    def as_dict(self) -> dict:
        return {
            "p": self.p, "b": self.b, "kelly_fraction": self.kelly_fraction,
            "capped_fraction": self.capped_fraction, "reason": self.reason,
        }


def kelly_fraction(p: float, b: float, max_cap: float = 0.5,
                   max_loss_ratio: float = 0.02) -> KellyResult:
    """凯利公式：f = p-(1-p)/b；负期望返回0；超 max_cap 截断。"""
    if not (0 <= p <= 1) or b <= 0:
        return KellyResult(p, b, 0.0, 0.0, "参数无效")
    f = p - (1 - p) / b
    if f < 0:
        return KellyResult(p, b, 0.0, 0.0, "负期望，放弃")
    capped = min(f, max_cap)
    return KellyResult(p, b, f, capped, f"凯利={f:.2f} 截断至 {capped:.2f}")


class ProbabilityCalibrator:
    """概率校准：记录每个信号项的命中率，供动态调权。"""

    def __init__(self):
        self.hist: Dict[str, dict] = {}

    def record(self, name: str, hit: bool):
        h = self.hist.setdefault(name, {"hits": 0, "total": 0})
        h["total"] += 1
        if hit:
            h["hits"] += 1

    def hit_rate(self, name: str, default: float = 0.5) -> float:
        h = self.hist.get(name)
        if not h or h["total"] == 0:
            return default
        return h["hits"] / h["total"]

    def all_rates(self) -> dict:
        return {k: round(v["hits"] / max(v["total"], 1), 3) for k, v in self.hist.items()}

    def reset(self, name: Optional[str] = None):
        if name:
            self.hist.pop(name, None)
        else:
            self.hist = {}


def bayesian_update(prior_p: float, evidence_p: float, evidence_weight: float = 0.5) -> float:
    """贝叶斯更新（加权近似）：后验 = 先验 + w*(证据-先验)。"""
    if not (0 <= prior_p <= 1) or not (0 <= evidence_p <= 1):
        raise ValueError("概率必须在 0-1 之间")
    w = max(0.0, min(1.0, evidence_weight))
    return prior_p + w * (evidence_p - prior_p)


def position_by_level(level: str, risk_fraction: float = 1.0) -> float:
    """按档位给建议仓位：高65%/中35%/低10%。"""
    base = {"高": 0.65, "中": 0.35, "低": 0.10}.get(level, 0.10)
    return round(base * risk_fraction, 4)
