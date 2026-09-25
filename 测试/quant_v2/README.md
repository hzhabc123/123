# Quant V2 量化回测系统

## 项目概述

Quant V2 是一个模块化的量化回测框架，采用事件驱动架构，支持多标的、多策略、多时间框架回测。

## 核心架构

```
┌─────────────────────────────────────────────────────────────┐
│                        用户层                                │
│  - main.py (入口)                                           │
│  - 策略配置                                                  │
└────────────────────┬────────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────────┐
│                      引擎层 (engine/)                        │
│  - BacktestEngine (回测引擎)                                │
│  - EventEngine (事件引擎)                                   │
└────────────────────┬────────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────────┐
│                     策略层 (strategy/)                       │
│  - BaseStrategy (策略基类)                                  │
│  - DonchianStrategy (唐奇安通道策略)                        │
│  - DualMAStrategy (双均线策略)                              │
└────────────────────┬────────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────────┐
│                     信号层 (signal/)                         │
│  - Signal (交易信号)                                        │
└────────────────────┬────────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────────┐
│                    风控层 (risk/)                            │
│  - RiskManager (风险管理器)                                 │
│    - 回撤控制                                                │
│    - 日亏损控制                                              │
│    - 连续亏损控制                                            │
│  - PositionSizer (仓位管理器)                               │
│    - FixedSizer (固定数量)                                  │
│    - PercentSizer (固定比例)                                │
│    - ATRSizer (ATR动态仓位)                                 │
│  - StopManager (止损管理器)                                 │
│    - 固定止损                                                │
│    - ATR止损                                                 │
│    - 移动止损                                                │
└────────────────────┬────────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────────┐
│                   组合层 (portfolio/)                        │
│  - Portfolio (组合管理器)                                   │
│  - Account (账户)                                           │
│  - Position (持仓)                                          │
│  - Order (订单)                                             │
│  - Trade (成交)                                             │
│  - Ledger (账本)                                            │
└────────────────────┬────────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────────┐
│                   经纪层 (broker/)                           │
│  - BacktestBroker (回测经纪商)                              │
│  - FeeModel (费用模型)                                      │
│  - OrderMatcher (订单撮合器)                                │
└────────────────────┬────────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────────┐
│                   数据层 (data/)                             │
│  - Bar (K线数据)                                            │
│  - Tick (逐笔数据)                                          │
│  - DataSource (数据源接口)                                  │
│  - DataManager (数据管理器)                                 │
└────────────────────┬────────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────────┐
│                   核心层 (core/)                             │
│  - enums (枚举定义)                                         │
│  - exceptions (异常定义)                                    │
│  - Clock (时钟)                                             │
│  - Calendar (交易日历)                                      │
│  - Instrument (合约元数据)                                  │
└─────────────────────────────────────────────────────────────┘
```

## 已实现模块

### ✅ 核心层 (core/)
- [x] `enums.py` - 统一枚举定义（OrderStatus, Side, SignalDirection等）
- [x] `exceptions.py` - 异常体系
- [x] `clock.py` - 时钟管理
- [x] `calendar.py` - 交易日历
- [x] `instrument.py` - 合约元数据

### ✅ 数据层 (data/)
- [x] `bar.py` - K线数据对象（Bar, BarFlags, Tick）
- [x] `data_source.py` - 数据源抽象接口（AbstractDataSource）
- [x] `akshare_source.py` - 免费真实行情源（akshare，新浪/东财，A股日线）
- [x] `gm_source.py` - 掘金量化数据源（GM，apikey接入）
- [x] `data_manager.py` - 数据管理器（缓存 + 多源注册）

### ✅ 信号层 (signals/)
- [x] `trading_signal.py` - 交易信号对象（Signal, SignalDirection）

