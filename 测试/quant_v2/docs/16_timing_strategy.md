---
title: 择时策略接入回测引擎（TimingStrategy）
version: "1.1"
domain: 量化回测 / 择时 / 策略 / 引擎集成 / 可视化
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
python3 -m pytest tests/test_review_triggers.py -q         # 失败模式预判+冻结标准 14 用例
python3 -m pytest tests/test_compare_trigger_reviews.py -q # 多标的对照 3 用例
python3 -m pytest tests/test_trigger_time_distribution.py -q  # 时间分布 4 用例
```

覆盖：engine 中产生交易、指标快照口径、权重影响评分、高价股整手适配、
触发事件字段完整性、forward_return 事后标注正确性、失败模式预判规则、
冻结标准命中判定、随机入场基准、多标的横向对照、下跌段占比时间分布。
全套 138 passed。

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
python3 scripts/plot_timing_signals.py 600519 3     # 真实行情，min_score=3
```

输出自包含 HTML `timing_signals_{symbol}_*.html`，三层标注：

- K 线主图：**底部触发（绿三角）+ 底分气泡**、**顶部触发（红三角）+ 顶分气泡**、空仓顶观望（橙点）
- 分数副图：`bottom_score` / `top_score` 双线 + `min_score` 阈值横线
- 事件表：触发类型、触发价、分数、档位、`forward_return_5/10/20`

### 验收标准（先于 B）

随机抽 20 个触发点，人工判断"该位置是否为合理区域"，肉眼可验证每个底/顶分数
对应的实际价格位置，排查打分偏早/偏晚。**命中率 < 60% 就先别做 B。**

#### 失败模式归类（比"合理/不合理"更有用）

不要只记"合理/不合理"得到一个数字——那不知道该修什么。改用失败模式归类：

| 失败模式 | 含义 | 对应调整方向 |
|---|---|---|
| 过早 | 信号出现后价格继续跌/涨 | 阈值偏高或超卖条件太激进 |
| 过晚 | 信号出现时价格已反转一段 | 阈值偏低或确认条件太重 |
| 假突破 | 突破颈线后快速收回 | 缺收盘价/量能二次确认 |
| 趋势中段误判 | 单边趋势中的中继震荡被当成顶/底 | 缺 ADX/趋势过滤 |
| 执行被卡 | 位置合理但被风控/整手卡住 | 执行层问题，非信号问题 |
| hit | 位置合理（预期方向收益成立） | — |

验收完得到的是一张**"该改哪里"的清单**，正好喂给路径 B 的分层设计。

#### 跨市场状态验收（勿全来自同一状态）

若 20 个触发点全部来自同一市场状态（如茅台 2023–2024 主要是区间震荡），
命中率只在震荡市成立，单边熊/牛里可能直接失效。≥2–3 个不同状态
（趋势 / 区间 / 高波动）分别统计，这也是 B 前置条件之一，验收阶段提前暴露。

### 自动归类工具

```bash
python3 scripts/review_triggers.py 600519                   # 预判失败模式分布（默认）
python3 scripts/review_triggers.py 600519 --interactive     # 逐点人工确认/改标
python3 scripts/review_triggers.py 600519 --out report.json # 结果存档
```

规则引擎预判 + 交互确认 + 分布表（按失败模式 + 市场状态分组）。

**茅台 2023–2024 实测（min_score=3，26 事件）**：规则引擎预判命中仅 **7.7%**
（过晚 38.5% + 过早 34.6% 高度集中）。但该数字是**规则引擎自判**（循环论证风险）——

**冻结标准命中率：策略 53.8%（14/26）**，方向分裂明显（方向仅统计
bottom_enter 做多 / top_exit 做空，top_no_pos 顶空仓不参与方向命中）：
- 做多 2/10=20%，随机基准 ~37% → **劣于随机买卖 17pp**
- 做空 1/3=33%，随机基准 ~63% → **劣于随机 30pp**（样本极小，仅供参考）

> ⚠️ 单标的样本小（区间态仅 3 点，样本不足仅供参考），且茅台回调浅不适宜择时验证。
> 在 `--interactive` 人工复核完成、且与规则引擎判定差异 ≤30% 前，上述数字
> **不作为决策依据**，结论为"信号质量尚未经验证"，而非"命中率太低"。

## 命中判定标准（冻结基准，多标的可比前提）

> 目的：多标的对照必须用**同一把尺子**，否则高波动标的天然更容易达标（波动率红利），
> 交叉比较失真。此标准在人工复核确认后**冻结**，后续所有标的共用。

