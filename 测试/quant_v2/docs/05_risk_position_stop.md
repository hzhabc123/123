---
title: Quant V2 风控 / 仓位 / 止损
version: 2.0
tags: [量化, 风控, 仓位, 止损, 资金截断, 单笔限额, max_drawdown, RiskConfig]
summary: 风控校验顺序、RiskConfig 各参数含义与触发、仓位计算方法、止损管理方式及常见踩坑（高价股限额）。
---

# Quant V2 风控 / 仓位 / 止损

## 1. 风控顺序（全链路）

```
Signal 产生
  → [A] 方向归一化（SHORT/HOLD 处理）
  → [B] 卖出数量截断（不超过持仓）
  → [C] RiskManager.validate_signal(风控校验)   ← 可拒绝
  → [D] 买入资金截断（不超过可用现金）            ← 隐式风控
  → [E] 生成订单入 Broker
```

外层顺序（建议与代码一致）：**Signal → PositionSizer → RiskManager → Order → Broker**。

## 2. RiskConfig 字段与触发（`risk/risk_manager.py`）

| 参数 | 默认 | 校验逻辑（通过才放行） |
|---|---|---|
| `max_position_ratio` | 0.3 | 加仓后单标的市值/权益 ≤ 该比 |
| `max_total_position_ratio` | 0.9 | 总仓位/权益 ≤ 该比 |
| `max_drawdown` | 0.2 | 回撤 ≤ 该值时禁开新仓 |
| `drawdown_warning` | 0.15 | 仅警告 |
| `max_daily_loss` | 5000.0 | 当日已实现亏损 ≤ 金额 |
| `max_daily_loss_ratio` | 0.02 | 当日已实现亏损 ≤ 权益比 |
| `max_consecutive_losses` | 5 | 连续亏损 ≤ 次数（含暂停） |
| `max_single_trade_amount` | 50000.0 | **单笔买入金额 ≤ 上限** |
| `max_single_trade_ratio` | 0.1 | 单笔/权益 ≤ 比 |
| `max_leverage` | 1.0 | 杠杆 ≤ 上限 |

**校验返回**：`RiskCheckResult(passed: bool, reason: str)`；失败即拒单，信号记录到 `engine.rejected_signals`。

### ⚠️ 高价股踩坑（必读）
`max_single_trade_amount=50000` 对高价股过严。例：茅台 ~1520 元 × 100股 = 15.2万 > 5万 → **全部买单被“单笔交易金额超限”拦截，回测 0 成交**。
**解决**：真实高价股回测时放宽该参数（`scripts/real_backtest.py` 用 `max_single_trade_amount=1e9`、`max_single_trade_ratio=0.95`、`max_position_ratio=0.9`）。
> 0 成交排查第一步：检查是否是风控拦截而非数量截断。

## 3. 资金截断（隐式风控，`engine/backtest_engine.py::_process_signal`）

买入时若目标数量超可用资金，自动按可承受的整手截断：

```python
qty = int(available_cash / price * 0.98 // 100 * 100)
```

- `*0.98` 预留约 2% 覆盖手续费
- `//100 *100` 向下取整到 100 股（A股整手）
- 卖出时数量截断到真实持仓

## 4. 仓位计算（`risk/position_sizer.py`）

`create_sizer(type, **kw)`：
| 类型 | 公式/参数 |
|---|---|
| `fixed` | 固定 `qty`（默认100） |
| `percent` | `percent`（权益比）+ `min_amount`（最小金额） |
| `atr`（推荐） | `qty = (equity × risk_percent) / (atr × atr_multiplier)`，向下取整100股；参数 `risk_percent/atr_multiplier/atr_period/min_qty` |

策略通过 `StrategyParams.atr` 或 `SetAttributes` 为信号提供数量（`signal.target_qty`）；无目标时由 sizer 计算。

## 5. 止损管理（`risk/stop_manager.py`）

`create_*_stop(entry_price, direction, **kw)` → `StopOrder`：
- `fixed`：固定 `stop_percent`，止损价 = 进场价×(1∓per)
- `atr`：`atr_multiplier × atr`
- `trailing`：`trailing_percent` 移动止损（随价格新高上移，方向 LOOK_BUY）

管理器：`add/remove`，`update(symbol, price)` 判断是否触发，返回 `"SELL"`（多单止损）或 `"COVER"`（空单）。**注意：返回的是止损动作，需由调用方（策略/引擎）转换为实际平仓信号**；StopManager 不直接下单。

## 6. 风控设计原则（约定）

- **宁可拒单、不可爆仓**：风控只在提交订单前执行，成交后仓位突变（如跳空）可通过下一 bar 风控校验兜底（当前未强制平仓）。
- **记录而非吞掉**：被拒信号进 `rejected_signals`，便于事后审计 `_summarize()` 的 `rejected` 计数。
- **可配置优先**：所有阈值放 `RiskConfig`，不改业务代码即可调参。

## 7. 使用建议

| 场景 | 建议配置 |
|---|---|
| 普通标的回测 | 默认即可 |
| 高价股回测 | `max_single_trade_amount` 调大，`max_single_trade_ratio` 适当 |
| 组合多标的 | 收紧 `max_position_ratio`、`max_total_position_ratio` |
| 复验历史 | 用「仅历史信息」的回撤/亏损风控，避免用到未来 |