### ✅ 策略层 (strategy/)
- [x] `base_strategy.py` - 策略基类（支持绑定Portfolio读取真实持仓）
- [x] `donchian.py` - 唐奇安通道策略（含ATR止损）
- [x] `ma_cross.py` - 双均线交叉策略（金叉/死叉）
- [x] `bollinger.py` - 布林带均值回归策略
- [x] `rsi.py` - RSI超买超卖策略
- [x] `turtle.py` - 海龟交易法（突破入场 + 2N止损）
- [x] `momentum.py` - 动量策略

### ✅ 风控层 (risk/)
- [x] `risk_manager.py` - 风险管理器（回撤/日亏损/连续亏损/仓位比例）
- [x] `position_sizer.py` - 仓位管理器（Fixed/Percent/ATR）
- [x] `stop_manager.py` - 止损管理器（固定/ATR/移动）

### ✅ 组合层 (portfolio/)
- [x] `portfolio.py`, `account.py`, `position.py`, `order.py`, `trade.py`, `ledger.py`

### ✅ 优化器 (optimizer/)
- [x] `optimizer.py` - 参数优化（GridSearch + WalkForward）

### ✅ 经纪/引擎/绩效/事件
- [x] `broker/` - BacktestBroker、FeeModel、OrderMatcher（含一字板规则）
- [x] `engine/` - BacktestEngine、EventEngine
- [x] `performance/` - PerformanceAnalyzer、Report Generator
- [x] `event/` - Event、EventType

### ⏳ 待实现
- [ ] `persistence/` 持久化（Database、Repository）

## 快速开始

```bash
cd /Coze/Drive/扣子/quant_v2

# 模拟数据回测（唐奇安）
python3 main.py

# 真实行情回测（akshare 拉取 A股日线，默认贵州茅台 2024）
python3 scripts/real_backtest.py 600519 20240101 20241231

# 真实行情 + 常见策略库擂台对比（多标的 × 5策略）
python3 scripts/strategy_compare.py

# 运行全部测试
python3 -m pytest tests/ -q
```

## 设计原则

1. **模块化**：每个功能独立模块，低耦合高内聚
2. **事件驱动**：基于事件的架构，支持实盘和回测
3. **防前视偏差**：严格的数据访问控制
4. **可扩展**：易于添加新策略、新数据源、新经纪商
5. **完整的风控**：多层风险控制机制

## 与 V1 的主要改进

1. **架构升级**：从简单的线性流程升级到事件驱动架构
2. **风控增强**：新增回撤控制、日亏损控制、连续亏损控制
3. **仓位管理**：新增PositionSizer，支持多种仓位计算策略
4. **止损管理**：新增StopManager，支持ATR止损、移动止损
5. **参数优化**：新增GridSearch和WalkForward验证
6. **多标的支持**：Portfolio支持多标的同时管理

## 下一步计划

1. 完善 `persistence/` 持久化模块（数据库回测结果存储）
2. 增加多标的组合级回测（资产配置层面）
3. 接入掘金/同花顺 apikey 实盘仿真
4. 参数优化与策略组合（GridSearch 已就绪）

## 技术栈

- Python 3.8+
- 数据类（dataclasses）
- 枚举（enum）
- 标准库为主，最小依赖

## 文件结构

```
quant_v2/
├── core/           # 核心层（枚举、异常、日历等）
├── data/           # 数据层（Bar、Tick、数据源）
├── signals/        # 信号层（交易信号）
├── strategy/       # 策略层（策略基类、具体策略）
├── risk/           # 风控层（风险管理、仓位、止损）
├── portfolio/      # 组合层（账户、持仓、订单、成交）
├── broker/         # 经纪层
├── engine/         # 引擎层
├── performance/    # 绩效层
├── optimizer/      # 优化器（网格搜索、WalkForward）
├── event/          # 事件层
├── persistence/    # 持久化层（待实现）
├── utils/          # 工具函数
├── tests/          # 测试
├── config/         # 配置文件
├── scripts/        # 周期脚本（真实回测、策略对比）
└── main.py         # 主入口
```

## 许可证

MIT License
