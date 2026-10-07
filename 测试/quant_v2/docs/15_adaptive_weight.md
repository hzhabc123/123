---
title: 择时自适应权重（prod_mode）
version: "1.1"
domain: 量化回测 / 择时 / 概率校准 / 动态权重
tags: [quant, timing, adaptive, weight, calibration, prod]
aliases:
  - 自适应权重
  - prod_mode
  - 动态权重
  - 权重自校正
description: 把个股真实命中率反馈为评分类目权重，让评分卡在新数据上持续自校正。
source: quant_v2/timing/adaptive.py
---

# 择时自适应权重（prod_mode）

## 解决的问题

`TimingScorer.score()` 每个类目固定 1 分（10 类最多 10 分），无法区分
"动量信号历史上命中率 70%"与"情绪信号命中率 40%"的真实差异。

`timing/adaptive.py` 把**个股真实命中率 → 类目权重**做成自动反馈闭环
（对应方法论文档"十三、动态权重：根据市场状态调整指标权重"），
让评分卡在新数据上持续自校正：
- 命中率高于先验(0.5)的类目 → 权重 > 1（更可信）
- 命中率低于先验的类目 → 权重 < 1（降权）
- 采样不足用默认权重 1.0（冷启动，避免小样本过激）
- 权重限制在 [0.5, 1.5]，防止单类主导

## 核心概念

- **key**：`{类目}-{方向}`，如 `动量-bottom` / `量能-top`。类目为中文
  （CATEGORY_KEYS 值），方向为 bottom/top，与 `TimingScorer.score(weights=)` 消费一致。
- **WeightItem**：维护 hits/total，`hit_rate()` 经验命中率。
- **权重映射**：`weight = 1.0 + (rate - 0.5) * 1.0`，截断到 [0.5, 1.5]。
- **采样下限**：默认 8 次，不足返回 1.0。

## prod_mode 闭环（推荐用法）

```python
from timing.adaptive import AdaptiveWeight, update_from_backtest
from timing.backtest import IntervalBacktest
from timing.scorer import TimingScorer

# 1) 真实行情回测累计类目命中率
bt = IntervalBacktest(scorer=TimingScorer(), lookback=60, min_score=5,
                      horizon=20, target_pct=0.05, stop_pct=0.03)
aw = AdaptiveWeight(min_samples=8)
for sym in symbols:                       # 多标的
    bars = src.fetch_daily_sorted(sym, start, end)
    update_from_backtest(aw, bt.run(bars))

# 2) 用自适应权重评分（只取底部方向权重示例）
weights = {k: v for k, v in aw.weights().items() if k.endswith("-bottom")}
result = TimingScorer().score(items, weights=weights)
```

`update_from_backtest` 使用区间回测的 `category_stats`（信号项级独立判定）按
`{类目}-{方向}` 累计——**每个类目有自己的命中率**，类目级权重与 scorer 消费一致。

> 迭代说明：v1 曾让同方向信号的命中类目共享同一次 hit，导致各底部类目命中率一致。
> 已改为**信号项级独立判定**：对每个 `hit=1` 的信号项单独以未来 horizon 判定，
> 不同类目信号出现在不同时点 → 类目命中率自然差异化。

### 周期自校正
prod_mode 效果来自"周期重算"：每隔一段新数据（如每季度）重跑真实回测，
用最新命中率覆盖 `AdaptiveWeight`，评分卡即随之调整。冷启动类目保持默认权重，
充分采样后自动获得可信权重。

## 真实数据运行结果（prod_mode demo，类目差异化）

8 只标的（茅台/五粮液/招行/平安/宁德/长江电力/美的/中信）2022–2024 真实行情累计：

```
动量-bottom  n=47   rate=61.7%  weight=1.117
动量-top     n=59   rate=59.3%  weight=1.093
情绪-top     n=40   rate=70.0%  weight=1.200   ← 最强信号
波动-top     n=52   rate=46.2%  weight=0.962   ← 最弱，降权
结构-top     n=93   rate=61.3%  weight=1.113
结构-bottom  n=137  rate=47.4%  weight=0.974
情绪-bottom  n=27   rate=55.6%  weight=1.056
确认-bottom  n=659  rate=50.8%  weight=1.008
波动-bottom  n=607  rate=50.6%  weight=1.006
量能-top     n=4    rate=50.0%  weight=1.0    ← 样本不足，冷启动默认
```

**差异化已生效**：不同类目命中率明显不同（情绪-top 70% vs 波动-top 46%），
权重相应上下调整；`rate` 未显著偏离先验(50%)的类目(确认/波动-bottom)权重几乎不动，
符合"防过激"设计。样本不足类目（量能）保持默认权重 1.0。

## 依赖关系

| 文件 | 角色 |
|---|---|
| timing/adaptive.py | AdaptiveWeight + update_from_backtest + weighted_score |
| timing/scorer.py | score(items, weights=) 支持类目-方向权重 |
| timing/backtest.py | HitRecord + category_stats（类目级独立命中判定） |
| scripts/timing_realscan.py | 真实行情多标的命中率来源 |

## 测试

```bash
python3 -m pytest tests/test_adaptive.py tests/test_timing_backtest.py -q
```

覆盖：命中率→权重映射、降权、冷启动默认、权重上下限、加权评分生效、
低权重不升档、从回测批量更新、类目差异化。全套 108 passed。
