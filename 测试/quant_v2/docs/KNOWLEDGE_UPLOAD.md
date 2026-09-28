---
title: Quant V2 知识库导入指引
version: 2.1
tags: [量化, 知识库, 扣子, 导入, RAG, 上传]
summary: 将 docs/ 下的 Quant V2 文档导入扣子空间知识库的操作指引、每文件一句话简介、建议的切分与命名方式。
aliases: ['知识库', '导入', '扣子空间', 'RAG', '上传', 'kb', 'coze']
---

# Quant V2 知识库导入指引

本文档说明如何把 `docs/` 下这套文档导入**扣子空间知识库**，做 RAG 检索问答。

> 前提：本 Agent 无写入你个人知识库的通道，上传在扣子平台手动完成。以下为"导入即用"适配结论。

## 1. 已具备的 RAG 友好结构（无需改造）

| 结构 | 状态 | 作用 |
|---|---|---|
| 多文件拆分（00–10 + 本档） | ✅ | 主题单一、每文件独立可检索，避免大文档淹没 |
| 每文件 frontmatter（title/version/tags/summary） | ✅ | 摘要/关键词可直接当检索索引 |
| FAQ 独立文件（10_faq_glossary） | ✅ | 问答命中最高效 |
| 术语表 | ✅ | 概念口径统一 |
| 规则用表格 + “必须/禁止/默认”措辞 | ✅ | 增强检索与指令遵从 |

## 2. 上传步骤（扣子空间知识库）

1. 扣子端打开 [扣子空间] → **知识库**。
2. 新建知识库（命名如 `quant_v2`），选择可编辑模式（便于后续更新）。
3. 批量上传 `docs/` 下全部 `.md` 文件（可整目录选择，或直接上传 `docs_quant_v2_kb.zip`）。
4. 分段方式：建议**自动分段**（本套文档每文件 ≤ 数 KB、主题单一，自动分段即可）；无需自定分隔符。
5. 完成后，在该空间引用此知识库的 Agent 中，把知识库关联到对应工作流/技能/机器人即可问答。

## 3. 每文件一句话简介（上传时便于核对）

| 文件 | 一句话 |
|---|---|
| `00_overview` | 系统总览、模块分层、完整数据流、入口命令 |
| `01_domain_model` | Bar/Signal/Order/Trade/Position/Account/Instrument/Event 定义与生命周期 |
| `02_interfaces` | 各层类构造签名与方法参数 |
| `03_backtest_assumptions` | 撮合规则、时间语义、防前视、费用模型 |
| `04_multi_market_rules` | A股/ETF/期货/加密规则矩阵（多市场为设计/规划） |
| `05_risk_position_stop` | 风控参数、仓位、止损及高价股踩坑 |
| `06_portfolio_broker_engine` | 组合/经纪商/引擎协作与资金结算口径 |
| `07_performance_optimizer` | 16 项绩效指标公式、GridSearch/Walk-Forward |
| `08_live_trading` | 实盘运维（V3 规划，未落地） |
| `09_config_testing` | 配置体系、测试验收、错误码排查表 |
| `10_faq_glossary` | 12 条 FAQ + 完整术语表 |
| `11_visualization` | 可视化回测系统：Recorder 记录、指标口径一致、买卖点分离、HTML 导出 |
| `KNOWLEDGE_UPLOAD` | 本指引 |

## 4. 建议（可选增强）

- 给每个文件补一行 `aliases:`（别名/同义词），提升检索召回（如 `Bar`→`K线`、`Signal`→`信号`）。
- 有多个业务线时，在文件名加业务前缀并分知识库隔离。
- 知识库更新流程：改 `docs/` → 重新推送 GitHub → 重新上传对应 `.md` 即可（逐文件替换）。
