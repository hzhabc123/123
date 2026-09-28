---
title: Quant V2 可视化回测系统
version: 2.1
tags: [量化, 可视化, BacktestRecorder, VisualExporter, 回放, Canvas, HTML, K线, 买卖点, 指标一致, 回撤, 一致性]
summary: 可视化回测系统：Recorder 全程记录（可追溯）、口径一致（图上指标=策略实际使用、买卖点=Portfolio 成交）、可视化层与交易层解耦（只读采集）；HTML/JSON/CSV 导出与验收标准。
aliases: ['可视化', '回测可视化', 'BacktestRecorder', 'VisualExporter', '买卖点', '指标显示', '回放', 'K线图', '净值曲线', '回撤', '一致性测试', 'replay', 'visualization']
---

# Quant V2 可视化回测系统

> 模块新增于 v2.1。理念一句话：**可视化是回测过程的"录音机"，只读采集、口径与回测引擎一致、绝不反向影响回测状态。**

## 1. 目标与三个"必须"

可视化回测系统的设计与验收围绕三个硬性要求展开：

1. **过程可追溯**：回测每一根 bar、每个信号、每次下单、每笔成交、每个持仓、每个净值点、每个指标值都被完整记录，可按时间还原。
2. **数据口径一致**：图上显示的指标 **必须等于策略实际计算所用的指标**（不得事后用另一套参数重算）；图上买卖点 **必须等于 Portfolio 入账的成交**。
3. **解耦**：可视化层只读 Recorder 的记录，**始终不修改、不依赖、不反向影响**回测状态；同一回测，加不加入 Recorder，最终结果完全一致。

任何一项测试不满足，可视化视为不合格。

## 2. 分层与文件

| 模块 | 文件 | 职责 |
|------|------|------|
| 记录层 | `visualization/recorder.py` | `BacktestRecorder`：纯记录，回测过程中零侵入采集 |
| 导出层 | `visualization/exporter.py` | `VisualExporter`：把记录渲染为 HTML / 导出 JSON / CSV |
| 引擎钩子 | `engine/backtest_engine.py` | `BacktestEngine` 可选 `recorder` 参数，在各环节调用记录 |
| 示例/自检 | `scripts/visualize_backtest.py` | 端到端 demo + `check()` 一致性自检 |
| 测试 | `tests/test_visualization.py` | pytest 验收用例 |

## 3. BacktestRecorder（记录层）

**角色**：纯记录容器。只接收外部给它的事件，不返回任何控制信号，不回调，不修改任何回测对象。

### 3.1 记录的分表

Recorder 按事件类型维护多张独立表：

| 表 | 方法 | 记录内容 | 数据结构 |
|----|------|---------|---------|
| bar | `record_bar(bar)` | K线 OHLCV | `{timestamp, symbol, open, high, low, close, volume, amount}` |
| indicator | `record_indicator(name, value, timestamp)` | 策略在该 bar 实际使用的指标值 | `{name, value, timestamp}` |
| signal | `record_signal(signal)` | 策略产出的信号 | `{timestamp, direction, price, reason, ...}` |
| order | `record_order(order)` | 发出的订单 | `{timestamp, order_id, side, qty, price, status, ...}` |
| trade | `record_trade(trade)` | 实际成交（= Portfolio 入账） | `{timestamp, trade_id, order_id, symbol, side, price, qty, commission, slippage, ...}` |
| position | `record_position(position)` | 持仓快照 | `{timestamp, symbol, side, qty, avg_price, market_value, unrealized_pnl, realized_pnl}` |
| equity | `record_equity(point)` | 净值点 | `{datetime, equity, cash, market_value}` |
| drawdown | `record_drawdown(dd, ts)` | 回撤点（写入同 equity 表） | `{timestamp, drawdown}` |
| risk_reject | `record_risk_reject(signal, order, reason)` | 风控拒绝，必须带 reason | `{timestamp, reason, ...}` |
| stop | `record_stop(event)` | 止损触发事件 | `{timestamp, ...}` |

