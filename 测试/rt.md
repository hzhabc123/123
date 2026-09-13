# Quant V2 量化交易框架设计文档

## 项目目标

Quant V2 是一个面向股票、ETF、期货、加密货币的量化研究与交易框架。

设计目标：

* 统一回测与实盘接口
* 支持多策略运行
* 支持组合管理
* 支持风险控制
* 支持参数优化
* 支持未来扩展 AI 量化模块
* 支持股票与加密货币双市场

---

# 系统架构

```text
Data
 ↓
Strategy
 ↓
Signal
 ↓
RiskManager
 ↓
PositionSizer
 ↓
Order
 ↓
Broker
 ↓
Portfolio
 ↓
Analyzer
```

数据从 Data 模块进入系统，策略产生信号，风控审核信号，仓位管理计算下单数量，经 Broker 执行交易，Portfolio 更新账户状态，Analyzer 统计绩效。

---

# 文件结构

```text
quant/

├── data/
│
├── strategy/
│
├── broker/
│   └── broker.py
│
├── portfolio/
│   ├── account.py
│   ├── position.py
│   ├── order.py
│   └── portfolio.py
│
├── risk/
│   ├── risk_manager.py
│   ├── position_sizer.py
│   └── stop_manager.py
│
├── backtest/
│   └── engine.py
│
├── optimizer/
│   ├── grid_search.py
│   └── walk_forward.py
│
├── analyzer/
│
├── logs/
│   ├── trade_log.csv
│   └── order_log.csv
│
└── main.py
```

---

# data 模块

## 作用

负责所有市场数据获取与加载。

统一数据接口。

无论数据来自：

* CSV
* Binance
* OKX
* 掘金
* Tushare

策略层无需修改。

---

## 主要职责

### 历史数据加载

```python
load_history()
```

返回：

```python
DataFrame
```

---

### 实时数据推送

```python
get_latest_bar()
```

---

### 数据缓存

避免重复读取磁盘。

---

### 数据标准化

统一字段：

```python
datetime
open
high
low
close
volume
```

---

# strategy 模块

## 作用

产生交易信号。

策略永远不负责：

* 下单
* 风控
* 资金管理

策略只负责判断：

```python
BUY
SELL
HOLD
```

---

## 策略开发规范

所有策略继承：

```python
BaseStrategy
```

统一接口：

```python
on_init()

on_bar()

on_tick()

on_finish()
```

---

## 推荐策略路线

### 第一阶段

双均线

```text
MA5
MA20
```

---

### 第二阶段

RSI

```text
RSI < 30 买入

RSI > 70 卖出
```

---

### 第三阶段

Donchian Breakout

```text
突破20日最高价买入

跌破20日最低价卖出
```

---

### 第四阶段

ETF轮动

```text
选择动量最高ETF
```

---

### 第五阶段

多因子选股

```text
价值
质量
成长
动量
```

---

# broker 模块

文件：

```text
broker.py
```

---

## 作用

模拟交易所。

负责：

* 撮合订单
* 扣除手续费
* 处理滑点
* 更新现金

---

## 核心职责

### 买入

```python
buy()
```

---

### 卖出

```python
sell()
```

---

### 撮合

支持：

```text
市价单
限价单
止损单
```

---

### 手续费

例如：

```text
0.1%
```

---

### 滑点

例如：

```text
0.05%
```

---

# portfolio 模块

核心中的核心。

---

# account.py

账户对象。

保存：

```python
cash
equity
available
margin
```

---

## 示例

```python
cash = 100000
```

---

# position.py

持仓对象。

记录：

```python
symbol
qty
avg_price
market_value
unrealized_pnl
realized_pnl
```

---

# order.py

订单对象。

记录：

```python
order_id
symbol
side
price
qty
status
```

---

订单状态：

```text
NEW

FILLED

PART_FILLED

CANCELLED
```

---

# portfolio.py

组合管理器。

负责：

```text
多标的管理
持仓统计
资产统计
收益统计
```

---

## 示例

```python
BTCUSDT

ETHUSDT

沪深300ETF
```

同时持仓。

---

# risk 模块

系统最重要模块。

多数散户不是策略亏钱。

而是风控失效。

---

# risk_manager.py

风控中心。

所有订单必须经过：

```python
risk.check()
```

---

## 风控规则

### 单笔风险

```text
账户资金 × 1%
```

---

### 最大仓位

```text
20%
```

---

### 最大回撤

```text
15%
```

---

### 日亏损

```text
3%
```

---

### 连续亏损

```text
5次
```

停止交易。

---

# position_sizer.py

仓位管理器。

决定买多少。

---

## 固定比例仓位

```text
10%
```

---

## ATR仓位管理

计算公式：

风险资金 ÷ ATR

---

适用于：

```text
CTA
趋势跟踪
加密货币
```

---

# stop_manager.py

止损管理器。

---

## 固定止损

```text
-5%
```

---

## ATR止损

```text
2 ATR
```

---

## 移动止损

盈利后跟踪价格。

保护利润。

---

# backtest 模块

文件：

```text
engine.py
```

---

## 作用

驱动整个回测系统。

---

## 流程

```text
读取K线

↓

执行策略

↓

生成信号

↓

风险检查

↓

计算仓位

↓

生成订单

↓

执行交易

↓

更新账户

↓

记录结果
```

---

## 输出

```python
equity_curve
```

账户净值曲线。

---

# optimizer 模块

用于参数优化。

---

# grid_search.py

网格搜索。

---

## 示例

```python
MA(
  short=5,
  long=20
)
```

遍历：

```text
5
10
20
30
```

寻找最佳参数。

---

## 输出指标

```text
收益率

夏普率

最大回撤

Calmar
```

---

# walk_forward.py

滚动验证。

防止过拟合。

---

## 流程

```text
训练

↓

优化

↓

测试

↓

滚动
```

---

## 示例

```text
训练

2020-2022

测试

2023
```

---

然后：

```text
训练

2021-2023

测试

2024
```

---

# analyzer 模块

绩效分析模块。

---

## 输出指标

### 收益率

```text
Total Return
```

---

### 年化收益

```text
Annual Return
```

---

### 夏普率

```text
Sharpe Ratio
```

---

### Sortino

只考虑下行波动。

---

### Calmar

收益与回撤比。

---

### 最大回撤

```text
Max Drawdown
```

---

### 胜率

```text
Win Rate
```

---

### 盈亏比

```text
Profit Factor
```

---

### 平均持仓时间

```text
Holding Time
```

---

# logs 模块

交易审计模块。

---

# trade_log.csv

记录成交。

字段：

```text
datetime
symbol
side
price
qty
commission
pnl
```

---

# order_log.csv

记录订单。

字段：

```text
datetime
order_id
symbol
status
price
qty
```

---

# main.py

系统入口。

---

## 回测模式

```python
python main.py
```

---

## 流程

```text
加载数据

↓

初始化策略

↓

初始化账户

↓

启动回测

↓

输出绩效

↓

生成报告
```

---

# V2开发优先级

第一优先级：

* Portfolio
* RiskManager
* PositionSizer

第二优先级：

* Donchian Strategy
* ATR Stop

第三优先级：

* Grid Search
* Walk Forward

第四优先级：

* Binance接口
* OKX接口

---

# 核心理念

优秀策略只能解决赚钱问题。

优秀风控才能解决长期活下来的问题。

系统设计顺序：

策略 → 风控 → 组合 → 优化 → 实盘

而不是：

策略 → 实盘 → 爆仓。
