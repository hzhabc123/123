---
title: 择时区间命中率回测（Timing Backtest）
version: "1.0"
domain: 量化回测 / 择时 / 概率校准
tags: [quant, timing, backtest, probability, calibration]
aliases:
  - 区间命中率回测
  - 择时回测
  - 概率校准
  - 命中率验证
description: 把 TimingScorer 接入历史数据做区间命中率验证，用经验命中率校准档位先验并动态调整仓位。
source: quant_v2/timing/backtest.py
---

# 择时区间命中率回测

## 解决的问题

`scripts/timing_score.py` 只做单点打分与仓位建议，无法回答一个关键问题：
**按评分卡给出的档位（高/中/低触发区间），其命中概率是否真的如期望？**

`timing/backtest.py` 把 TimingScorer 接入历史 K 线做区间命中率回测，
验证"评分挡位 → 实际命中率"是否一致，并据此：
- 用经验命中率校准档位先验（ProbabilityCalibrator）
- 贝叶斯更新先验 → 后验
- 凯利公式定仓，与档位基准仓位融合给出动态仓位

这是方法论文档"十一、量化回测与概率模型"的落地闭环。

## 核心逻辑

对每个 bar t，只用其之前 `lookback` 根构造 SignalInput 打分（严格不偷看未来）：
- 底/顶得分 ≥ `min_score`（默认 5，即"中"档）记为一次**区间信号**。
- 未来 `horizon` 根 bar 内判定命中/失败。
- 统计各 `方向-档位` 的样本数与命中率。

## 使用

```bash
# 内置合成行情（无需网络）
python3 scripts/timing_backtest.py
# 接入真实 akshare 行情: 证券代码 开始日期 结束日期
python3 scripts/timing_backtest.py 600519 20240101 20241231
```

API 示例见源码 docstring。

外部四类信号（情绪/跨市场/基本面/期权）可通过 `externals_fn(t, bars) -> dict`
注入，每项应为 `{"hit": 0/1, "detail": str}` 格式；未提供则价格六类正常打分。

## 参数含义

| 参数 | 默认 | 含义 |
|------|------|------|
| lookback | 60 | 打分用的历史根数与指标窗口 |
| min_score | 5 | 底/顶触发信号的最低分数（5=中档） |
| horizon | 20 | 未来 N 根内判定命中 |
| target_pct | 0.05 | 目标幅度（命中要求的涨/跌幅） |
| stop_pct | 0.03 | 止损幅度（失败触发的反向幅度） |

## 输出示例（合成行情）

```
触发区间信号总数: 73
类别        样本  命中  命中率
bottom-中    73   29    39.73%
概率校准: 底部-中 经验命中率 39.70%
档位基准仓位: 35%
贝叶斯后验: 50% → 43.82%
凯利仓位(截断): 6.4%
融合建议仓位: 20.7%
```

## 概率校准闭环

- **ProbabilityCalibrator**：`record(name, hit)` 累计样本，`hit_rate(name)` 取经验命中率。
- **贝叶斯更新**：`bayesian_update(prior, evidence, weight)`。
- **凯利定仓**：`kelly_fraction(p, b)`，负期望返回 0，风控截断 ≤ 50%。
- **融合仓位**：档位基准仓位 与 校准后凯利按 50/50 融合。

### 实操提示
合成行情命中率不代表真实概率。实盘前必须用**真实数据**（如 akshare 历史日线）
跑同参数回测，得到的经验命中率才能作为仓位依据。

## 测试

```bash
python3 -m pytest tests/test_timing_backtest.py -q   # 7 个用例
```

覆盖：不偷看未来、底部命中需反弹、V 型反转应命中、校准器闭环、
贝叶斯边界、外部信号注入、数据不足不崩溃。全套 100 passed。

## 后续

- 接入真实数据源（akshare 已支持）跑多标的区间命中率统计
- 把经验命中率反馈给 TimingScorer 做动态权重/阈值自动调整
- 区间信号直接接入 BacktestEngine 的可视化记录层，图上标注底/顶触发点