关键约定：
- **统一时间轴**：所有记录以 `bar.datetime` 为对齐键，保证各表可按时间拉齐回放。
- **回撤与净值同表**：`record_drawdown` 追加到 `equity_records`（便于画副图），故 equity 表是混合记录（含 `equity` 或 `drawdown` 字段），导出 CSV 时必须用**所有记录键的并集**构建表头，不能只取首条字段。
- `get(type)` / `to_dataframe(type)` / `summary()` 提供只读访问，供导出层与测试使用。

### 3.2 记录纪律（必须遵守）

- 只在 engine 既定钩子处调用，不侵入策略内部逻辑。
- `record_*` 全部用 `try/except` 包裹，**任何记录失败都不允许中断回测**。
- Recorder 无状态回写，永不修改 portfolio / broker / 引擎 / 策略对象。

## 4. 引擎钩子（最小侵入接入）

`BacktestEngine.__init__(..., recorder: Optional[object] = None)` 增加可选参数，`self.recorder = recorder`。接入点固定为 5 处（全部用 `try/except` 包裹，失败静默）：

| 钩子 | 调用时机 | 记录 |
|------|---------|------|
| **bar** | `_on_bar` 开头 | 记录当根 K 线 |
| **signal** | 策略 `on_bar` 之后、处理每个信号前 | 记录策略信号 |
| **order** | `_process_signal` 创建订单后 | 记录发出的订单 |
| **trade** | `_on_trade`（`portfolio.on_trade` 之后） | 记录实际成交 |
| **equity/drawdown/position** | bar 结尾（组合市值更新后） | 记录净值、回撤、持仓 |

### 4.1 指标上报（口径一致的关键）

**在 strategy 的 `on_bar` 之后**，engine 读取 `strategy.indicator_values()` 并把每个指标名-值上报给 recorder。

- `BaseStrategy.indicator_values()` 默认返回 `{}`；
- `DonchianStrategy` 覆写返回 `{entry_high, exit_low, atr, close}`（即它本 bar 真实计算所用的通道上下轨与 ATR）；
- 这样图上指标 = 策略内部实际值，杜绝"事后用另一组参数重算导致图上与策略不一致"。

> 注意：指标必须在 `on_bar` **之后**读取（此时策略刚计算完本 bar 指标），不能在 `_on_bar` 开头与 K 线一起上报，否则拿到的是上一 bar 的值。

## 5. VisualExporter（导出层）

| 方法 | 功能 |
|------|------|
| `to_dict()` | 返回结构化 dict（bars/indicators/signals/orders/trades/positions/equity/risk_rejects/stops） |
| `to_json(path)` | JSON 导出 |
| `export_equity_csv(path)` | 净值/回撤 CSV（**用所有记录键的并集**做表头） |
| `render_html(path, symbol, title)` | 生成自包含 HTML（内嵌数据 + Canvas 绘制，**不依赖 CDN，可离线打开**） |

### 5.1 五类买卖点（图上标记）

图上用 5 种标记，严格区分"意图"与"事实"：

| 类型 | 形状 | 颜色 | 含义 |
|------|------|------|------|
| Signal | 空心箭头 | 橙 | 策略产生的信号（意图） |
| Order | 小圆点 | 灰 | 发出的订单 |
| Trade-Buy | 实心三角 ▲ | 红 | 实际买入成交（= Portfolio） |
| Trade-Sell | 实心三角 ▼ | 绿 | 实际卖出成交（= Portfolio） |
| Stop | 红叉 | 深红 | 止损触发 |
| Reject | 菱形 | 灰 | 风控拒绝 |

**买卖必须分离**：`render_html` 内部先构建全部成交点 `all_trades`，再按 `record.side` 过滤分为 `trade_buy` 与 `trade_sell`。**过滤必须基于 record 自带字段**，导出层不得自行猜测方向。

### 5.2 图表面板（自上而下）

