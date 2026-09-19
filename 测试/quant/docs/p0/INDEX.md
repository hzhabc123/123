# P0 里程碑索引

> **状态：DONE** ✅
> **完成日期：** 2026-09-18
> **总测试数：** 57（全部通过）

---

## 子任务总览

| 任务 ID | 描述 | 状态 | 文档 |
|---------|------|------|------|
| P0-1 | 数据质量（BarFlags + 停牌标记） | DONE | [P0_1_2_7_data_repro.md](P0_1_2_7_data_repro.md) |
| P0-2 | 防前视偏差（history_bars） | DONE | [P0_1_2_7_data_repro.md](P0_1_2_7_data_repro.md) |
| P0-3 | 订单撮合（Order + 撮合循环） | DONE | [P0_3_4_5_match_fee_ledger.md](P0_3_4_5_match_fee_ledger.md) |
| P0-4 | 费用模型（ChinaAFeeModel） | DONE | [P0_3_4_5_match_fee_ledger.md](P0_3_4_5_match_fee_ledger.md) |
| P0-5 | 账本流水（Ledger + 公司行动） | DONE | [P0_3_4_5_match_fee_ledger.md](P0_3_4_5_match_fee_ledger.md) |
| P0-6 | 绩效指标 + 一键报告 | DONE | [P0_6_performance.md](P0_6_performance.md) |
| P0-7 | 可复现性（run_hash + manifest） | DONE | [P0_1_2_7_data_repro.md](P0_1_2_7_data_repro.md) |

---

## 变更文件清单

### 子任务 A（P0-1 + P0-2 + P0-7）

| 文件 | 操作 | 说明 |
|------|------|------|
| `data/bar.py` | 修改 | 新增 BarFlags + adj_factor |
| `data/calendar.py` | 新增 | TradingCalendar |
| `data/tdx_txt_data_source.py` | 修改 | 停牌标记填充 |
| `strategy/base_strategy.py` | 修改 | history_bars 防前视 |
| `config/config.yaml` | 新增 | 运行配置 |
| `config/settings.py` | 修改 | 新增 SEED |
| `config/run_hash.py` | 新增 | compute_run_hash |
| `tests/test_p0_1_2_7_data.py` | 新增 | 18 个测试 |

### 子任务 B（P0-3 + P0-4 + P0-5）

| 文件 | 操作 | 说明 |
|------|------|------|
| `broker/order.py` | 新增 | 独立 Order 类 |
| `broker/fee_model.py` | 新增 | ChinaAFeeModel |
| `broker/backtest_broker.py` | 重写 | 撮合循环 + 费用 |
| `portfolio/ledger.py` | 新增 | LedgerEntry |
| `portfolio/portfolio.py` | 修改 | 账本 + corporate_action |
| `portfolio/account.py` | 修改 | 增加 ledger 字段 |
| `engine/backtest_engine.py` | 修改 | Signal→Order，每 bar 撮合 |
| `tests/test_p0_3_4_5_match.py` | 新增 | 17 个测试 |

### 子任务 C（P0-6 + 最终集成）

| 文件 | 操作 | 说明 |
|------|------|------|
| `performance/__init__.py` | 新增 | 导出 PerformanceAnalyzer, PerformanceMetrics |
| `performance/analyzer.py` | 新增 | 完整绩效计算 |
| `engine/backtest_engine.py` | 最小修改 | 新增 equity_curve 记录 + all_trades 收集 |
| `main.py` | 重写 | 一键运行 + 报告 + manifest |
| `tests/test_p0_6_metrics.py` | 新增 | 17 个绩效指标测试 |
| `tests/test_p0_7_repro.py` | 新增 | 2 个可复现性测试 |
| `tests/test_p0_integration.py` | 新增 | 3 个端到端集成测试 |

---

## 测试命令与结果

### 全量测试

```bash
cd /Coze/Drive/扣子/quant_run && python3 -m pytest tests/ -v
```

**结果：57 passed in 16.59s**

- test_p0_1_2_7_data.py: 18 passed
- test_p0_3_4_5_match.py: 17 passed
- test_p0_6_metrics.py: 17 passed
- test_p0_7_repro.py: 2 passed
- test_p0_integration.py: 3 passed

### 一键运行

```bash
python3 main.py
```

**输出示例：**
```
============================================================
  Performance Metrics Summary
============================================================

  --- 收益指标 ---
  总收益率:               6.70%
  年化收益率:             3.94%
  基准收益率:             0.00%

  --- 风险指标 ---
  年化波动率:             4.08%
  最大回撤:               2.56%
  最大回撤持续(天):           1

  --- 风险调整收益 ---
  夏普比率:              0.4753
  索提诺比率:            0.4221
  卡玛比率:              1.5412

  --- 交易统计 ---
  总交易数(配对):             8
  胜率:                  62.50%
  盈亏比:                1.1050
  换手率:                0.8994

============================================================

[OUTPUT] Run ID: run_d9c9c946
[OUTPUT] Manifest: outputs/run_d9c9c946/manifest.json
[OUTPUT] Run Hash: 296c68c699591c93
[OUTPUT] Metrics SHA256: 13bbd893b7bd965c
```

**生成文件：**
- `outputs/{run_id}/manifest.json`
- `outputs/{run_id}/equity_curve.csv`
- `outputs/{run_id}/trades.csv`
- `outputs/{run_id}/ledger.csv`

---

## 验收证据

### 1. 可复现性验证

两次运行 `python3 main.py`：

| 运行 | metrics_sha256 |
|------|----------------|
| 第 1 次 | `13bbd893b7bd965c` |
| 第 2 次 | `13bbd893b7bd965c` |

**结论：** ✅ 完全一致，可复现性通过。

### 2. 交易成本对账

ChinaAFeeModel 手工对账（见 test_p0_3_4_5_match.py::TestFeeModel）：
- 买入 1000 股 @ 10.00
- 成交额 = 10000.00
- 佣金 = max(10000 × 0.0003, 5.0) = 5.00
- 印花税 = 0（买入不征收）
- 过户费 = 10000 × 0.00001 = 0.10
- 滑点 = 10000 × 0.0001 = 1.00
- **合计 = 6.10** ✅

### 3. DoD（Definition of Done）

| 验收条件 | 状态 |
|---------|------|
| P0 全部通过 | ✅ 57/57 |
| 示例一键运行 | ✅ `python main.py` |
| 无前瞻/幸存者偏差 | ✅ history_bars 防前视 + bar flags |
| 交易成本与手工对账 | ✅ ChinaAFeeModel |
| 自动生成绩效报告 | ✅ PerformanceAnalyzer |
| 配置可复现 | ✅ manifest + run_hash |

---

## 风险与遗留问题

1. **复权因子**：`adj_factor` 字段已预留，但 TDXTxtDataSource 未接入真实复权数据，默认为 1.0（不复权）。P1 需接入复权因子数据。
2. **涨跌停/ST 标记**：当前数据源无法判断，保持 False。需接入涨跌停价数据和 ST 标记数据。
3. **基准对比**：当前 benchmark_curve 需要手工传入，P1 可接入指数数据自动对比。
4. **多标的**：当前仅支持单标的回测，P1 需扩展为多标的组合。

---

## 下一步（P1 规划）

- P1-1：风险管理扩展（止损、仓位上限动态调整）
- P1-2：多标的支持
- P1-3：复权数据接入
- P1-4：基准指数自动对比
- P1-5：可视化报告（HTML/PDF）
