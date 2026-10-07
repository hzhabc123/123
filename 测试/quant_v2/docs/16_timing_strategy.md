---
title: 择时策略接入回测引擎（TimingStrategy）
version: "1.0"
domain: 量化回测 / 择时 / 策略 / 引擎集成
tags: [quant, timing, strategy, engine, backtest]
aliases:
  - TimingStrategy
  - 择时策略
  - 权重接入引擎
  - 每bar权重打分
description: 把 TimingScorer(自适应权重) 接入 BacktestEngine，每个 bar 用当期权重打分并产生区间信号。
source: quant_v2/strategy/timing_strategy.py
---

# 择时策略接入回测引擎（TimingStrategy）

## 解决的问题

前面已实现评分卡打分（TimingScorer）、区间命中率回测（IntervalBacktest）、
类目级自适应权重（AdaptiveWeight），但这些都是离线验证。
要让"每 bar 用当期权重打分"真正驱动回测，需把评分器接入 `BacktestEngine`。
`strategy/TimingStrategy` 完成这一闭环：**每个 bar 用 TimingScorer(+当期权重)
打分 → 达到阈值产生带 strength 的区间信号**。

## 设计

`TimingStrategy` 继承 `BaseStrategy`，复用引擎的 `set_bar_context`/`get_signals`：

- **打分**：每 bar 累积 closes/highs/lows/volumes，取最近 `lookback` 根构造
  `SignalInput`，`TimingScorer.score(items, weights=...)`。
- **权重**：静态表或动态 `weights_provider(bar, index, history)`；
  空仓且 `bottom_score >= min_score` → 做多。
- **qty**：置 0 交给引擎 `position_sizer`（PercentSizer 按资金占比定仓，天然适配高价股）。
- **指标快照**：上报 `bottom_score/top_score/direction/level`（口径=策略实际采用）。

## 使用

```bash
python3 scripts/timing_strategy_backtest.py              # 合成行情（免网络）
python3 scripts/timing_strategy_backtest.py 600519       # 指定标的真实行情
```

## 真实行情结果（茅台 2023–2024，min_score=3，PercentSizer 30%）

```
bars=484  交易数=7  订单=13
final_equity=522,519.78   total_return=+4.5%
```

每 bar 都用 Scoring + 当期权重打分，7 笔交易来自底部区间信号。

## 高价股整手适配（重要踩坑）

茅台每股约 1500，100 股整手 = 15 万。若本金只有 10 万，即使 PercentSizer
算出 30% 仓位（3 万），整手取整后仍会**超 `max_single_trade_ratio`** 被风控拒单
（单笔比例 150% > 40%）。已有 `05_risk_position_stop` 记录此问题。

解法：足够本金 + 放宽比例上限 + PercentSizer 定仓。演示用 `initial_cash=50万`、
`max_single_trade_ratio=0.4`、`PercentSizer(0.3)`。

## 与 prod_mode 联动

```python
from timing.adaptive import AdaptiveWeight, update_from_backtest
from timing.backtest import IntervalBacktest

aw = AdaptiveWeight(min_samples=8)
for sym in symbols:
    update_from_backtest(aw, IntervalBacktest().run(bars))

strat = TimingStrategy(min_score=3, weights=aw.weights())
engine = BacktestEngine(strategy=strat, ...)
engine.run(bars)
```

若需每个 bar 动态切换权重，用 `weights_provider`（如按季度重算命中率）。

## 测试

```bash
python3 -m pytest tests/test_timing_strategy.py -q   # 4 个用例
```

覆盖：engine 中产生交易、指标快照口径、权重影响评分、高价股整手适配。全套 112 passed。

## 依赖与后续

| 文件 | 角色 |
|---|---|
| strategy/timing_strategy.py | 评分器接入引擎的策略 |
| timing/scorer.py | 打分 |
| timing/adaptive.py | 当期权重来源 |
| scripts/timing_strategy_backtest.py | 端到端演示 |

后续：打分结果接入可视化记录层（图上标注底/顶触发点）；weights_provider 联动每季度自校正；与 Donchian 等策略对比评估。