1. **主图**：K 线（红涨绿跌）+ 成交量 + 指标叠加线（见下图面板）
2. **副图 1**：指标线（图上与策略一致：`entry_high`/`exit_low`/`atr`/`close`…）
3. **副图 2**：净值曲线 + 回撤曲线
4. **交易明细表**：trade_id / symbol / 时间 / side / price / qty / commission / slippage

## 6. 配置段

v2.1 延续"代码内配置对象"风格，无独立 .yaml/.toml。可视化相关配置集中在**构造参数**与**策略覆写**两层：

| 配置项 | 载体 | 默认 | 说明 |
|--------|------|------|------|
| `recorder` | `BacktestEngine(recorder=...)` | `None`（不记录） | 传入 `BacktestRecorder()` 即开启全程记录；缺省完全不影响回测 |
| `symbol` / `title` | `render_html(..., symbol, title)` | `""` / 固定标题 | 导出 HTML 的标题与标的 |
| `indicator_values()` | 各策略覆写 | `{}` | 决定图上画哪几条指标线（必须=策略实际计算） |
| 输出前缀 | `scripts/visualize_backtest.py` 的 `out_prefix` | `outputs/visual` | 控制 HTML/JSON/CSV 输出路径 |

示例开启可视化：

```python
from visualization.recorder import BacktestRecorder
from visualization.exporter import VisualExporter

recorder = BacktestRecorder()
engine = BacktestEngine(..., recorder=recorder)   # 唯一改动点
engine.run(bars)
VisualExporter(recorder).render_html("outputs/visual.html", symbol="TEST001")
```

## 7. 端到端用法

```bash
python3 scripts/visualize_backtest.py
# 产物：
#   outputs/visual.html        自包含可视化报告（离线可开）
#   outputs/visual.json        全量结构化记录
#   outputs/visual_equity.csv  净值/回撤 CSV
# 控制台输出：[check] 一致性自检结果
```

## 8. 一致性 / 验收（必须全部通过）

`tests/test_visualization.py` 覆盖以下断言：

| 验收项 | 断言 | 说明 |
|--------|------|------|
| **解耦** | 有无 Recorder 最终权益一致、成交数一致 | Recorder 绝不改变回测结果 |
| **买卖点 = Trade** | 成交记录条数/ID/方向/价格/数量 == `portfolio.trades` | 图上买卖点与入账逐条一致 |
| **图上指标 = 策略指标** | `indicator` 记录含 `entry_high/exit_low/atr`，且上轨 ≥ 下轨 | 指标来自策略 `indicator_values()`，非重算 |
| **净值 = Portfolio** | 净值末点 == `portfolio.account.equity` | 曲线最后一个点与最终权益一致 |
| **买卖分离** | `trade_buy`/`trade_sell` 数量 == Portfolio 买卖数，且方向正确 | 图上买/卖点分类正确 |
| **拒绝可追溯** | 每条 `risk_reject` 都带 `reason` | 风控拦截原因可查 |
| **JSON 往返** | 导出 dict 含 bars/trades/equity/signals，bars 数 == 输入 bar 数 | 结构化导出完整 |

运行：

```bash
python3 -m pytest tests/test_visualization.py -v
```

## 9. 多标的 / 回放 / 性能（增强方向，当前未实现）

- **多标的**：Recorder 各表记录带 `symbol` 字段，具备合并展示的数据基础；按标的分面板的渲染待实现。
- **回放控制器**：当前 `render_html` 为静态整页渲染。步进回放（逐 bar 播放 + 暂停 + 滑杆）属后续增强。
- **性能与存储**：全量内存记录，bar 量级大时内存占用随记录数线性增长；超大样本建议只记录关键事件或落盘中间态。当前 MVV 满足 ≤ 数千 bar 场景。

## 10. 最小可用版本（MVV）核对

需求文档的 MVV 已全部落地：

- [x] K 线 + 成交量
- [x] 均线/通道/ATR 指标叠加（来自策略实际计算）
- [x] 买卖点分离显示（信号 / 成交 分开，买入/卖出分开）
- [x] 净值曲线 + 回撤
- [x] 交易明细表
- [x] 导出自包含 HTML
