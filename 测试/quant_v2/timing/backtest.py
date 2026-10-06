from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np

from timing.signals import build_signal_items, SignalInput
from timing.scorer import TimingScorer
from timing.probability import ProbabilityCalibrator


@dataclass
class HitRecord:
    index: int
    dt: object
    direction: str
    level: str
    entry_price: float
    hit: bool
    out_price: float
    reason: str = ""


@dataclass
class IntervalBacktestResult:
    records: List[HitRecord]
    level_stats: Dict[str, dict] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "total_signals": len(self.records),
            "level_stats": self.level_stats,
            "hit_rate": {
                k: (v["hits"] / v["total"] if v["total"] else 0.0)
                for k, v in self.level_stats.items()
            },
        }


class IntervalBacktest:
    def __init__(self, scorer: Optional[TimingScorer] = None, lookback: int = 60,
                 min_score: int = 5, horizon: int = 20,
                 target_pct: float = 0.05, stop_pct: float = 0.03):
        self.scorer = scorer or TimingScorer()
        self.lookback = lookback
        self.min_score = min_score
        self.horizon = horizon
        self.target_pct = target_pct
        self.stop_pct = stop_pct
        self.calibrator = ProbabilityCalibrator()

    def _signal_input(self, bars: List, t: int) -> SignalInput:
        start = max(0, t - self.lookback + 1)
        win = bars[start:t + 1]
        closes = np.array([b.close for b in win], dtype=float)
        highs = np.array([b.high for b in win], dtype=float)
        lows = np.array([b.low for b in win], dtype=float)
        volumes = np.array([getattr(b, "volume", 0.0) for b in win], dtype=float)
        return SignalInput(closes=closes, highs=highs, lows=lows, volumes=volumes)

    def _judge(self, bars, t: int, direction: str, entry: float) -> tuple:
        horizon = min(self.horizon, len(bars) - 1 - t)
        if horizon <= 0:
            return False, entry, "无未来数据"
        window = bars[t + 1:t + 1 + horizon]
        hi = max(b.high for b in window)
        lo = min(b.low for b in window)
        if direction == "bottom":
            if hi >= entry * (1 + self.target_pct):
                return True, hi, f"见底反弹 高见{hi:.2f}"
            if lo <= entry * (1 - self.stop_pct):
                return False, lo, f"止损 低见{lo:.2f}"
            return False, lo, "区间内未达标"
        else:
            if lo <= entry * (1 - self.target_pct):
                return True, lo, f"见顶回落 低见{lo:.2f}"
            if hi >= entry * (1 + self.stop_pct):
                return False, hi, f"止损 高见{hi:.2f}"
            return False, hi, "区间内未达标"

    def run(self, bars: List, externals_fn=None) -> IntervalBacktestResult:
        records: List[HitRecord] = []
        for t in range(self.lookback, len(bars)):
            if len(bars) - 1 - t <= 0:
                continue
            inp = self._signal_input(bars, t)
            externals = externals_fn(t, bars) if externals_fn else None
            items = build_signal_items(inp, externals=externals)
            res = self.scorer.score(items)
            if res.bottom_score >= self.min_score:
                hit, out_p, reason = self._judge(bars, t, "bottom", bars[t].close)
                rec = HitRecord(t, bars[t].datetime, "bottom", res.level,
                                bars[t].close, hit, out_p, reason)
                records.append(rec)
                self.calibrator.record(f"底部-{res.level}", hit)
            if res.top_score >= self.min_score:
                hit, out_p, reason = self._judge(bars, t, "top", bars[t].close)
                rec = HitRecord(t, bars[t].datetime, "top", res.level,
                                bars[t].close, hit, out_p, reason)
                records.append(rec)
                self.calibrator.record(f"顶部-{res.level}", hit)
        level_stats: Dict[str, dict] = {}
        for r in records:
            key = f"{r.direction}-{r.level}"
            st = level_stats.setdefault(key, {"hits": 0, "total": 0})
            st["total"] += 1
            st["hits"] += 1 if r.hit else 0
        return IntervalBacktestResult(records, level_stats)