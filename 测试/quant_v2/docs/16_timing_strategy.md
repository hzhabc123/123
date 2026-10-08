---
title: 择时策略接入回测引擎（TimingStrategy）
version: "1.1"
domain: 量化回测 / 择时 / 策略 / 引擎集成 / 可视化
version: "1.1"
tags: [quant, timing, strategy, engine, backtest, visualization]
aliases:
  - TimingStrategy
  - 择时策略
  - 权重接入引擎
  - 每bar权重打分
  - 打分触发点
  - plot_timing_signals
  - forward_return
  - path A
  - path B
description: 把 TimingScorer(自适应权重) 接入 BacktestEngine，每 bar 用当期权重打分产生区间信号；打分触发点接入可视化记录层（图上标注底/顶 + forward_return 事后标注）。
source: quant_v2/strategy/timing_strategy.py
---

# 择时策略接入回测引擎（TimingStrategy）

## 解决的问题

前面已实现：
- 评分卡打分（`TimingScorer`）
- 区间命中率回测（`IntervalBacktest`）
- 类目级自适应权重（`AdaptiveWeight`）

但这些都是**离线验证**。要让"每 bar 用当期权重打分"真正驱动回测，
需把评分器接入 `BacktestEngine`。`strategy/TimingStrategy` 完成这一闭环：
**每个 bar 用 TimingScorer(+当期权重) 打分 → 达到阈值产生带 strength 的区间信号**。

## 设计

`TimingStrategy` 继承 `BaseStrategy`，复用引擎的 `set_bar_context`/`get_signals` 机制：

- **打分**：每 bar 累积 closes/highs/lows/volumes，取最近 `lookback` 根构造
  `SignalInput`，`TimingScorer.score(items, weights=...)`。
- **权重**：静态表或动态 `weights_provider(bar, index, history)`；
  空仓且 `bottom_score >= min_score` → 做多。
- **qty**：置 0 交给引擎 `position_sizer`（PercentSizer 按资金占比定仓，
  天然适配高价股）。
- **指标快照**：上报 `bottom_score/top_score/direction/level`（口径=策略实际采用）。

## 使用

```bash
# 合成行情（免网络）
python3 scripts/timing_strategy_backtest.py
# 指定标的真实行情（akshare）
python3 scripts/timing_strategy_backtest.py 600519
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

解法：足够本金 + 放宽比例上限 + PercentSizer 定仓。

### 茅台回测固定配置（复现即用，勿再踩坑）

```python
# scripts/timing_strategy_backtest.py 中的可复现参数
strategy  : TimingStrategy(min_score=3, direction_mode="both", weights=..., lookback=60)
portfolio : Portfolio(initial_cash=500_000.0)          # 本金 50 万
risk      : max_single_trade_amount=1_000_000.0       # 单笔金额上限放宽
            max_single_trade_ratio=0.4                # 单笔最多占 40%
            max_position_ratio=0.8
sizer     : PercentSizer(percent=0.3, min_amount=1000.0)  # 按资金占比 30% 定仓
engine    : BacktestEngine(lookback=500)
```

> ⚠️ 结论仅作链路验证，**不代表策略有效性**：7 笔交易统计置信度极低，
> 且茅台为单边慢牛 + 高价整手限制，会同时污染"信号有效性"与"执行可行性"两个变量。
> 权重自适应是否成立需 3–5 年 × 10+ 标的（含牛/熊/震荡）验证；中低价高波动对照
> （宁德、券商 ETF、科创 50）可区分"打分弱"与"执行被卡"。

## 与 prod_mode 联动

```python
from timing.adaptive import AdaptiveWeight, update_from_backtest
from timing.backtest import IntervalBacktest

# 1) 训练权重（真实回测命中率）
aw = AdaptiveWeight(min_samples=8)
for sym in symbols:
    update_from_backtest(aw, IntervalBacktest().run(bars))

