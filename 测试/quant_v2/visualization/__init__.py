"""
Quant V2 可视化子系统

核心设计原则（与主文档一致）：
1. 可追溯：每个 bar / 信号 / 订单 / 成交 / 持仓 / 净值 / 指标都被记录；
2. 口径一致：图上指标 = 策略实际用的指标，绝不事后重算；
3. 解耦：可视化只读记录，不能反向影响回测状态。

模块：
- recorder       BacktestRecorder：在各环节采集原始记录（纯记录，不改状态）
- exporter       导出 JSON / CSV / 静态 HTML 报告
- replay         （规划）时间轴回放控制器
- dashboard      交互面板（规划）
"""

from visualization.recorder import BacktestRecorder

__all__ = ["BacktestRecorder"]