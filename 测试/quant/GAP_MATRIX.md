# 回测系统完善 · 现状-差距-任务矩阵

> 基线仓库：`hzhabc123/123` · 分支：`feature/quant-system-improvement`
> 基线提交：`fa9e341`（已含双均线策略 + main.py 可运行入口 + 引擎持仓同步修复）
> 基线运行结果（301313，2024-09-06 ~ 2026-06-12，424 根日线，MA5/MA20，每次 200 股）：
>   - 现金 94,225.38 / 总资产 106,085.38 / 浮盈 +5,503.36
>   - 9 次买入、8 次卖出、期末持仓 200 股
>   - 无风控报错，无幸存者偏差数据，无复权数据

---

## 现状总览

| 模块 | 当前实现 | 能力评估 |
|---|---|---|
| `data/` | Bar 数据类 + TDXTxtDataSource（只读通天天勤 txt）+ CSV | 仅支持**不复权日线**，缺交易日历、复权、停牌/ST/退市标记 |
| `strategy/` | BaseStrategy 抽象基类 + MACrossStrategy + DualMAStrategy | 策略只产出 `BUY/SELL` 信号，无订单类型、无仓位建议 |
| `signal.py` | `SignalType ∈ {BUY, SELL}` + `price/volume` | **无订单类型、无止损止盈、无部分成交概念** |
| `broker/` | BacktestBroker：市价成交，固定 `commission_rate` + `slippage` | **无印花税、过户费、涨跌停检查、成交量限制、部分成交** |
| `portfolio/` | Portfolio/Account/Position/Order/Trade | **无分红送股/拆股、无现金流流水、无多币种** |
| `risk/` | RiskManager 仅检查 单票仓位比 + 总仓位比 | **无最大回撤、VaR、日亏损、连亏、止损** |
| `engine/` | BacktestEngine（同步 position 修复版） + 空 event_engine | **无事件驱动、无订单队列、无前视偏差校验** |
| `performance/` | **不存在** | 无任何绩效指标计算 |
| `config/` | settings.py 只含 START_CASH / COMMISSION | **无环境配置、无数据版本、无随机种子** |
| `utils/` | logger.py（仅 StreamHandler） | **无文件日志、无哈希、无审计** |
| 测试 | 仅 `test_ma_strategy.py` 等几个手工脚本，无 pytest 规范 | 覆盖率 ≈ 0% |
| 文档 | CLASS_DESIGN.md + 下一步.md（设计稿） | 无 API 文档、无策略模板、无用户手册 |

---

## 差距矩阵（按任务书映射）

