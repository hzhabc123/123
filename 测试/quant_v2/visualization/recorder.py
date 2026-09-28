"""
Quant V2 BacktestRecorder — 回测过程记录器

职责（"先记录，再可视化"）：
  在每个关键环节采集原始记录，供后续可视化 / 回放 / 审计使用。
  Recorder 是**纯记录器**：只读采集，绝不修改回测状态。

设计约束：
- to_dataframe 事件表按时间排序（bar.datetime 为统一时间轴键）；
- 买卖点区分五类：Signal / Order / Trade / Stop / Reject，分别建档，
  避免"信号=成交"的误读；
- 指标记录采用 (name, value, timestamp)，由策略/引擎主动上报，
  保证"图上指标 = 策略实际指标"，不做事后重算。
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import List, Dict, Any, Optional


@dataclass
class Record:
    """单条记录的通用载体（序列化友好）"""
    type: str                       # bar / indicator / signal / order / trade / position / equity / risk_reject / stop
    timestamp: Any                  # 统一时间轴：bar.datetime（datetime）
    data: Dict[str, Any] = field(default_factory=dict)   # 各环节明细字段


class BacktestRecorder:
    """回测过程记录器"""

    def __init__(self):
        self.records: List[Record] = []

        # 分表（按类型索引，便于查询与导出）
        self.bar_records: List[dict] = []
        self.indicator_records: List[dict] = []
        self.signal_records: List[dict] = []
        self.order_records: List[dict] = []
        self.trade_records: List[dict] = []
        self.position_records: List[dict] = []
        self.equity_records: List[dict] = []
        self.risk_reject_records: List[dict] = []
        self.stop_records: List[dict] = []

    # ---------------- 各环节记录 ----------------

    def record_bar(self, bar, indicator_values: Optional[Dict[str, float]] = None):
        """记录一根 K线（可选附带该 bar 上策略使用的指标快照）"""
        bd = {
            "symbol": bar.symbol,
            "open": bar.open,
            "high": bar.high,
            "low": bar.low,
            "close": bar.close,
            "volume": bar.volume,
            "amount": getattr(bar, "amount", 0.0),
        }
        self.bar_records.append({"timestamp": bar.datetime, **bd})
        self._append(Record("bar", bar.datetime, bd))
        # 指标：与 bar 绑定的"策略当前使用的值"（口径一致的关键）
        if indicator_values:
            for name, value in indicator_values.items():
                rec = {"name": name, "value": value, "timestamp": bar.datetime}
                self.indicator_records.append(rec)
                self._append(Record("indicator", bar.datetime, rec))

    def record_indicator(self, name: str, value: float, timestamp: Any):
        """独立记录一个指标值（引擎/策略在计算处主动上报）"""
        rec = {"name": name, "value": value, "timestamp": timestamp}
        self.indicator_records.append(rec)
        self._append(Record("indicator", timestamp, rec))

    def record_signal(self, signal):
        """记录策略信号（Signal 点）"""
        rec = {
            "symbol": signal.symbol,
            "direction": getattr(signal.direction, "value", str(signal.direction)),
            "price": signal.price,
            "qty": getattr(signal, "target_qty", 0.0),
            "strength": getattr(signal, "strength", 1.0),
            "reason": getattr(signal, "reason", ""),
            "strategy_id": getattr(signal, "strategy_id", ""),
            "timestamp": signal.timestamp,
        }
        self.signal_records.append(rec)
        self._append(Record("signal", rec["timestamp"], rec))

    def record_order(self, order):
        """记录订单（Order 点：看执行延迟）"""
        rec = {
            "order_id": order.order_id,
            "symbol": order.symbol,
            "side": getattr(order.side, "value", str(order.side)),
            "order_type": getattr(order.order_type, "value", str(order.order_type)),
            "signal_price": order.price,
            "qty": order.qty,
            "stop_price": getattr(order, "stop_price", 0.0),
            "strategy_id": getattr(order, "strategy_id", ""),
            "status": getattr(order.status, "value", str(order.status)),
            "timestamp": getattr(order, "create_time", datetime.now()),
        }
        self.order_records.append(rec)
        self._append(Record("order", rec["timestamp"], rec))

    def record_risk_reject(self, signal, order, reason: str):
        """记录风控/资金拒绝（Reject 点：看未执行原因）"""
        rec = {
            "symbol": getattr(signal, "symbol", ""),
            "direction": getattr(getattr(signal, "direction", None), "value",
                                 str(getattr(signal, "direction", ""))),
            "price": getattr(signal, "price", 0.0),
            "qty": getattr(signal, "target_qty", 0.0),
            "reason": reason,
            "strategy_id": getattr(signal, "strategy_id", ""),
            "timestamp": getattr(signal, "timestamp", datetime.now()),
        }
        self.risk_reject_records.append(rec)
        self._append(Record("risk_reject", rec["timestamp"], rec))

    def record_trade(self, trade):
        """记录实际成交（Trade 点：真实买卖）"""
        rec = {
            "trade_id": trade.trade_id,
            "order_id": trade.order_id,
            "symbol": trade.symbol,
            "side": getattr(trade.side, "value", str(trade.side)),
            "price": trade.price,
            "qty": trade.qty,
            "commission": trade.commission,
            "slippage": trade.slippage,
            "notional": trade.notional,
            "net_amount": trade.net_amount,
            "strategy_id": getattr(trade, "strategy_id", ""),
            "timestamp": trade.trade_time,
        }
        self.trade_records.append(rec)
        self._append(Record("trade", rec["timestamp"], rec))

    def record_position(self, position):
        """记录持仓快照（Position 点）"""
        rec = {
            "symbol": position.symbol,
            "side": getattr(position.side, "value", str(getattr(position, "side", ""))),
            "qty": getattr(position, "qty", 0.0),
            "available_qty": getattr(position, "available_qty", 0.0),
            "avg_price": getattr(position, "avg_price", 0.0),
            "market_value": getattr(position, "market_value", 0.0),
            "unrealized_pnl": getattr(position, "unrealized_pnl", 0.0),
            "realized_pnl": getattr(position, "realized_pnl", 0.0),
            "timestamp": datetime.now(),
        }
        self.position_records.append(rec)
        self._append(Record("position", rec["timestamp"], rec))

    def record_equity(self, equity_curve_point: dict):
        """记录净值点（Equity 点）"""
        rec = {
            "datetime": equity_curve_point["datetime"],
            "equity": equity_curve_point["equity"],
            "cash": equity_curve_point["cash"],
            "market_value": equity_curve_point["market_value"],
        }
        self.equity_records.append(rec)
        self._append(Record("equity", rec["datetime"], rec))

    def record_drawdown(self, drawdown: float, timestamp: Any):
        """记录回撤（Drawdown 点）"""
        rec = {"drawdown": drawdown, "timestamp": timestamp}
        self.equity_records.append(rec)          # 与净值同表，便于画副图
        self._append(Record("equity", timestamp, rec))

    def record_stop(self, stop_event: dict):
        """记录止损触发（Stop 点：看风控退出）"""
        rec = {
            "symbol": stop_event.get("symbol", ""),
            "trigger_price": stop_event.get("trigger_price", 0.0),
            "fill_price": stop_event.get("fill_price", 0.0),
            "action": stop_event.get("action", ""),
            "reason": stop_event.get("reason", ""),
            "timestamp": stop_event.get("timestamp", datetime.now()),
        }
        self.stop_records.append(rec)
        self._append(Record("stop", rec["timestamp"], rec))

    # ---------------- 内部 ----------------

    def _append(self, record: Record):
        self.records.append(record)

    # ---------------- 查询 / 导出 ----------------

    def get(self, record_type: str) -> List[dict]:
        """按类型取记录（list[dict]）"""
        tables = {
            "bar": self.bar_records, "indicator": self.indicator_records,
            "signal": self.signal_records, "order": self.order_records,
            "trade": self.trade_records, "position": self.position_records,
            "equity": self.equity_records, "risk_reject": self.risk_reject_records,
            "stop": self.stop_records,
        }
        return list(tables.get(record_type, []))

    def to_dataframe(self, record_type: Optional[str] = None):
        """导出为 pandas DataFrame（按类型默认同名分表）"""
        try:
            import pandas as pd
        except ImportError:
            return None
        if record_type:
            return pd.DataFrame(self.get(record_type))
        return {t: pd.DataFrame(self.get(t)) for t in [
            "bar", "indicator", "signal", "order", "trade",
            "position", "equity", "risk_reject", "stop"]}

    def summary(self) -> str:
        """记录统计摘要"""
        lines = ["BacktestRecorder 记录摘要"]
        counts = {
            "bar": len(self.bar_records), "indicator": len(self.indicator_records),
            "signal": len(self.signal_records), "order": len(self.order_records),
            "trade": len(self.trade_records), "position": len(self.position_records),
            "equity": len(self.equity_records), "risk_reject": len(self.risk_reject_records),
            "stop": len(self.stop_records),
        }
        for k, v in counts.items():
            lines.append(f"  {k}: {v}")
        return "\n".join(lines)
