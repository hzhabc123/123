"""
Quant V2 回测经纪商

职责：
- 接收订单（submit_order），维护挂单队列
- 每个 bar 由引擎调用 match_orders 撮合挂单
- 成交后计算费用、生成 Trade、回调 Portfolio
- 支持撤单、查询挂单
"""

from datetime import datetime
from itertools import count
from typing import Callable, Dict, List, Optional

from data.bar import Bar
from portfolio.order import Order
from portfolio.trade import Trade
from broker.fee_model import FeeModel, ChinaAFeeModel, FeeBreakdown
from broker.matcher import OrderMatcher
from core.enums import OrderStatus, Side, TimeInForce


_order_counter = count(1)
_trade_counter = count(1)


class BacktestBroker:

    def __init__(self, fee_model: Optional[FeeModel] = None,
                 matcher: Optional[OrderMatcher] = None,
                 on_trade_callback: Optional[Callable[[Trade], None]] = None):
        self.fee_model = fee_model or ChinaAFeeModel()
        self.matcher = matcher or OrderMatcher()
        self.on_trade_callback = on_trade_callback
        self._orders: Dict[str, Order] = {}
        self._pending: List[str] = []
        self._last_trades: List[Trade] = []

    def create_order(self, symbol: str, side: Side, order_type, price: float,
                     qty: float, stop_price: float = 0.0, strategy_id: str = "") -> Order:
        order = Order(
            order_id=f"O{next(_order_counter):06d}", symbol=symbol, side=side,
            order_type=order_type, price=price, qty=qty, stop_price=stop_price,
            strategy_id=strategy_id, create_time=datetime.now(),
        )
        self.submit_order(order)
        return order

    def submit_order(self, order: Order) -> Order:
        if order.qty <= 0:
            order.reject("订单数量必须大于0")
            return order
        self._orders[order.order_id] = order
        self._pending.append(order.order_id)
        return order

    def cancel_order(self, order_id: str) -> bool:
        order = self._orders.get(order_id)
        if order is None or not order.is_active:
            return False
        order.cancel()
        if order_id in self._pending:
            self._pending.remove(order_id)
        return True

    def pending_orders(self, symbol: Optional[str] = None) -> List[Order]:
        result = [self._orders[oid] for oid in self._pending]
        if symbol is not None:
            result = [o for o in result if o.symbol == symbol]
        return result

    def get_order(self, order_id: str) -> Optional[Order]:
        return self._orders.get(order_id)

    def all_orders(self) -> List[Order]:
        return list(self._orders.values())

    def match_orders(self, bar: Bar) -> List[Trade]:
        self._last_trades = []
        if bar.flags and bar.flags.is_suspended:
            return self._last_trades

        pending_snapshot = list(self._pending)
        still_pending: List[str] = []

        for order_id in pending_snapshot:
            order = self._orders[order_id]
            if not order.is_active:
                continue

            status, fill_price, fill_qty, reject_reason = self.matcher.match(order, bar)

            if status == OrderStatus.REJECTED:
                order.reject(reject_reason)
                continue

            if status in (OrderStatus.FILLED, OrderStatus.PART_FILLED) and fill_qty > 0:
                trade = self._create_trade(order, fill_price, fill_qty, bar)
                self._last_trades.append(trade)
                if self.on_trade_callback is not None:
                    self.on_trade_callback(trade)

            if order.is_active:
                if order.time_in_force == TimeInForce.IOC and order.status != OrderStatus.FILLED:
                    order.cancel()
                    continue
                still_pending.append(order_id)

        self._pending = still_pending
        return self._last_trades

    @property
    def last_trades(self) -> List[Trade]:
        return self._last_trades

    def _create_trade(self, order: Order, fill_price: float, fill_qty: float, bar: Bar) -> Trade:
        order.fill(fill_price, fill_qty)
        notional = fill_price * fill_qty
        fees: FeeBreakdown = self.fee_model.calculate(
            side=order.side, price=fill_price, qty=fill_qty, notional=notional,
        )
        return Trade(
            trade_id=f"T{next(_trade_counter):06d}", order_id=order.order_id,
            symbol=order.symbol, side=order.side, price=fill_price, qty=fill_qty,
            commission=fees.total, slippage=fees.slippage_cost, trade_time=bar.datetime,
            strategy_id=order.strategy_id, fee_breakdown=fees,
        )