# 2) 用当期权重注入策略
strat = TimingStrategy(min_score=3, weights=aw.weights())
engine = BacktestEngine(strategy=strat, ...)
engine.run(bars)
```

若需每个 bar 动态切换权重，用 `weights_provider`（如按季度重算命中率）。

## 测试

```bash
python3 -m pytest tests/test_timing_strategy.py -q         # 策略集成 4 用例
python3 -m pytest tests/test_timing_signal_snapshot.py -q  # 快照字段 5 用例
```

覆盖：engine 中产生交易、指标快照口径、权重影响评分、高价股整手适配、
触发事件字段完整性、forward_return 事后标注正确性。
全套 117 passed。

## 打分触发点可视化（path A，诊断工具）

优先级高于权重自校正：A 是"诊断工具"，B 是"治疗手段"；没有 A 的可视化证据，
B 的季度调整无从验证对错。

### 快照字段扩展

`TimingStrategy.indicator_values()` 与 `get_trigger_events()` 上报字段：

| 字段 | 说明 |
|---|---|
| `bottom_score` / `top_score` | 当期底/顶分数 |
| `direction` / `level` | 方向 / 档位 |
| `trigger_type` | `bottom_enter` / `top_exit` / `top_no_pos`（空仓顶观望） |
| `price_at_signal` | 触发 bar 收盘价 |
| `forward_return_5/10/20` | **事后**标注 N 根收益（`get_trigger_events(annotate=True)` 回填） |

> 防前视：运行期 `on_bar` 只记录 `index` 与触发价，**不**计算未来收益；
> `forward_return` 由 `get_trigger_events(annotate=True)` 在 run 结束后
> 用累积的完整 closes 回填，只用于事后信号质量标注，不参与打分/下单。

### 可视化运行

```bash
python3 scripts/plot_timing_signals.py              # 合成数据
python3 scripts/plot_timing_signals.py 600519       # 真实行情
```

输出自包含 HTML `timing_signals_{symbol}_*.html`，三层标注：

- K 线主图：**底部触发（绿三角）+ 底分气泡**、**顶部触发（红三角）+ 顶分气泡**、空仓顶观望（橙点）
- 分数副图：`bottom_score` / `top_score` 双线 + `min_score` 阈值横线
- 事件表：触发类型、触发价、分数、档位、`forward_return_5/10/20`

### 验收标准（先于 B）

随机抽 20 个触发点，人工判断"该位置是否为合理区域"，肉眼可验证每个底/顶分数
对应的实际价格位置，排查打分偏早/偏晚。**命中率 < 60% 就先别做 B。**

## 权重季度自校正（path B，先别动权重）

前置三件事未完成前，**weights_provider 维持现状**，不为自校正编写/启用逻辑：

1. **扩样本**：3–5 年 × 10+ 标的，含牛/熊/震荡三态。
2. **分层回测**：按市场状态（ADX / 波动率分位）分组统计各信号命中率，
   而非全局一个权重。
3. **防过拟合**：季度权重变动设上下限（如单季度 ±15%），并保留
   "上一季度权重"作为对照基准。

否则 weights_provider 会变成"最近一个季度什么信号灵就押什么"，在 A 股
风格切换快的环境里非常危险。

## 依赖与后续

| 文件 | 角色 |
|---|---|
| strategy/timing_strategy.py | 评分器接入引擎的策略（含触发事件记录） |
| timing/scorer.py | 打分 |
| timing/adaptive.py | 当期权重来源 |
| scripts/timing_strategy_backtest.py | 端到端演示 |
| scripts/plot_timing_signals.py | 触发点可视化（三层标注 HTML） |
| tests/test_timing_signal_snapshot.py | 快照字段完整性 |

后续（按优先级）：
- ✅ 打分触发点接入可视化记录层（图上标注底/顶，path A）
- ⏸ weights_provider 季度自校正（path B）——先扩样本 + 分层回测 + 防过拟合，再启用
- ☐ 与 Donchian、买入持有等基准对比评估（需多标的样本）
