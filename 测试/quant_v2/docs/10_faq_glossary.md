---
title: Quant V2 FAQ 与术语表
version: 2.0
tags: [量化, FAQ, 术语表, 问题排查, 速查, 回测, RAG]
summary: 高频问题速答（成交时点、0成交、防前视、信号与下单区别、指标口径等）与完整术语表，RAG 问答首选入口。
---

# Quant V2 FAQ 与术语表

## 一、FAQ（高频问答）

### Q1. 信号什么时候成交？用什么价？
信号在 **T 日收盘**产生；订单 T 日只入队，**T+1 交易日**撮合。市价单按 **T+1 开盘价**成交；限价单按 T+1 区间条件成交。这是防前视的核心设计（`docs/03`）。

### Q2. 为什么我的回测 0 成交？
最常见：**风控拦截高价股**。默认 `max_single_trade_amount=50000`，茅台 100股≈15万会被全部拒掉。放宽 `RiskConfig` 该值即可（`docs/05`）。也检查：数据是否确实进入、策略是否真产生信号（看 `engine.rejected_signals`）。

### Q3. 什么是“未来函数 / 前视偏差”？如何避免？
用当前 bar 收盘价给当前信号当根成交、或在策略里读到未来 bar，都会引入未来信息，让回测失真。V2 强制：策略只拿到 `history[:index]`（不含当前 bar），且成交延后到 T+1（`docs/03`）。

### Q4. Signal 和 Order 有什么区别？
`Signal` 是策略的**买卖意图**（direction/price/qty），只负责“想买多少”；`Order` 是提交给 Broker 执行、带完整生命周期（NEW→FILLED/REJECTED…）的委托。Signal → 风控/仓位 → Order（`docs/01`）。

### Q5. 一字板怎么处理？
一字涨停（high==low 且阳线）时，**买单被拒**；一字跌停时**卖单被拒**。若 BarFlags 有 `limit_up/limit_down` 则优先采用（`docs/03`）。

### Q6. 我该用哪个仓位方式？
- 固定数量：`FixedSizer`
- 按权益比例：`PercentSizer`
- **按波动（ATR）控制风险**：`ATRSizer`（推荐），`qty=(权益×risk_percent)/(atr×multiplier)`，自动向下取整到 100 股。

### Q7. 绩效指标都怎么算？
16 项指标与公式见 `docs/07`：总收益、年化、夏普、索提诺、卡玛、最大回撤、胜率、盈亏比、换手、alpha/beta/信息比率等。注意胜率用 FIFO 配对口径。

### Q8. 支持美股/期货/加密吗？
V2 当前真正跑通的是 **A 股日线现货回测**。美股/期货/加密的费用模型和 Instrument 元数据已具备，但多市场撮合、做空、保证金、真实日历为**设计/规划**（`docs/04`）。

### Q9. 实盘能直接跑吗？
**不能**。V2 是回测框架，无实盘网关/对账/实时风控，实盘属 V3 规划（`docs/08`）。切勿在没验证对账的情况下实盘交易。

### Q10. 更换数据源怎么做？
实现 `AbstractDataSource` 的 `fetch_daily` + `price_to_fetch`，注册进 `DataManager` 即可。akshare 免费无需 token；掘金需 token。（`docs/02`）

### Q11. 报告怎么生成？
`python3 main.py` 生成 `outputs/report.html` + `outputs/equity_curve.csv`；`ReportGenerator(analyzer, trades, equity_curve)` 也可在代码里定制调用。

### Q12. 把滑点算进去没有？
滑点按比率（0.01% 等）**加进 FeeBreakdown.slippage_cost** 计入成本（`docs/03`）。市场冲击 `impact_cost` 字段预留未计入。现金结算只扣 commission（`docs/06`)。

## 二、术语表

| 术语 | 英文 | 定义 |
|---|---|---|
| K线 | Bar | OHLCV 标准行情单元（open/high/low/close/volume/amount） |
| 前复权 | qfq | 以当前价为基准调整历史价，消除除权跳空 |
| 后复权 | hfq | 以早期价为基准，价格连续不跳空 |
| 复权因子 | adj_factor | Bar 上记录，用于价格换算 |
| 交易信号 | Signal | 策略输出的买卖意图 |
| 买入/卖出 | BUY/SELL | Single方向 |
| 持有 | HOLD | 不操作 |
| 做空/回补 | SHORT/COVER | 期货/加密用（V2 现货忽略） |
| 订单 | Order | 提交撮合的委托 |
| 市价单 | MARKET | 按开盘/fill 价成交 |
| 限价单 | LIMIT | 达到指定价才成交 |
| 止损单 | STOP | 触发价触发后转市价/限价 |
| 止损限价单 | STOP_LIMIT | 触发价+限价双条件 |
| 成交 | Trade | 撮合结果，含费用 |
| 持仓 | Position | 某标的当前头寸 |
| 整手 | lot | A股最小单位 100 股 |
| 可用/冻结 | available/frozen | T+1 下当日买入冻结 |
| 账户 | Account | 现金/权益/账本 |
| 组合 | Portfolio | 多标的多策略集合 |
| 总权益 | Equity | 现金+持仓市值 |
| 回撤 | Drawdown | 净值自峰回落幅度 |
| 最大回撤 | Max Drawdown | 历史最大峰-谷跌幅 |
| 年化收益 | Annual Return | 折算 252 交易日年化 |
| 年化波动 | Annual Volatility | 日收益标准差×√252 |
| 夏普比率 | Sharpe | 单位风险超额收益 |
| 索提诺 | Sortino | 仅下行风险口径夏普 |
| 卡玛 | Calmar | 年化收益/最大回撤 |
| 胜率 | Win Rate | FIFO 配对盈利比 |
| 盈亏比 | PL Ratio | 平均盈利/平均亏损 |
| 换手率 | Turnover | 成交额/平均净值 |
| Alpha/Beta | — | 相对基准的主动收益/系统性相关 |
| 信息比率 | IR | 超额收益/跟踪误差 |
| 滑点 | Slippage | 预期价与成交价偏差 |
| 保证金 | Margin | 期货/加密占用资金 |
| 前视偏差 | Lookahead Bias | 使用未来信息致回测失真 |
| 过拟合 | Overfitting | 参数过度迎合历史 |
| Walk-Forward | WFO | 滚动样本外优化防过拟合 |
| ATR | 平均真实波幅 | 波动度量，用于止损/仓位 |

## 三、索引

建议按序阅读：`00_overview` → `01_domain_model` → `02_interfaces` → `03_backtest_assumptions` → `04_multi_market_rules` → `05_risk_position_stop` → `06_portfolio_broker_engine` → `07_performance_optimizer` → `08_live_trading`(规划) → `09_config_testing` → `10_faq_glossary`(本档)。