---
title: Quant V2 组合 / 经纪商 / 引擎
version: 2.0
tags: [量化, Portfolio, Broker, Engine, 账本, 撮合, 成交回调, 主循环, 资金结算]
summary: 组合管理（持仓/账户/账本）、经纪商（撮合/费用/成交）、回测引擎主循环三者的职责、协作方式与资金结算口径。
---

# Quant V2 组合 / 经纪商 / 引擎

本文档串联三者：**组合承载状态、经纪商执行交易、引擎驱动时间推进**。

## 1. Portfolio — 组合管理器（`portfolio/portfolio.py`）

管理多标的持仓、账户、订单、成交。

```python
portfolio = Portfolio(initial_cash=100000.0)
portfolio.account            # Account（现金/权益/账本）
portfolio.positions          # Dict[symbol, Position]
portfolio.orders / trades    # 历史订单/成交
get_position(symbol) -> Position|None
get_or_create_position(symbol) -> Position
add_order / add_trade
on_trade(trade)              # 成交回调：更新持仓/现金/账本
update_market_value(symbol, last_price)   # 每bar末引擎调用
calculate_market_value() -> float          # 持仓市值总和
calculate_equity() -> float                # 总权益
ledger_entries() -> list
summary() -> str
```

> ⚠️ `initial_cash` 属性不存在！取初始资金请用 `portfolio.account.initial_cash`（曾导致 `AttributeError`）。

### on_trade 资金结算口径（重点）
| 方向 | 现金 | 持仓 |
|---|---|---|
| BUY 买入 | `cash -= (金额 + commission)` | 加仓：新成本 =(旧成本+金额)/新数量；`available_qty=qty` |
| SELL 卖出 | `cash += (金额 - commission)` | 减仓：数量减少；`realized_pnl += (卖价-均价)×数量`；清仓时均价归零 |

- 费用只扣 `commission`（`fee_breakdown.total`），**滑点不直接从现金扣**（已按比例算进 Fees）。
- 每次买入/卖出与费用各产生一条**账本流水**（`LedgerEntry`：`INITIAL/TRADE/FEE`）。

### 账本 Ledger
`portfolio/ledger.py` 提供 `LedgerEntry` + `LedgerEntryType`（INITIAL/TRADE/FEE/WITHDRAWAL/DEPOSIT/DIVIDEND/INTEREST/OTHER）。`Portfolio._record_initial` 写入首条 INITIAL 流水。

## 2. Account — 账户（`portfolio/account.py`）

| 字段 | 说明 |
|---|---|
| `initial_cash` / `cash` | 初始/当前可用现金 |
| `equity` | 总权益（现金+市值） |
| `frozen_cash` | 冻结资金（挂单预占） |
| `margin` | 占用保证金（期货） |
| `leverage` | 杠杆 |
| `ledger` | 账本流水列表 |

方法：`deposit/withdraw/freeze_cash/unfreeze_cash/update_equity`；属性 `available_cash=cash-frozen`、`total_asset=equity`。

> 注：V2 回测路径中冻结资金字段已预留，但 `on_trade` 直接改 `cash`，挂单资金冻结主要通过引擎资金截断兜底，未完全走 frozen 机制（见 `docs/03`）。

## 3. BacktestBroker — 回测经纪商（`broker/backtest_broker.py`）

职责：收单入队 → 撮合 → 算费 → 生成 Trade → 回调 Portfolio。

```python
broker = BacktestBroker(fee_model, matcher, on_trade_callback)
broker.create_order(symbol, side, order_type, price, qty, stop_price=0, strategy_id="") -> Order
broker.submit_order(order)     # qty<=0 直接 reject
broker.match_orders(bar) -> List[Trade]   # 引擎每bar调用
broker.cancel_order(order_id) / pending_orders(symbol) / all_orders() / get_order(order_id)
```

**match_orders 流程**：
1. 停牌 bar → 返回空，挂单保持。
2. 遍历挂单快照 → `matcher.match(order, bar)`。
3. `REJECTED` → `order.reject(reason)`。
4. `FILLED/PART_FILLED` 且 `fill_qty>0` → `_create_trade`（`order.fill` + `fee_model.calculate` → `Trade`），回调 `on_trade_callback`。
5. IOC 未成交 → cancel；活跃单保留。
6. 返回本 bar 成交列表（`last_trades`）。

**Trade 生成**：`O{id}`/`T{id}` 全局递增；`trade_time = bar.datetime`；佣金取 `fees.total`，滑点取 `fees.slippage_cost`。

## 4. BacktestEngine — 回测引擎（`engine/backtest_engine.py`）

```python
engine = BacktestEngine(
    strategy, portfolio,
    broker=None, risk_manager=None, position_sizer=None,
    symbol="", lookback=500,
)
result = engine.run(bars, start_equity=True) -> dict
```

**初始化**：`strategy.set_portfolio(portfolio)`；`broker.on_trade_callback` 指向 `_on_trade`（调 `portfolio.on_trade` + `strategy.on_trade`）。

**run 主循环（每根 bar）**：
```
for index, bar in enumerate(bars):
    ① broker.match_orders(bar)          # 撮合上一根留下的挂单
    ② strategy.set_bar_context(bar, index, history[:index])   # 防前视
    ③ strategy.on_bar(bar)              # 策略产生信号
    ④ for signal in strategy.get_signals(): _process_signal(signal, bar)
    ⑤ portfolio.update_market_value(symbol, bar.close)
    ⑥ portfolio.calculate_equity()
    ⑦ 记录净值曲线 {datetime, equity, cash, market_value, close}
```

** _process_signal**：
- SHORT/HOLD → 跳过（现货不做空）
- 卖出：数量截断到持仓可用
- 风控：`risk_manager.validate_signal(signal, portfolio)` 失败 → 拒，送入 `rejected_signals`
- 买入：若 `target_qty` 超可用资金，截断为 `int(available_cash/price*0.98 //100*100)`
- 下单：`broker.create_order(symbol, side, order_type=signal.order_type or MARKET, price=..., qty, strategy_id=...)`

**结果与查询**：
- `run` 返回 `{bars, trades, orders, final_equity, total_return, rejected}`
- `get_equity_curve()` / `get_all_trades()` / `get_all_orders()` / `event_count` / `rejected_signals`
- `analyzer()` → 由净值曲线+成交构造 `PerformanceAnalyzer`

## 5. 三者协作时序（一次完整交易）

```
bar T（信号日）
  strategy.on_bar → 产生 BUY Signal
  engine._process_signal → 风控通过 → 资金截断
  broker.create_order(MARKET, qty) → submit_order 入队（挂单）
bar T+1（成交日）
  engine: broker.match_orders(bar)
    matcher.match → FILLED @ bar.open
    _create_trade → Trade + fee
    on_trade_callback → portfolio.on_trade（更新现金/持仓/账本）
  portfolio.update_market_value / calculate_equity
```

## 6. 关键坑位备忘

| 坑 | 说明 |
|---|---|
| `portfolio.initial_cash` 不存在 | 用 `portfolio.account.initial_cash` |
| 高价股风控拦截 | 见 `docs/05`，放宽 `max_single_trade_amount` |
| 结算只扣 commission | 滑点不进现金，量级小可忽略，精确口径注意 |
| SHORT 被忽略 | 现货引擎不处理 SHORT/COVER |
| frozen 机制未走通 | 资金截断由引擎兜底 |