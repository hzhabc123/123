---
title: Quant V2 配置 / 测试 / 错误码
version: 2.0
tags: [量化, 配置, 测试, pytest, 错误码, 异常, RiskConfig, 数据源配置, 验收]
summary: 系统配置项（含数据源、风控、示例脚本）、测试清单与验收标准、异常/错误码体系与排查速查表。
---

# Quant V2 配置 / 测试 / 错误码

## 1. 配置体系

V2 以**代码内配置对象**为主（无统一 .yaml/.toml）。配置分布：

| 配置 | 载体 | 位置 |
|---|---|---|
| 数据源注册 | `DataManager({"akshare": AkshareDataSource()})` | 脚本内存 |
| 数据源 token | 构造时传 `token=...` 或 DataSource kwargs | 数据源配置 |
| 风控 | `RiskConfig(...)` + `RiskManager(config)` | `risk/risk_manager.py`（见 `docs/05`） |
| 仓位 | `create_sizer("atr", ...)` 等 | `risk/position_sizer.py` |
| 止损 | `create_*_stop(...)` + `StopManager` | `risk/stop_manager.py` |
| 费用 | `ChinaAFeeModel(...)` 等 | `broker/fee_model.py` |
| 策略参数 | 策略构造参数，如 `DonchianStrategy(entry_period=20...)` | 策略构造 |

> `config/` 目录当前仅占位（`__init__.py`）。统一配置文件模板属后续增强。

### 数据源凭据约定
- **akshare**：免费，无需 token（`AkshareDataSource()`）。
- **掘金 GM**：需 `GmDataSource(token="...")`，`DataSourceAuthError` 会在缺 token 时抛出。
- `_check_auth`：required 且无 token → 抛 `DataSourceAuthError`。

### 高价股脚本用的宽松风控（`scripts/real_backtest.py`）
```python
RiskConfig(
    max_position_ratio=0.9,
    max_single_trade_amount=1e9,
    max_single_trade_ratio=0.95,
    max_drawdown=0.2,
    max_daily_loss=5000.0,
)
```

## 2. 测试清单与验收

**运行**：`python -m pytest tests/ -q`（依赖 `pytest`）。共 5 个测试文件、70+ 用例。

| 测试文件 | 覆盖 | 验收要点 |
|---|---|---|
| `test_engine.py` | 回测主循环、信号→订单 →成交、资金/风控截断 | 撮合在 T+1 开盘；风控拒单计入 rejected |
| `test_broker.py` | 撮合、费用、订单生命周期 | 市价开成交/限价条件/一字板拒单/费用计算 |
| `test_data.py` | DataManager、Bar 属性 | 缓存命中、复权/标记位 |
| `test_risk.py` | RiskConfig 各阈值、仓位、止损 | 关键阈值触发即拒 |
| `test_strategy.py` | 5 个策略 | 每个策略能产生正确买卖信号、无未来函数 |

**验收标准**：
1. `pytest` 全绿（70+ 用例）。
2. `python3 main.py` 跑通端到端并生成 `outputs/report.html`、`outputs/equity_curve.csv`。
3. `python3 scripts/real_backtest.py 600519 20240101 20241231` 真实数据有成交（非 0）。
4. 任何“回测 0 成交”先查风控拦截（`engine.rejected_signals` / `_summarize().rejected`）。

## 3. 异常 / 错误码体系（`core/exceptions.py`）

所有异常继承 `QuantError`：

| 异常 | 含义（触发场景） |
|---|---|
| `DataError` | 数据获取/处理异常（基类） |
| `DataNotFoundError` | 数据不存在（区间无数据/标的未找到） |
| `DataFormatError` | 数据格式错误 |
| `BrokerError` | 经纪商错误（基类） |
| `InsufficientFunds` | 资金不足（下单冻结/买入超额） |
| `OrderRejected` | 订单被拒 |
| `RiskRejected` | 风控拒绝 |
| `PositionError` | 持仓错误（基类） |
| `InsufficientPosition` | 持仓不足（卖出>可用） |
| `StrategyError` | 策略错误（基类） |
| `ConfigError` | 配置错误 |
| `PersistenceError` | 持久化错误（V3 用） |

数据源额外：`DataSourceError`、`DataSourceAuthError`。

## 4. 常见错误排查速查表

| 症状 | 根因 | 处理 |
|---|---|---|
| 回测 0 成交 | 风控拦截高价股（单笔金额超限） | 放宽 `max_single_trade_amount`/`max_single_trade_ratio`（`docs/05`） |
| `DataSourceAuthError` | 缺 apikey（掘金等） | 提供 token |
| `AttributeError: initial_cash` | 用了 `portfolio.initial_cash` | 用 `portfolio.account.initial_cash` |
| `AttributeError: metrics` | 直接读 `analyzer.metrics` | 用 `analyzer.compute()` 返回对象 |
| akshare 在 3.13 报 Imp 错误 | 需要兼容补丁 | 先调用 `utils.compat.patch_imp_importer()`（见 README 数据源节） |
| `KeyError: 数据源未注册` | DataManager 未注册/未设默认 | `register` 或 `set_default` |
| 成交价异常 | 用了 `bar.close` 当成交价 | 确认市价单按 bar.open 成交（`docs/03`） |

## 5. 建议补强（知识库可检索性）

- 统一配置文件模板（`config/*.toml`），覆盖数据源/风控/费用/策略默认值。
- 集中错误码表注册（数字码 + 中文说明 + 排查指引），供 RAG 检索。
- 测试收敛到“行为即文档”：测试名直接映射到规则文档编号。