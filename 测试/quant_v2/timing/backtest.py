"""
Quant V2 择时区间命中率验证器（timing/backtest）

把 TimingScorer 接入历史数据做"区间命中率"回测，验证评分卡档位与实际概率是否一致，
据此做概率校准与动态调权——这是方法论文档"十一、量化回测与概率模型"的落地。

核心逻辑：
  对每个 bar t，用其之前 lookback 根构造 SignalInput 并打分（不偷看未来）。
  若 bottom/top 得分 >= 触发分，记为一次"区间信号"（记录信号时的价格、档位、方向）。
  然后看未来 horizon 根 bar：
    - 底部信号命中 = 未来最高价能达到 entry*(1+target_pct)（见底反弹），
      失败 = 最低价跌破 entry*(1+stop_pct)；
    - 顶部信号命中 = 未来最低价跌到 entry*(1-target_pct)（见顶回落），
      失败 = 最高价涨过 entry*(1+stop_pct)。
  统计各档位命中率，喂给 ProbabilityCalibrator → 得到经验命中率 → 动态调权。

输出：按档位/方向分组的命中率、样本数，及校准结果。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np

from timing.signals import build_signal_items, SignalInput
from timing.scorer import TimingScorer
from timing.probability import ProbabilityCalibrator


@dataclass
class HitRecord:
    """一次区间信号及其结果"""
    index: int
    dt: object
    direction: str       # bottom / top
    level: str           # 高/中/低（命中前档位）
    entry_price: float
    hit: bool            # 命中?
    out_price: float     # 触发 hp/LP 的价格
    reason: str = ""
    hit_categories: List[str] = field(default_factory=list)  # 触发该方向得分的类目


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
    """
    区间命中率回测器。

    参数：
      scorer             TimingScorer 实例
      lookback          打分用历史 bar 数与指标窗口
      min_score          触发信号的底/顶最小分数（默认5，即"中"档才记区间）
      horizon           未来 N 根内判定命中
      target_pct        目标幅度（命中要求涨/跌幅）
      stop_pct          止损幅度（失败触发的反向幅度）
    """

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
        """用 t 之前 lookback 根构造 SignalInput（严格不偷看 t 之后）"""
        start = max(0, t - self.lookback + 1)
        win = bars[start:t + 1]  # 含 t
        closes = np.array([b.close for b in win], dtype=float)
        highs = np.array([b.high for b in win], dtype=float)
        lows = np.array([b.low for b in win], dtype=float)
        volumes = np.array([getattr(b, "volume", 0.0) for b in win], dtype=float)
        return SignalInput(closes=closes, highs=highs, lows=lows, volumes=volumes)

    def _judge(self, bars, t: int, direction: str, entry: float) -> tuple:
        """未来 horizon 内判定命中。返回 (hit, hit=False; 触发价)"""
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
        else:  # top
            if lo <= entry * (1 - self.target_pct):
                return True, lo, f"见顶回落 低见{lo:.2f}"
            if hi >= entry * (1 + self.stop_pct):
                return False, hi, f"止损 高见{hi:.2f}"
            return False, hi, "区间内未达标"

    def run(self, bars: List, externals_fn=None) -> IntervalBacktestResult:
        """
        跑区间命中率回测。

        externals_fn: 可选，调用方提供的外部信号函数 externals_fn(t, bars) -> dict，
                      传给 build_signal_items 的 externals。
        """
        records: List[HitRecord] = []
        for t in range(self.lookback, len(bars)):
            if len(bars) - 1 - t <= 0:
                continue
            inp = self._signal_input(bars, t)
            externals = externals_fn(t, bars) if externals_fn else None
            items = build_signal_items(inp, externals=externals)
            res = self.scorer.score(items)
            # 底/顶任一达到触发分
            if res.bottom_score >= self.min_score:
                hit, out_p, reason = self._judge(bars, t, "bottom", bars[t].close)
                cats = list(res.details.get("bottom", {}).keys())
                rec = HitRecord(t, bars[t].datetime, "bottom", res.level,
                                bars[t].close, hit, out_p, reason, cats)
                records.append(rec)
                self.calibrator.record(f"底部-{res.level}", hit)
            if res.top_score >= self.min_score:
                hit, out_p, reason = self._judge(bars, t, "top", bars[t].close)
                cats = list(res.details.get("top", {}).keys())
                rec = HitRecord(t, bars[t].datetime, "top", res.level,
                                bars[t].close, hit, out_p, reason, cats)
                records.append(rec)
                self.calibrator.record(f"顶部-{res.level}", hit)
        # 汇总按档位
        level_stats: Dict[str, dict] = {}
        for r in records:
            key = f"{r.direction}-{r.level}"
            st = level_stats.setdefault(key, {"hits": 0, "total": 0})
            st["total"] += 1
            st["hits"] += 1 if r.hit else 0
        return IntervalBacktestResult(records, level_stats)