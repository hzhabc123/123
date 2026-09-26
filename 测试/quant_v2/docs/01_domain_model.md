---
title: Quant V2 领域模型
version: 2.0
tags: [量化, 领域模型, Bar, Signal, Order, Trade, Position, Account, Instrument, Event]
summary: 定义 Bar、Signal、Order、Trade、Position、Account、Instrument、Event 等核心对象及其职责、关键字段与生命周期。
---

# Quant V2 领域模型

本文档定义系统核心对象，是理解其它文档的基础。**每个对象都在真实代码中可查**（目录见各节）。

## 1. Bar — K线数据（`data/bar.py`）

标准 OHLCV 结构，所有数据源统一转换为此对象。

| 字段 | 类型 | 说明 |
|---|---|---|
| `symbol` | str | 标的代码 |
| `datetime` | datetime | 时间戳 |
| `open/high/low/close` | float | OHLC |
| `volume` | float | 成交量 |
| `amount` | float | 成交额 |
| `flags` | BarFlags | 附加标记位 |
| `adj_factor` | float | 复权因子（默认1.0） |
| `open_interest` | float | 持仓量（期货用） |

**BarFlags 标记位**：`is_suspended`(停牌) / `is_st`(ST) / `is_delisted`(退市) / `limit_up`(涨停) / `limit_down`(跌停) / `is_ex_dividend`(除权除息)。

常用属性：`mid`、`typical_price`、`range`(振幅)、`body`(实体)、`is_bullish/is_bearish`。

另有 `Tick`（逐笔/快照）：含 `last/bid/ask` 价与量、`mid_price`、`spread`、`spread_bps`。

## 2. Signal — 交易信号（`signals/trading_signal.py`）

策略的输出，**只是“意图”，不直接下单**。

| 字段 | 说明 |
|---|---|
| `symbol` | 标的 |
| `direction` | SignalDirection：BUY/SELL/HOLD/SHORT/COVER |
| `price` | 信号参考价（当前 bar close） |
| `timestamp` | 信号时间 |
| `strategy_id` | 产生信号的策略名 |
| `strength` | 信号强度 [0,1] |
| `reason` | 信号原因（可读） |
| `target_qty` | 目标数量（可选；为空则由 PositionSizer 计算） |
| `order_type` | 建议订单类型（可选） |

派生属性：`is_buy`(BUY/COVER)、`is_sell`(SELL/SHORT)、`is_entry`(BUY/SHORT)、`is_exit`(SELL/COVER)。

> ⚠️ SHORT/HOLD 方向当前在回测引擎中不产生订单（现货不做空，见 `engine/backtest_engine.py::_process_signal`）。

## 3. Order — 订单（`portfolio/order.py`）

提交给 Broker 的委托，含完整生命周期。

| 字段 | 说明 |
|---|---|
| `order_id` | 订单号（`O000001` 递增） |
| `symbol/side/order_type/price/qty` | 交易要素 |
| `status` | OrderStatus |
| `filled_qty/avg_price` | 成交进度 |
| `stop_price` | 止损/止盈触发价 |
| `time_in_force` | GTC/IOC/FOK/DAY |

**关键枚举**（`core/enums.py`）：
- `OrderStatus`: NEW → PART_FILLED → FILLED；另有 CANCELLED/REJECTED/EXPIRED
- `OrderType`: MARKET / LIMIT / STOP / STOP_LIMIT
- `Side`: BUY / SELL
- `TimeInForce`: GTC / IOC / FOK / DAY

## 4. Trade — 成交（`portfolio/trade.py`）

Broker 撮合后的结果，已扣除费用。

| 字段 | 说明 |
|---|---|
| `trade_id/order_id` | 成交号（`T000001`）/ 关联订单号 |
| `symbol/side/price/qty` | 成交要素 |
| `commission/slippage` | 费用 |
| `trade_time` | 成交时间（= bar.datetime） |
| `fee_breakdown` | FeeBreakdown 明细 |

派生：`notional`(成交额)、`total_cost`(费用合计)、`net_amount`(净金额，买负卖正)。

## 5. Position — 持仓（`portfolio/position.py`）

单个标的当前头寸。

| 字段 | 说明 |
|---|---|
| `symbol` | 标的 |
| `side` | PositionSide：LONG/SHORT |
| `qty/available_qty/frozen_qty` | 数量、可用、冻结（T+1） |
| `avg_price` | 平均成本 |
| `market_price/market_value` | 市值刷新 |
| `unrealized_pnl/realized_pnl` | 未实现/已实现盈亏 |

核心方法：`update_price`（重算市值盈亏）、`update_position`（支持加/减仓与反向）、`close`。属性：`is_long/is_short/is_flat`、`direction_multiplier`。

## 6. Account — 账户（`portfolio/account.py`）

| 字段 | 说明 |
|---|---|
| `initial_cash/cash` | 初始/当前现金 |
| `frozen_cash` | 冻结资金（挂单占用） |
| `equity` | 总权益 |
| `margin` | 占用保证金（期货） |
| `leverage` | 杠杆 |
| `ledger` | 账本流水 |

方法：`deposit/withdraw/freeze_cash/unfreeze_cash/update_equity`；属性 `available_cash`(cash-frozen)、`total_asset`。

## 7. Instrument — 合约元数据（`core/instrument.py`）

统一多标的基础信息：`symbol/asset_class/exchange/currency`、`lot_size/tick_size/multiplier`（手/价档/乘数）、`price_precision/qty_precision`、`t_plus`(T+N)、`shortable`、`trading_hours`、`calendar`、期货 `margin_rate/expiry_date`、加密 `funding_interval`。

方法：`round_price/round_qty/calc_notional/calc_margin`。内置示例：`301313`(A股)、`BTCUSDT`(加密)。

## 8. Event — 事件（`event/event_engine.py`）

事件驱动核心对象：`event_type`(EventType) + `data` + `timestamp` + `sender`。

`EventType`（`core/enums.py`）：BAR / TICK / ORDER / TRADE / ACCOUNT / POSITION / TIMER / RISK / LOG / SIGNAL。

## 对象生命周期总览

```
Instrument(元数据,静态)
Bar(行情输入)
   → BaseStrategy.on_bar → Signal(意图)
   → RiskManager(校验) → PositionSizer(数量)
   → Order(委托) → OrderMatcher + FeeModel(撮合结算)
   → Trade(结果) → Portfolio.on_trade → Position/Account 更新
   → PerformanceAnalyzer(绩效)
```

## 术语表速查

| 术语 | 英文 | 含义 |
|---|---|---|
| K线 | Bar | OHLCV 行情 |
| 信号 | Signal | 策略买卖意图 |
| 订单 | Order | 提交给 Broker 的委托 |
| 成交 | Trade | Broker 撮合结果 |
| 持仓 | Position | 某标的头寸 |
| 组合 | Portfolio | 多标的多策略集合 |
| 回撤 | Drawdown | 净值高点→低点跌幅 |
| 滑点 | Slippage | 预期价与成交价之差 |
| 手续费 | Commission | 交易成本 |