---
title: Quant V2 回测成交前提与时间语义
version: 2.0
tags: [量化, 回测, 成交假设, 时间语义, 防前视, 撮合, 涨跌停, 滑点, 费用]
summary: 回测撮合规则、价格假设、防前视偏差、时间/时钟语义与费用计算的完整约定。
---

# Quant V2 回测成交前提与时间语义

回测只是真实交易的**近似模型**。一切偏离现实的简化都是收入里的偏差，本文档把这些前提显式列出，避免“回测谦虚、实盘打脸”。

## 1. 撮合规则（以代码为准）

### 成交价（`broker/matcher.py::_determine_fill`）

| 订单类型 | 成交条件 | 成交价 |
|---|---|---|
| MARKET 市价 | 无条件可成交 | `bar.open`（下一交易日开盘价） |
| LIMIT 限价买 | `bar.low <= price` | `min(bar.open, price)` |
| LIMIT 限价卖 | `bar.high >= price` | `max(bar.open, price)` |
| STOP 止损买 | `bar.high >= stop_price` | `max(bar.open, stop_price)` |
| STOP 止损卖 | `bar.low <= stop_price` | `min(bar.open, stop_price)` |
| STOP_LIMIT | 触发后才判断限价 | trigger → limit 规则 |

未触发 → 状态保持 `NEW`（挂单保留，等后续 bar）。

### 其它前提

- **停牌拒单**：`bar.flags.is_suspended` → `REJECTED`，挂单保持原状
- **退市拒单**：`is_delisted` → `REJECTED`
- **涨跌停**（`_check_price_limit`，默认开启 `use_price_limit=True`）：
  - 一字涨停（买单）→ 拒：“一字涨停，买入无法成交”
  - 一字跌停（卖单）→ 拒：“一字跌停，卖出无法成交”
  - 一字板判据：优先用 `BarFlags.limit_up/limit_down`；无标记时按 `high == low` 且 close 相对 open 方向推断
- **流动性限制**：单笔可成交量 ≤ `bar.volume × volume_limit_ratio`（默认 10%）；不足则 `PART_FILLED`；`bar.volume<=0` 时不限制

## 2. 防前视 / 数据泄漏（核心铁律）

- **策略历史隔离**：`BaseStrategy.set_bar_context(bar, index, history)`，引擎只传 `history[:index]`（不含当前 bar），策略**永远无法看到未来**。
- **成交延后**：信号在 T 日收盘产生，订单 T 日只入队，**T+1 交易日才撮合**（市价单按 T+1 开盘价）。
- **显式调用优于隐式**：V2 默认直接调用（`broker.match_orders` → `strategy.on_bar` → `get_signals`），比隐式事件回调更可控、更不易漏；`event/` 仅作解耦参考。

**必须禁止**：
- ❌ 用 T 日收盘价给 T 日信号当根成交
- ❌ 在策略 on_bar 内读取 `index` 之后的 bar
- ❌ 用除权除息前/后的混价序列直接交易（需复权处理）

## 3. 时间/时钟语义

### 分层时钟

- **回测时钟** `core/clock.py::Clock(start_time)`：`now/start_time`、`advance(timedelta)`、`set_time`、`elapsed`。由引擎按 bar 推进。
- **实盘时钟** `LiveClock`：返回 `datetime.now()`（V3 用）。

### 交易日历（`core/calendar.py::TradingCalendar`）

**已实现**为占位：周一到周五为交易日，`holidays` 可扩展。
- `is_trading_day(dt)` / `next_trading_day` / `prev_trading_day` / `add_trading_days(dt, n)` / `trading_days_between` / `count_trading_days`
- `get_calendar(market)` 目前返回默认实例；**多市场真实日历注册是 TODO**。

> ⚠️ **已实现局限**：当前日历**不包含 A 股真实节假日**（春节/国庆等）。做含长假段的回测时，`next_trading_day` 会把节假日当作可交易日，导致撮合时点偏差。阶段回测或对节假敏感的策略请注意；接入真实交易日历（如 `exchange_calendars`）列入规划。

### 时间语义速记

| 时刻 | 含义 | 对应 bar |
|---|---|---|
| T | 信号产生日 | strategy.on_bar 处理的当前 bar |
| T+1 | 成交日 | 下一次 match_orders 撮合 |
| bar.datetime | 成交时间戳 | 撮合该 bar 的时间 |

## 4. 费用模型（`broker/fee_model.py`）

`FeeBreakdown`：`commission` 佣金、`stamp_tax` 印花税、`transfer_fee` 过户费、`sec_fee` SEC费、`ta_fee` TA费、`slippage_cost` 滑点、`impact_cost` 冲击。
- `.total` = 规费合计（**不含**滑点/冲击）
- `.all_in_cost` = total + 滑点 + 冲击

| 市场 | 佣金 | 印花税 | 其它 | 滑点 |
|---|---|---|---|---|
| A股 | 0.03% 双向，最低5元 | **0.05% 仅卖出** | 过户费 0.001% 双向 | 0.01% |
| 美股 | 0（按股数） | — | SEC费 0.00278% 仅卖 + TA费 | 0.02% |
| 加密 | taker 0.05% / maker 0.02% | — | — | 0.01% |

> 注：滑点在本模型中**以比例加进 FeeBreakdown**（近似计入成本），并非改成交价。市场冲击 `impact_cost` 字段预留，当前未计入。

## 5. 默认值与可调项汇总

| 参数 | 默认 | 位置 |
|---|---|---|
| 单笔流动性占比 `volume_limit_ratio` | 0.1 | OrderMatcher |
| 涨跌停开关 `use_price_limit` | True | OrderMatcher |
| A股佣金率/最低 | 0.0003 / 5元 | ChinaAFeeModel |
| 印花税率 | 0.0005 | ChinaAFeeModel |
| 滑点率 | 0.0001/0.0002/0.0001 | 各市场 |
| 策略历史窗口 `lookback` | 500 | BacktestEngine |
| 单笔金额上限 | 50000 | RiskConfig |

## 6. 已实现 vs 待完善

| 项 | 状态 |
|---|---|
| 市价单下一 bar 开盘成交 | ✅ |
| 限价/止损/止损限价撮合 | ✅ |
| 一字板买卖拒单 | ✅ |
| 停牌/退市拒单 | ✅ |
| 流动性比例限制 | ✅ |
| 滑点按比率计入 | ✅（近似） |
| 交易日历含真实节假日 | 🚧 TODO |
| 市场冲击 impact_cost | 🚧 预留未计 |
| 分时/分钟级撮合 | 🚧 规划 |
| 复权因子自动处理 | ✅ 字段预留，边界需人工保证 |