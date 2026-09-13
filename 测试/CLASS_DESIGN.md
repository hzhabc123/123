# CLASS_DESIGN.md

# Quant V2 类设计文档

---

# 设计原则

## 单一职责原则

一个类只负责一件事情。

例如：

* Strategy 负责产生信号
* Broker 负责执行订单
* Portfolio 负责管理资产
* RiskManager 负责风控

不要出现：

```python
Strategy.buy()
Strategy.sell()
Strategy.calculate_position()
```

这种违反职责分离的设计。

---

# 类关系图

```text
BaseStrategy
    │
    ├── MAStrategy
    ├── RSIStrategy
    ├── DonchianStrategy
    └── ETFRotationStrategy


Account
    │
    └── Portfolio
            │
            ├── Position
            └── Order


PositionSizer
    │
    ├── FixedSizer
    ├── PercentSizer
    └── ATRSizer


StopManager
    │
    ├── FixedStop
    ├── ATRStop
    └── TrailingStop


RiskManager

Broker

BacktestEngine

PerformanceAnalyzer
```

---

# data 模块

---

## DataFeed

### 作用

统一数据接口。

所有数据源必须实现同一接口。

---

### 属性

```python
symbol: str

start_date: datetime

end_date: datetime

data: DataFrame
```

---

### 方法

```python
load()
```

加载历史数据

---

```python
get_next_bar()
```

获取下一根K线

---

```python
reset()
```

重置游标

---

# strategy 模块

---

## BaseStrategy

抽象基类。

所有策略继承该类。

---

### 属性

```python
name: str

symbol: str

parameters: dict

current_position: int
```

---

### 方法

```python
on_init()
```

策略初始化

---

```python
on_bar(bar)
```

收到K线

---

```python
on_tick(tick)
```

收到Tick

---

```python
generate_signal()
```

生成信号

---

```python
on_finish()
```

回测结束

---

# MAStrategy

双均线策略

---

### 继承

```python
BaseStrategy
```

---

### 属性

```python
short_window

long_window

prices
```

---

### 方法

```python
calculate_ma()
```

---

```python
generate_signal()
```

金叉买入

死叉卖出

---

# RSIStrategy

RSI策略

---

### 继承

```python
BaseStrategy
```

---

### 属性

```python
rsi_period

overbought

oversold
```

---

### 方法

```python
calculate_rsi()
```

---

```python
generate_signal()
```

---

# DonchianStrategy

CTA突破策略

---

### 继承

```python
BaseStrategy
```

---

### 属性

```python
lookback_period
```

---

### 方法

```python
highest_high()
```

---

```python
lowest_low()
```

---

```python
generate_signal()
```

---

# portfolio 模块

---

## Account

账户对象

---

### 属性

```python
cash

available_cash

frozen_cash

equity

margin
```

---

### 方法

```python
deposit()
```

入金

---

```python
withdraw()
```

出金

---

```python
update_equity()
```

更新净值

---

# Position

持仓对象

---

### 属性

```python
symbol

qty

avg_price

market_price

market_value

unrealized_pnl

realized_pnl
```

---

### 方法

```python
update_price()
```

---

```python
update_position()
```

---

```python
close()
```

---

# Order

订单对象

---

### 属性

```python
order_id

symbol

side

price

qty

filled_qty

status

create_time
```

---

### 方法

```python
fill()
```

---

```python
cancel()
```

---

# Portfolio

组合管理器

---

### 属性

```python
account

positions

orders

trades
```

---

### 方法

```python
add_position()
```

---

```python
remove_position()
```

---

```python
update_position()
```

---

```python
calculate_market_value()
```

---

```python
calculate_equity()
```

---

```python
calculate_drawdown()
```

---

# broker 模块

---

## Broker

模拟交易所

---

### 属性

```python
commission_rate

slippage

portfolio
```

---

### 方法

```python
submit_order()
```

提交订单

---

```python
execute_order()
```

执行订单

---

```python
cancel_order()
```

撤单

---

```python
calculate_commission()
```

手续费

---

```python
calculate_slippage()
```

滑点

---

# risk 模块

---

## RiskManager

统一风控入口

---

### 属性

```python
max_position_pct

max_drawdown

max_daily_loss

max_consecutive_loss
```

---

### 方法

```python
check_order()
```

订单检查

---

```python
check_drawdown()
```

回撤检查

---

```python
check_daily_loss()
```

日亏损检查

---

```python
check_position_limit()
```

仓位限制

---

```python
can_trade()
```

允许交易判断

---

# PositionSizer

仓位管理抽象类

---

### 方法

```python
calculate_size()
```

---

# FixedSizer

固定手数

---

### 继承

```python
PositionSizer
```

---

### 属性

```python
fixed_qty
```

---

# PercentSizer

资金比例仓位

---

### 继承

```python
PositionSizer
```

---

### 属性

```python
position_pct
```

---

# ATRSizer

ATR动态仓位

---

### 继承

```python
PositionSizer
```

---

### 属性

```python
risk_pct

atr_multiplier
```

---

### 方法

```python
calculate_size()
```

公式：

风险资金 ÷ ATR风险

---

# StopManager

止损基类

---

### 方法

```python
check_stop()
```

---

# FixedStop

固定止损

---

### 继承

```python
StopManager
```

---

### 属性

```python
stop_loss_pct
```

---

# ATRStop

ATR止损

---

### 继承

```python
StopManager
```

---

### 属性

```python
atr_period

atr_multiplier
```

---

# TrailingStop

移动止损

---

### 继承

```python
StopManager
```

---

### 属性

```python
trail_pct
```

---

# backtest 模块

---

## BacktestEngine

回测引擎

---

### 属性

```python
datafeed

strategy

portfolio

broker

risk_manager

analyzer
```

---

### 方法

```python
run()
```

启动回测

---

```python
process_bar()
```

处理K线

---

```python
process_signal()
```

处理信号

---

```python
process_order()
```

处理订单

---

```python
update_portfolio()
```

更新账户

---

```python
generate_report()
```

生成报告

---

# optimizer 模块

---

## GridSearchOptimizer

参数优化器

---

### 属性

```python
parameter_grid
```

---

### 方法

```python
optimize()
```

---

```python
evaluate()
```

---

```python
rank_result()
```

---

# WalkForwardOptimizer

滚动验证优化器

---

### 属性

```python
train_window

test_window
```

---

### 方法

```python
split_dataset()
```

---

```python
optimize_train()
```

---

```python
evaluate_test()
```

---

```python
run()
```

---

# analyzer 模块

---

## PerformanceAnalyzer

绩效分析器

---

### 属性

```python
equity_curve

trade_log
```

---

### 方法

```python
calculate_return()
```

总收益率

---

```python
calculate_annual_return()
```

年化收益

---

```python
calculate_sharpe()
```

夏普率

---

```python
calculate_sortino()
```

Sortino

---

```python
calculate_max_drawdown()
```

最大回撤

---

```python
calculate_win_rate()
```

胜率

---

```python
calculate_profit_factor()
```

盈亏比

---

```python
generate_report()
```

输出最终绩效报告

---

# V3扩展预留

未来新增：

```python
StrategyManager

SignalManager

Allocator

Gateway

LiveEngine
```

无需修改现有类结构。

遵循开放封闭原则：

对扩展开放

对修改封闭
