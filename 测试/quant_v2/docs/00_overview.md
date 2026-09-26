---
title: Quant V2 系统总览
version: 2.0
tags: [量化, 回测, 架构, 数据流, 模块划分, quant_v2]
summary: Quant V2 量化回测系统的整体架构、模块分层与完整数据流，用于快速定位各模块职责与协作关系。
---

# Quant V2 系统总览

## 一句话定位

Quant V2 是一个**事件驱动 + 分层模块化**的 A 股量化回测框架，主打防前视偏差，支持多标的、多策略、多数据源。V2 当前以**日线回测 + 直接调用驱动**为主，保留事件引擎接口。

## 模块分层

自下而上（数据源 → 核心模型 → 业务分层 → 引擎 → 输出）：

| 层 | 目录 | 职责 | 状态 |
|---|---|---|---|
| 核心层 | `core/` | 枚举、异常、时钟、日历、合约元数据 | ✅ 已实现 |
| 数据层 | `data/` | Bar/Tick、数据源抽象、acshare/GM 适配、DataManager 缓存 | ✅ 已实现 |
| 信号层 | `signals/` | 交易信号对象 | ✅ 已实现 |
| 策略层 | `strategy/` | 策略基类 + 5 个常用策略 | ✅ 已实现 |
| 风控层 | `risk/` | 风险校验、仓位管理、止损管理 | ✅ 已实现 |
| 组合层 | `portfolio/` | 账户、持仓、订单、成交、账本 | ✅ 已实现 |
| 经纪层 | `broker/` | 费用模型、订单撮合、回测经纪商 | ✅ 已实现 |
| 事件层 | `event/` | 事件引擎（订阅/发布） | ✅ 已实现 |
| 引擎层 | `engine/` | 回测引擎主循环 | ✅ 已实现 |
| 绩效层 | `performance/` | 绩效分析、报告生成 | ✅ 已实现 |
| 优化器 | `optimizer/` | 网格搜索、Walk-Forward | ✅ 已实现 |
| 持久化 | `persistence/` | 回测结果存储 | ⏳ 占位，待实现 |
| 实盘层 | — | 网关、对账、实盘撮合 | 🚧 V3 规划，未实现 |

> 说明：`signal/`（旧名）已更名为 `signals/`，避免与 Python 标准库 `signal` 冲突。所有策略统一从 `signals.trading_signal` 导入 `Signal`。

## 完整数据流（回测）

```
DataBar 序列
   │
   ▼
BacktestEngine.run(bars)                    —— 逐根 bar 主循环
   │
   ├─① broker.match_orders(bar)             —— 撮合上一根 bar 留下的挂单
   │      └─ 成交回调 → portfolio.on_trade → strategy.on_trade
   │
   ├─② strategy.set_bar_context(bar, idx,   —— 注入历史（只给 idx 之前，防前视）
   │              history)
   ├─③ strategy.on_bar(bar) → 产生 Signal
   │
   └─④ 逐 Signal 处理  _process_signal
         ├─ 卖出时按持仓截断数量
         ├─ risk_manager.validate_signal    —— 风控校验
         ├─ 买入时按可用资金截断
         └─ broker.create_order(...)        —— 默认市价单，下一 bar 开盘成交
   │
   ├─⑤ 更新持仓市值 → 记录净值曲线
   │
   ▼
_summarize() → {bars, trades, orders, final_equity, total_return, rejected}
```

## 信号到成交的关键时序（防前视核心）

| 阶段 | 时刻 | 价格依据 |
|---|---|---|
| 策略产生信号 | T 日收盘后 | 仅用 ≤ T 日 bar（`history = bars[:index]`） |
| 订单入队 | T 日 | 不成交 |
| 撮合成交 | **T+1 日（下一交易日）** | 市价单按 **T+1 开盘价**；限价单按 T+1 区间 |
| 一字板例外 | T+1 为一字板 | 一字涨停买单拒、一字跌停卖单拒 |

**必须禁止**：使用当前 bar 收盘价作为当前信号当根成交价（产生未来函数）。

## 关键入口

```bash
# 模拟数据回测（唐奇安）
python3 main.py

# 真实行情回测（akshare，默认茅台 2024）
python3 scripts/real_backtest.py 600519 20240101 20241231

# 真实行情 × 5 策略对比
python3 scripts/strategy_compare.py

# 全量测试
python3 -m pytest tests/ -q
```

## 快速定位

- 想知道订单如何撮合 → 见 `broker/matcher.py` + 本文档 §04 回测成交前提
- 想知道风控规则与顺序 → `risk/risk_manager.py` + `docs/05_risk_position_stop.md`
- 想知道策略怎么写 → `docs/02_interfaces.md`
- 想知道绩效指标口径 → `docs/07_performance_optimizer.md`