| 常量 | 值 | 含义 |
|------|-----|------|
| `ATR_N` | 14 | Wilder ATR 窗口（用差分范围近似） |
| `HIT_K` | 2.0 | 目标倍数：触发后 20 根内收盘朝预期方向 ≥ 2×ATR |
| `HIT_HORIZON` | 20 | 判定窗口（根） |
| `HIT_MIN_SAMPLES` | 10 | 市场状态最少样本；不足 → "样本不足，仅供参考"，不参与汇总 |

**命中定义**：`触发后 HIT_HORIZON 根内，收盘朝预期方向移动 ≥ HIT_K×ATR，
且未先触发反向（朝反方向 k×ATR 止损）`。

- 方向：`bottom_enter`（做多）期望涨；`top_exit`（做空）期望跌；`top_no_pos`（顶空仓）
  不参与方向命中统计（compare 表已排除）。
- **随机入场基准**：同标的随机选 start 个入场点、持有 horizon 根、同一冻结标准判定，
  得基准命中率。**只有策略命中率显著高于同标的随机基准（≥10pp），才算该方向策略有效**，
  否则可能是"高波动标的做多本身胜率高"的波动率红利。
- `review_triggers.py` 输出含 `std_hit` / `atr` / `hit_std` 字段；输出 JSON 供
  `compare_trigger_reviews.py` 跨标的汇总。

```bash
python3 scripts/review_triggers.py 600519 --out outputs/review_600519.json
python3 scripts/compare_trigger_reviews.py 600519 300750 512880 588000
```

### 多标的对照结果（2023–2025，冻结标准）

> 本表为 `compare_trigger_reviews.py` 自动产出，已加**样本量列 + 低样本标灰 +
> 做空/做多基准差列**。**所有方向样本均 <10**，故本表**只到"信号质量未充分验证"**，
> 不做任何有效/无效归因。

| 标的 | 方向 | n | 策略命中 | 随机基准 | 优势(pp) | 判定 |
|------|------|---|---------|---------|---------|------|
| 600519 茅台 | 全部 | 26 | 53.8% | - | - | - |
| | 做多 | 10 | 20% | 37% | −17 | 🔴 |
| | ⬜做空 | 3 | 33% | 63% | −30 | ⬜ 样本<10，噪声 |
| 300750 宁德 | 全部 | 20 | 40.0% | - | - | - |
| | ⬜做多 | 6 | 17% | 48% | −31 | ⬜ 样本<10，噪声 |
| | ⬜做空 | 5 | 60% | 50% | +10 | ⬜ 样本<10，噪声 |
| 512880 券商ETF | 全部 | 23 | 47.8% | - | - | - |
| | ⬜做多 | 4 | 75% | 39% | **+36** | ⬜ 样本<10，噪声 |
| | ⬜做空 | 3 | 33% | 56% | −22 | ⬜ 样本<10，噪声 |
| 588000 科创50 | 全部 | 10 | 40.0% | - | - | - |
| | ⬜做多 | 2 | 0% | 38% | −38 | ⬜ 样本<10，噪声 |
| | ⬜做空 | 1 | 0% | 60% | −60 | ⬜ 样本<10，噪声 |

#### 低样本判定红线（勿对 <10 样本下结论）

> **样本 <10 的行标灰**：4 样本的 95% 置信区间 ≈ 19%–99%，几乎覆盖所有可能，
> 既不能证明有效也不能证明无效，**它就是噪声**。券商ETF做多 +36pp（3/4）同属此类，
> **不能当策略有效证据**。0% 命中率同样须配样本量读：0/2 是样本不足，不是策略失效。

#### 熊市混淆变量（做空基准 − 做多基准）

> 四标的做空基准**系统性**高于做多基准：茅台 +26pp、宁德 +3pp（微偏）、
> 券商ETF +17pp、科创50 +22pp。**这说明样本期（2023–2024）以跌为主**，
> "随机做多 20 根"天然胜率低——**这不是策略差，是熊市里做多本身就难**。

**据此修正结论表述**：~~"策略几乎跑不赢随机买卖"~~ → **"在熊市样本期内，
策略没有识别出下跌段并减少做多信号——这是趋势过滤缺失（ADX/均线/状态门控），
不是阈值问题"**。阈值再严，信号仍落在下跌段，故下一步是诊断信号是否集中
在下跌段（见下文时间分布），而非急于调阈值。

