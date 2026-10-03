---
title: Quant V2 择时引擎（增强模块落地）
version: 2.3
tags: [量化, 择时, 底部顶部, 评分卡, 凯利, 贝叶斯, 信号共振, 概率, 仓位, 指标]
summary: 将 12_market_timing_booster 方法论文档固化为可执行代码：timing/ 模块（指标库+10类信号打分器+底/顶评分卡+凯利仓位+概率校准+贝叶斯更新），含端到端用法与测试。
aliases: ['择时引擎', '评分引擎', '底部顶部代码', '凯利公式', '贝叶斯更新', '信号共振', 'TimingScorer', 'ProbabilityCalibrator', 'timing']
---

# Quant V2 择时引擎（timing/ 模块）

> v2.3 新增。把 `12_market_timing_booster.md` 的方法论**固化为可执行、可回测、可复用的 Python 模块**。
> 定位：判断底部/顶部"区间"，输出档位与仓位建议——**只算概率，不给绝对保证**，输出永远带风控。

## 1. 与文档的关系

| 文档（12 号） | 落地代码 |
|--------------|---------|
| 十三类信号源 | `timing/signals.py` 10 类 0/1 打分器 |
| 指标计算 | `timing/indicators.py` 向量化指标库 |
| 10 分制评分卡 | `timing/scorer.py` `TimingScorer` |
| 量能/波动/结构/动量 | `signals.py` 对应打分函数 |
| 情绪/跨市场/基本面/期权/时间 | 打分器预留外部注入接口 |
| 凯利公式 | `timing/probability.py` `kelly_fraction` |
| 概率校准 | `ProbabilityCalibrator` |
| 贝叶斯更新 | `bayesian_update` |
| 仓位与风控 | `position_by_level` + 凯利截断 |

## 2. 模块结构

| 文件 | 作用 |
|------|------|
| `timing/indicators.py` | numpy 向量化的 SMA/EMA/RSI/MACD/ATR/布林/VolumeProfile/VWAP/ZScore |
| `timing/signals.py` | 10 类信号 0/1 打分器（`SignalItem`），`build_signal_items` 聚合 |
| `timing/scorer.py` | `TimingScorer.score()` → 底部/顶部得分 + 方向 + 档位 |
| `timing/probability.py` | 凯利仓位、概率校准、贝叶斯更新、按档位给仓位 |
| `scripts/timing_score.py` | 端到端演示（指标→信号→评分→仓位） |
| `tests/test_timing.py` | 16 个用例 |

## 3. 信号打分器（signals.py）

`SignalInput(closes, highs, lows, volumes, ...)` 承载输入；每个信号函数返回 `List[SignalItem]`。

10 类：structure 结构 / momentum 动量 / volume 量能 / volatility 波动 / emotion 情绪 / confirm 确认（价格可算）+ cross 跨市场 / fundamental 基本面 / options 期权 / timing 时间（外部注入）。

**外部注入**：真实情绪/跨市场/基本面/期权/时间信号不在价格数据里，由调用方通过 `build_signal_items(..., externals={...})` 传入，每项 `{"name","hit","detail"}`。信号名需含方向词（偏多/回升/看涨 或 偏空/回落/看跌），评分卡据此归类。

## 4. 评分卡（scorer.py）

- **每类别按 hit 取 1 分**（同类多信号去重）。
- **bottom_score** = 偏底部命中的类别数；**top_score** = 偏顶部命中的类别数。
- 方向：`bottom>top → 看多`；`top>bottom → 看空`；相等 → 观察。
- 档位：`max≥7 → 高`；`5-6 → 中`；`≤4 → 低`。

方向归类由 `_bias(name)` 的底部/顶部关键词表决定。

## 5. 概率与仓位（probability.py）

- **凯利**：`kelly_fraction(p, b, max_cap=0.5)` → `f=p-(1-p)/b`；负期望返回0；超 cap 截断。
- **按档位仓位**：`position_by_level` → 高65%/中35%/低10%。
- **概率校准**：`ProbabilityCalibrator.record/hit_rate`。
- **贝叶斯更新**：`bayesian_update(prior, evidence, weight)`。

## 6. 端到端用法

```bash
python3 scripts/timing_score.py
```

```python
from timing.signals import build_signal_items, SignalInput
from timing.scorer import TimingScorer
from timing.probability import kelly_fraction, position_by_level

inp = SignalInput(closes=closes, highs=highs, lows=lows, volumes=volumes)
items = build_signal_items(inp, externals={...})
result = TimingScorer().score(items)
pos = position_by_level(result.level)
```

## 7. 一致性与风控约定

- **防前视**：只用历史数据计算。
- **指标口径**：指标库独立可复用，与策略层/可视化层值一致。
- **只算概率不给保证**：输出档位 + 仓位与止损约束，禁止裸给方向。
- **风控默认**：单笔亏损 ≤ 总资金 2%，最高仓位 50%。

## 8. 测试

```bash
python3 -m pytest tests/test_timing.py -v   # 16 passed
```

## 9. 当前范围与下一步

- **已落地**：10 类信号（跨市场/基本面/期权/时间由外部注入）+ 指标库 + 评分卡 + 概率/仓位。
- **待增强**：外部四类接真实数据源；W底/M头/头肩形态识别；假突破细化；接入 BacktestEngine 做区间回测验证命中率；市场状态识别（ADX/Hurst）动态调权。
- **仅教学**：本模块输出只反映历史统计规律，不构成投资建议。