| 任务 ID | 现状 | 目标能力 | 优先级 | 实施策略 | 风险 |
|---|---|---|---|---|---|
| **P0-1** 数据质量与 PiT | 仅不复权日线 txt | 交易日历、复权、停牌/ST/退市、财务公告日 | P0 | 新增 `data/calendar.py`、`Bar` 加 flags 字段、数据源抽象层支持多格式；暂不引入外部财务数据（无数据源） | 无外部数据源则仅做空实现 + 占位接口 |
| **P0-2** 防前视偏差 | 无约束 | 信号只使用当前及历史数据 | P0 | 在 `BaseStrategy` 增加 `current_bar_index` 与切片访问控制；引擎按时间戳喂数据 | 策略内部仍可能偷看，需测试用例 |
| **P0-3** 订单与撮合 | 市价单立即成交 | 市价/限价/止损、部分成交、涨跌停/停牌不成交 | P0 | 重构 `Broker`：引入 `Order` 队列，每根 bar 模拟撮合；涨跌停按 ±10% 判定 | 与现有 `BacktestBroker.execute_signal` 接口不兼容，需重写并更新 `main.py` 调用链 |
| **P0-4** 交易成本 | 仅佣金 + 滑点 | 佣金/印花税/过户费/滑点/冲击成本 | P0 | 引入 `FeeModel` 抽象（StampTax、TransferFee、Commission） | 需配置化，避免硬编码 |
| **P0-5** 账户记账 | 简单 cash + position | 分红送股、拆股、多币种、现金流流水 | P0 | `Account` 增 `LedgerEntry` 列表；`Portfolio` 增 `process_corporate_action` | 多币种在本项目无数据，仅做抽象预留 |
| **P0-6** 绩效指标 | 无 | 年化/波动/夏普/索提诺/卡玛/最大回撤/胜率/盈亏比/换手/基准 | P0 | 新建 `performance/analyzer.py`，基于 pandas 计算；提供基准对比 | 需引入 pandas/numpy（已有） |
| **P0-7** 可复现性 | 无 | 配置/随机种子/数据版本/输出哈希 | P0 | `config.yaml` + `run_hash` 计算 + 输出 manifest.json | 需保证无副作用代码不破坏复现 |
| **P1-1** 组合风控 | 仅 2 项仓位比 | 单票/行业/杠杆/止损/VaR/压力 | P1 | 扩展 `RiskManager` + 可配置 `RiskRule` | 行业数据缺失，行业限制仅做抽象 |
| **P1-2** 稳健性 | 无 | Walk-forward / 参数敏感性 / 蒙特卡洛 | P1 | 新建 `optimizer/robust.py` | 计算量大，仅做框架与简单示例 |
| **P1-3** 归因与报告 | `portfolio.summary()` 仅打 6 行 | HTML/PDF 完整报告 | P1 | 新建 `performance/report.py`（HTML，使用 matplotlib/plotly 可选） | 依赖 matplotlib，需检查环境 |
| **P1-4** 工程化 | 无 pytest、无 CI、无覆盖率 | 核心模块覆盖率 >80%，CI | P1 | 补 `pytest` 用例 + `pytest.ini` + GitHub Actions | 覆盖率目标需实测 |
| **P1-5** 多资产 | 仅 A 股日线 + ETH 小时线 | 期货/期权等 | P1 | 抽象 `ContractSpec`（乘数、保证金、换月）；ETH 作为示例 | 复杂衍生品暂不实现 |
| **P2-1** 模拟盘/实盘 | 无 | 信号导出、订单路由、对账 | P2 | 定义 `Gateway` 抽象 + 纸交易 Gateway | 无真实券商接口 |
| **P2-2** 性能 | 单线程 for 循环 | 向量化、并行 | P2 | 关键路径用 numpy 向量化 | 保持可读性 |
| **P2-3** UI/API | 无 | 任务提交/查询/可视化 | P2 | 简单 FastAPI + 静态 HTML | 仅 MVP |
| **P2-4** 文档协作 | 仅 2 个 md | 策略模板、API 文档、示例 | P2 | `docs/` 目录 + mkdocs 风格 | 轻量 |

---

## DoD 对照（目标完成状态预测）

| DoD 项 | 完成路径 |
|---|---|
| P0 全部通过 | 本轮重点交付 |
| 示例策略一键运行 | `python main.py` 已可运行，改造后仍保持 |
| 单元/集成测试通过，核心覆盖率 >80% | 每个 P0 模块配 pytest，最终跑 coverage |
| 无前视偏差、无幸存者偏差 | P0-1/P0-2 实现 + 测试用例 |
| 交易成本与手工对账一致 | P0-4 提供对账测试 |
| 自动生成绩效报告 | P0-6 + P1-3 |
| 文档更新，配置可复现 | P0-7 + P2-4 |

---

## 执行计划

本轮（本轮会话）优先完成 **P0 全部 7 项**，每项都包含：
1. **代码变更**：最小侵入、保持兼容（必要时提供旧接口别名）
2. **测试**：`tests/test_p0_*.py`，覆盖关键路径
3. **文档**：在 `docs/p0/` 下记录设计决策
4. **验收证据**：测试通过截图式日志 + 手工对账表

P1、P2 在本轮内按进度推进，至少完成 P1-1/P1-3/P1-4。