#### 时间分布诊断（回答"调过滤还是调阈值"，优先于人工复核）

`scripts/trigger_time_distribution.py` 把每标的 `bottom_enter` 按**季度 + 市场状态**
打点、并标记所在段的价格方向（下跌段占比）：

| 标的 | bottom_enter 数 | 下跌段占比 | 按状态 |
|------|----------------|-----------|--------|
| 600519 | 10 | **100%**（10/10） | 趋势8、区间2 |
| 300750 | 6 | 33%（2/6） | 趋势6 |
| 512880 | 4 | 25%（1/4） | 区间3、趋势1 |
| 588000 | 2 | 50%（1/2） | 区间1、趋势1 |

**诚实结论（实测 vs 假设）**：你的"信号集中在下跌段"假设**只有茅台成立**（100%，
因其回调浅+慢牛，每次下探都触发底部信号）。宁德/券商/科创的下跌段占比仅 25–33%，
**没有证据表明 bottom_enter 系统性集中在下跌段**。但同时**四标 bottom_enter 总量
仅 10/6/4/2，信号本身稀少**——在如此小的样本下，"缺趋势过滤"与"阈值/确认条件
问题"**在统计上尚无法区分**。

> ⚠️ 真正的瓶颈是**样本量**（回到路径 B Gate 第 3 条：3–5 年 × 10+ 标的）。
> 信号量太少时，加过滤或调阈值都可能是对噪声的过度响应。在看得出方向前，
> 先扩样本；茅台单标的的 100% 下跌段可作为"趋势过滤可能有增益"的假设，
> 但需多标的验证。完整分布见 `outputs/trigger_time_dist.md`。

## 权重季度自校正（path B，先别动权重）

前置三件事未完成前，**weights_provider 维持现状**，不为自校正编写/启用逻辑：

1. **扩样本**：3–5 年 × 10+ 标的，含牛/熊/震荡三态。
2. **分层回测**：按市场状态（ADX / 波动率分位）分组统计各信号命中率，
   而非全局一个权重。
3. **防过拟合**：季度权重变动设上下限（如单季度 ±15%），并保留
   "上一季度权重"作为对照基准。

否则 weights_provider 会变成"最近一个季度什么信号灵就押什么"，在 A 股
风格切换快的环境里非常危险。

### 路径 B 准入卡点（未通过则不得启动权重自校正）

> Gate 是对未来自己的约束：路径 B 的诱惑很大（尤其已有一个能跑的 weights_provider），
> 但样本不足时自校正会把噪声固化成权重，比不自校正更糟。

- [ ] A 人工验收完成，失败模式分布已记录
- [ ] 命中率 ≥60%（且跨 ≥2 种市场状态分别统计）
- [ ] 样本扩至 ≥3 年 × ≥10 标的
- [ ] 分层统计（ADX / 波动率分位）已产出各信号命中率
- [ ] 权重变动上限（单季度 ±15%）+ 上季度权重对照基准已实现
- [ ] 防过拟合：季度调整仅在样本量达标后启用

## 依赖与后续

| 文件 | 角色 |
|---|---|
| strategy/timing_strategy.py | 评分器接入引擎的策略（含触发事件记录） |
| timing/scorer.py | 打分 |
| timing/adaptive.py | 当期权重来源 |
| scripts/timing_strategy_backtest.py | 端到端演示 |
| scripts/plot_timing_signals.py | 触发点可视化（三层标注 HTML） |
| scripts/review_triggers.py | 失败模式归类工具（预判+交互+分布表） |
| scripts/compare_trigger_reviews.py | 多标的命中对照表（含样本量/低样本标灰/随机基准/熊市偏差列） |
| scripts/trigger_time_distribution.py | bottom_enter 按季度+状态打点（诊断是否集中下跌段） |
| data/akshare_source.py | akshare 数据源（含新浪 ETF 回退） |
| tests/test_timing_signal_snapshot.py | 快照字段完整性 |
| tests/test_review_triggers.py | 失败模式预判规则引擎 + 冻结标准命中 |
| tests/test_compare_trigger_reviews.py | 多标的对照表渲染 |
| tests/test_trigger_time_distribution.py | 时间分布诊断（下跌段占比/季度打点） |

后续（按优先级）：
- ✅ 打分触发点接入可视化记录层（图上标注底/顶，path A）
- ⏸ weights_provider 季度自校正（path B）——先扩样本 + 分层回测 + 防过拟合，再启用
- ☐ 与 Donchian、买入持有等基准对比评估（需多标的样本）
