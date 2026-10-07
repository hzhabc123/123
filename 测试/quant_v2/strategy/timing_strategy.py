"""
Quant V2 择时策略（strategy/TimingStrategy）

把 TimingScorer 接入 BacktestEngine：每个 bar 用"当前自适应权重"对区间信号打分，
达到触发分产生带 strength 的做多/做空信号，将 prod_mode 评分直接联入回测引擎。

设计要点：
  - 与 Donchian 等纯技术策略不同，TimingStrategy 消费 timing/ 模块的评分卡，
    权重可来自 AdaptiveWeight（实时命中率自校正）或静态 dict。
  - strength = 评分归一化（bottom_score/10 或 top_score/10），供仓位/可视化使用。
  - 通过 engine 的"当期权重提供器"逐 bar 注入当期权重（如需动态自校正）。

状态建模：不强制持仓；当打分达到区间阈值才产生方向信号，否则观望。
"""
from __future__ import annotations

from typing import Dict, List, Optional

import numpy as np

from strategy.base_strategy import BaseStrategy
from timing.signals import build_signal_items, SignalInput
from timing.scorer import TimingScorer


class TimingStrategy(BaseStrategy):
    """
    基于择时评分卡的策略。

    参数：
      symbol          标的代码（默认取自 bar）
      min_score       触发做多/做空的底/顶最小分数（默认 5=中档）
      direction_mode  "both" 双向 / "long" 仅做多
      weights         Optional[Dict[str, float]]：静态权重表（{"类目-bottom":w}）
      weights_provider 可选 callable(bar, index, bars) -> Dict[str,float]，每 bar 当期权重
      lookback        打分用历史 bar 数
    """

    def __init__(self, name: str = "TimingStrategy",
                 min_score: int = 5,
                 direction_mode: str = "both",
                 weights: Optional[Dict[str, float]] = None,
                 weights_provider=None,
                 lookback: int = 60,
                 params: Optional[dict] = None):
        super().__init__(name=name, params=params)
        self.min_score = min_score
        self.direction_mode = direction_mode
        self._weights = weights or {}
        self._weights_provider = weights_provider
        self.lookback = lookback
        self.scorer = TimingScorer()
        self.closes: List[float] = []
        self.highs: List[float] = []
        self.lows: List[float] = []
        self.volumes: List[float] = []
        self._last_indicator: dict = {}

    # ---- 权重注入（供 engine / 外部调用） ----
    def set_weights(self, weights: Dict[str, float]):
        """设置静态权重表"""
        self._weights = dict(weights)

    def set_weights_provider(self, provider):
        """设置每 bar 动态权重提供器 provider(bar, index, bars) -> dict"""
        self._weights_provider = provider

    # ---- 指标快照（供可视化上报） ----
    def indicator_values(self) -> dict:
        return dict(self._last_indicator)

    # ---- 核心逻辑 ----
    def on_bar(self, bar):
        """处理单根 bar：打分 → 达到阈值产生信号"""
        self.closes.append(float(bar.close))
        self.highs.append(float(bar.high))
        self.lows.append(float(bar.low))
        self.volumes.append(float(getattr(bar, "volume", 0.0)))

        if len(self.closes) < self.lookback:
            return

        # 取最近 lookback 根（含当前）构造 SignalInput（不偷看未来：只用至当前）
        closes = np.array(self.closes[-self.lookback:], dtype=float)
        highs = np.array(self.highs[-self.lookback:], dtype=float)
        lows = np.array(self.lows[-self.lookback:], dtype=float)
        volumes = np.array(self.volumes[-self.lookback:], dtype=float)
        inp = SignalInput(closes=closes, highs=highs, lows=lows, volumes=volumes)
        items = build_signal_items(inp)

        # 当期权重：优先 provider（动态），否则静态表
        weights = self._weights
        if self._weights_provider is not None and self.state is not None:
            try:
                p = self._weights_provider(bar, self.state.current_bar_index,
                                           self.state.history)
                if p:
                    weights = p
            except Exception:
                weights = self._weights

        res = self.scorer.score(items, weights=weights)

        # 记录指标快照（供可视化：图上=策略实际采用的评分）
        self._last_indicator = {
            "bottom_score": res.bottom_score,
            "top_score": res.top_score,
            "direction": res.direction,
            "level": res.level,
        }

        symbol = bar.symbol
        current_position = self._get_position_qty(symbol)

        # 空仓且达到底部阈值 → 做多
        if current_position == 0 and res.bottom_score >= self.min_score:
            strength = min(1.0, res.bottom_score / 10.0)
            # qty=0 表示交给 engine 的 position_sizer 决定（适配高价股/风险预算）
            self.buy(symbol=symbol, price=bar.close, qty=0,
                     reason=f"底部区间 score={res.bottom_score}/{res.level} "
                            f"strength={strength:.2f}")
            return
        # 已达底部阈值但已持仓 → 允许加仓信号（由外部风控决定），这里保持观望避免重复
        if current_position > 0 and res.top_score >= self.min_score and self.direction_mode in ("both", "long"):
            strength = min(1.0, res.top_score / 10.0)
            # 顶部区间 + 已持仓 → 获利了结（卖出）
            self.sell(symbol=symbol, price=bar.close,
                      qty=current_position,
                      reason=f"顶部区间 score={res.top_score}/{res.level} "
                             f"strength={strength:.2f}")
            return
        if current_position == 0 and res.top_score >= self.min_score and self.direction_mode == "both":
            strength = min(1.0, res.top_score / 10.0)
            # 空仓 + 顶部区间（both 模式）→ 不做空（A股），仅观望
            self._last_indicator["note"] = f"顶部区间但空仓，仅观望 score={res.top_score}"

    def _get_position_qty(self, symbol: str) -> float:
        """读取当前持仓数量"""
        if self.portfolio is None:
            return 0.0
        pos = self.portfolio.get_position(symbol)
        return pos.qty if pos else 0.0

    # ---- 绩效/可选接口 ----
    def get_signal_summary(self) -> list:
        """返回已产生信号摘要（便于测试/归档）"""
        return list(self._signals)