对于你要做的 **V2量化交易系统（回测 + 实盘统一架构）**，建议按照机构级量化系统的职责进行拆分。

# 整体目录结构

```text
quant_v2/

├── main.py

├── config/
│   └── settings.py

├── data/
│   ├── bar.py
│   ├── data_source.py
│   ├── data_manager.py
│   └── loader.py

├── strategy/
│   ├── base_strategy.py
│   ├── strategy_manager.py
│   └── ma_cross.py

├── broker/
│   ├── broker.py
│   ├── backtest_broker.py
│   ├── live_broker.py
│   └── matcher.py

├── portfolio/
│   ├── account.py
│   ├── position.py
│   ├── order.py
│   ├── trade.py
│   └── portfolio.py

├── engine/
│   ├── event_engine.py
│   ├── backtest_engine.py
│   └── live_engine.py

├── risk/
│   ├── risk_manager.py
│   └── rules.py

├── performance/
│   ├── analyzer.py
│   ├── metrics.py
│   └── report.py

├── event/
│   ├── event.py
│   └── event_type.py

├── persistence/
│   ├── database.py
│   ├── repository.py
│   └── models.py

├── utils/
│   ├── logger.py
│   ├── time_utils.py
│   └── common.py

└── tests/
```

---

# 1. main.py

系统启动入口

```python
main()
```

职责：

* 加载配置
* 创建引擎
* 注册策略
* 启动回测
* 输出结果

不允许出现：

```python
下单逻辑
风控逻辑
策略逻辑
```

---

# 2. config

配置中心

```text
config/
└── settings.py
```

---

## settings.py

统一管理参数

例如：

```python
RUN_MODE = "backtest"

INITIAL_CAPITAL = 100000

COMMISSION = 0.0003

SLIPPAGE = 0.0001
```

未来支持：

```python
yaml
json
env
数据库
```

---

# 3. data

数据层

负责所有行情数据管理。

---

## bar.py

K线对象

```python
Bar
```

保存：

```python
datetime
open
high
low
close
volume
```

例如：

```python
Bar(
    symbol="000001.SZ",
    close=10.5
)
```

---

## data_source.py

数据源抽象

统一接口

```python
class DataSource
```

实现：

```python
CSV
MySQL
MongoDB
掘金
Tushare
Binance
```

---

## data_manager.py

缓存数据

避免重复读取。

功能：

```python
get_bar()

get_history()

get_latest()
```

---

## loader.py

加载历史数据

例如：

```python
csv -> Bar
```

---

# 4. strategy

策略层

系统核心。

---

## base_strategy.py

所有策略基类

```python
class BaseStrategy
```

统一接口：

```python
on_init()

on_bar()

on_order()

on_trade()
```

---

## strategy_manager.py

管理多个策略

负责：

```python
注册
启动
停止
广播行情
```

---

## ma_cross.py

双均线策略

例如：

```python
MA5
MA20
```

金叉买入

死叉卖出

---

# 5. broker

模拟券商层

负责成交。

---

## broker.py

Broker抽象类

统一接口

```python
submit_order()

cancel_order()

match()
```

---

## backtest_broker.py

回测券商

负责：

```python
模拟成交

手续费

滑点
```

---

## live_broker.py

实盘券商

负责连接：

```python
掘金
CTP
Binance
```

---

## matcher.py

撮合器

负责：

```python
订单撮合
```

例如：

```python
限价单

市价单
```

---

# 6. portfolio

账户层

系统最重要模块之一。

---

## account.py

账户对象

保存：

```python
现金

总资产

冻结资金
```

---

## position.py

持仓对象

保存：

```python
股票代码

持仓数量

成本价

浮盈亏
```

---

## order.py

订单对象

保存：

```python
订单号

方向

价格

数量

状态
```

状态：

```python
NEW
FILLED
CANCELLED
```

---

## trade.py

成交对象

保存：

```python
成交价格

成交数量

成交时间
```

---

## portfolio.py

组合管理器

负责：

```python
更新持仓

更新账户

计算市值
```

---

# 7. engine

交易引擎

整个系统大脑。

---

## event_engine.py

事件引擎

负责：

```python
事件队列

事件分发
```

典型事件：

```python
BAR

ORDER

TRADE

TIMER
```

---

## backtest_engine.py

回测引擎

流程：

```text
读取K线
   ↓
发送BAR事件
   ↓
策略计算
   ↓
产生订单
   ↓
Broker撮合
   ↓
更新账户
```

---

## live_engine.py

实盘引擎

流程：

```text
实时行情
   ↓
策略
   ↓
下单
   ↓
交易所
```

---

# 8. risk

风控模块

机构级系统必须有。

---

## risk_manager.py

统一风控入口

检查：

```python
订单数量

仓位比例

资金限制
```

---

## rules.py

具体风控规则

例如：

```python
最大仓位 20%

单笔亏损 2%

日亏损 5%
```

---

# 9. performance

绩效分析

回测结束后使用。

---

## analyzer.py

绩效分析入口

---

## metrics.py

计算指标

包括：

```python
收益率

年化收益

夏普比率

最大回撤

胜率

盈亏比
```

---

## report.py

生成报告

输出：

```python
html

pdf

excel
```

---

# 10. event

事件定义

---

## event_type.py

事件枚举

```python
BAR

ORDER

TRADE

ACCOUNT

POSITION
```

---

## event.py

事件对象

```python
Event(
    type=BAR,
    data=bar
)
```

---

# 11. persistence

持久化层

未来实盘必须有。

---

## database.py

数据库连接

支持：

```python
MySQL

PostgreSQL

SQLite
```

---

## repository.py

统一数据访问层

类似DAO。

---

## models.py

ORM模型

例如：

```python
OrderModel

TradeModel

PositionModel
```

---

# 12. utils

工具类

---

## logger.py

统一日志

```python
INFO

WARNING

ERROR
```

---

## time_utils.py

时间处理

例如：

```python
交易日判断
```

---

## common.py

公共函数

例如：

```python
round_price()

generate_order_id()
```

---

# V2 最核心的数据流

```text
Bar
 │
 ▼
Strategy
 │
 ▼
Order
 │
 ▼
Broker
 │
 ▼
Trade
 │
 ▼
Portfolio
 │
 ▼
Performance
```

这是后续所有代码设计都应该严格遵守的主链路。这样未来从单策略回测扩展到股票、期货、加密货币、多策略组合时，几乎不需要重构核心架构。
