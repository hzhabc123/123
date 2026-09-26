---
title: Quant V2 绩效 / 优化
version: 2.0
tags: [量化, 绩效, 夏普, 最大回撤, 胜率, 盈亏比, alpha, beta, 网格搜索, WalkForward, PerformanceMetrics]
summary: PerformanceAnalyzer 全部指标的精确口径（公式）、PerformanceMetrics 字段、报告生成与 Optimizer 参数搜索方式。
---

# Quant V2 绩效 / 优化

## 1. PerformanceAnalyzer（`performance/analyzer.py`）

```python
analyzer = PerformanceAnalyzer(
    equity_curve,            # [{"datetime","equity",...}]
    trades,
    benchmark_curve=None,    # 可选，["equity"] 同上
    risk_free_rate=0.02,
)
metrics = analyzer.compute() -> PerformanceMetrics   # 有缓存，二次直接返回
df = analyzer.to_dataframe() -> pd.DataFrame         # datetime/equity/daily_return/drawdown
analyzer.metrics_to_dict() -> dict                   # 16 项
analyzer.summary() -> str                            # 中文报告
```

`TRADING_DAYS_PER_YEAR = 252`。

## 2. PerformanceMetrics 16 项口径（公式为准）

### 收益
| 字段 | 公式 |
|---|---|
| `total_return` | `final/initial - 1`（首尾净值） |
| `annual_return` | `(1+total)^(252/n) - 1`（n=日收益率数）；total≤-1 时记 -1 |
| `benchmark_return` | 基准曲线末段累计（`bench[-1]`，简化） |

### 风险
| 字段 | 公式 |
|---|---|
| `annual_volatility` | `std(日收益) × √252` |
| `max_drawdown` | 最大 `(peak-eq)/peak` |
| `max_drawdown_duration` | 达到最大回撤时的累计未创新高天数 |

### 风险调整
| 字段 | 公式 |
|---|---|
| `sharpe_ratio` | `mean(超额日收益×252)/年化波动`，`mean≤0` 记 0 |
| `sortino_ratio` | `mean(超额×252) / (下行偏差×√252)`，无下行记 0 |
| `calmar_ratio` | `annual_return / |max_dd|`，max_dd>0 时 |

### 交易统计
| 字段 | 公式 |
|---|---|
| `total_trades` | 成交笔数 `len(trades)` |
| `win_rate` | FIFO 配对后盈利笔 / 总配对笔 |
| `profit_loss_ratio` | 平均盈利 / 平均亏损；无亏损→0 |
| `turnover` | 全部换手额(abs) / 平均净值 |

### 基准对比
| 字段 | 公式 |
|---|---|
| `alpha` | 年化 `(mean_s - rf) - beta×(mean_b - rf)`，×252 |
| `beta` | `cov(strat,bench)/var(bench)` |
| `information_ratio` | `mean(active×252)/(std(active)×√252)` |

> 配对口径（`_calc_trade_stats`）：维护未平仓**买单队列**做 FIFO，每笔卖与买入配对算 `pnl=(卖价-买价)×量`。只统计有配对的部分。

## 3. 输出

`summary()` 输出中文分隔报告；`to_dataframe()` 给 pandas 序列含回撤列（`drawdown` 为负值）；`metrics_to_dict` 返回可直接序列化的 16 字段 dict。

## 4. Optimizer — 参数优化（`optimizer/`）

### GridSearchOptimizer（`optimizer/grid_search.py`）

```python
from optimizer.grid_search import GridSearchOptimizer
grid = GridSearchOptimizer(
    evaluator,             # 可调用：eval(**params) -> dict，含优化目标
    param_grid={"short": [5,10,20], "long": [20,40,60]},
    objective="total_return",   # 或 "sharpe_ratio" 等
    maximize=True,
    top_n=5,
)
results = grid.search()     # DataFrame?/记录，含 top_n 最优
grid.best_params / grid.top_results
```

- 遍历参数笛卡尔积，逐组调 `evaluator(**params)` 跑回测，按 `objective` 排序取 `top_n`。
- 评估函数返回 dict（如 `{total_return, sharpe_ratio, max_drawdown, total_trades}`），由外部策略包装 `BacktestEngine.run` 结果提供。

### WalkForwardOptimizer（`optimizer/walk_forward.py`）

滚动样本外优化，降低过拟合：

```python
wfo = WalkForwardOptimizer(
    evaluator, param_grid, objective, maximize=True,
    train_window=252, test_window=63, step=252,
)
results = wfo.run(bars)   # 逐段：训练段网格搜索 → 最优参数测样本外段
wfo.all_results / wfo.best_parameters_per_window / wfo.oos_metrics
```

> 依据真实代码实现方式书写；若实际签名有出入以 `optimizer/` 源码为准。

## 5. 报告生成（`performance/report.py`）

`PerformanceReport` 汇总：`analyzer`（PerformanceAnalyzer）+ `trades` 分层统计（全部/盈利/亏损）、分桶收益、月度收益热力、`render_markdown()` / `render_html()`。

## 6. 使用建议

| 目标 | 指标 |
|---|---|
| 绝对收益 | `total_return` / `annual_return` |
| 回撤控制 | `max_drawdown` / `calmar` |
| 稳定性 | `sharpe` / `sortino` |
| 与基准关系 | `alpha` / `beta` / `information_ratio` |
| 交易质量 | `win_rate` / `profit_loss_ratio` |

**防过拟合**：多策略、多区间、Walk-Forward 交叉验证后再定参，避免“参数迎合历史”。

## 7. 坑位备忘

- `PerformanceAnalyzer.metrics` 是**内部缓存属性**，初值 None；取指标用 `.compute()`，不要直接读 `.metrics`（曾 `AttributeError`）。
- 空净值曲线 → 返回全 0 的 `PerformanceMetrics`，不抛错。
- 基准曲线缺失时 alpha/beta/IR 与 benchmark_return 均为 0，非错误。