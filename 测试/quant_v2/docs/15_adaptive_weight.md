---
title: 择时自适应权重（prod_mode）
version: "1.0"
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
让评分卡在新数据上持续自校正。

## 核心概念

- **key**：`{类目}-{方向}`，如 `动量-bottom` / `量能-top`，与 `score(weights=)` 消费一致。
- **权重映射**：`weight = 1.0 + (rate - 0.5) * 1.0`，截断到 [0.5, 1.5]。
- **采样下限**：默认 8 次，不足返回 1.0（冷启动防过激）。

## prod_mode 闭环（推荐用法）

```python
from timing.adaptive import AdaptiveWeight, update_from_backtest
from timing.backtest import IntervalBacktest
from timing.scorer import TimingScorer

bt = IntervalBacktest(scorer=TimingScorer(), lookback=60, min_score=5,
                      horizon=20, target_pct=0.05, stop_pct=0.03)
aw = AdaptiveWeight(min_samples=8)
for sym in symbols:
    bars = src.fetch_daily_sorted(sym, start, end)
    update_from_backtest(aw, bt.run(bars).records)

weights = {k: v for k, v in aw.weights().items() if k.endswith("-bottom")}
result = TimingScorer().score(items, weights=weights)
```

`HitRecord.hit_categories` 记录该方向信号命中的类目，`update_from_backtest`
据此按 `{类目}-{方向}` 累计，类目级权重与 scorer 消费 key 一致。

## 真实数据运行结果（prod_mode demo）

5 只标的（茅台/五粮液/招行/平安/宁德）2022–2024 真实行情累计：

```
动量-bottom  n=166  rate=59.6%  weight=1.096
情绪-bottom  n=166  rate=59.6%  weight=1.096
波动-bottom  n=166  rate=59.6%  weight=1.096
...
```

同一方向信号的所有命中类目共享该次 hit，因此命中率一致——这是当前
`HitRecord` 粒度的合理近似。权重 1.096 仅比先验微调，符合"防过激"设计。

## 依赖关系

| 文件 | 角色 |
|---|---|
| timing/adaptive.py | AdaptiveWeight + update_from_backtest + weighted_score |
| timing/scorer.py | score(items, weights=) 支持类目-方向权重 |
| timing/backtest.py | HitRecord 增加 hit_categories |
| scripts/timing_realscan.py | 真实行情多标的命中率来源 |

## 测试

```bash
python3 -m pytest tests/test_adaptive.py -q   # 7 个用例
```

覆盖：命中率→权重映射、降权、冷启动默认、权重上下限、加权评分生效、
低权重不升档、从回测批量更新。全套 107 passed。

## 后续

- 按类目独立判定命中（细化 HitRecord），得到差异化类目权重
- 把自适应权重接入 BacktestEngine，回测中每 bar 用当期权重打分
- 权重快照可持久化，供跨进程/跨标的复用