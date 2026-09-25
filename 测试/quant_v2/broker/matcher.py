"""
Quant V2 订单撮合器

撮合规则：
- 市价单：按 bar.open 成交（订单是上一bar信号产生的）
- 限价单：买入 bar.low <= limit_price 才成交；卖出 bar.high >= limit_price
- 止损单/止损限价：触发后转限价/市价
- 涨跌停：涨停不可买入、跌停不可卖出（A股）
- 停牌：拒单
- 成交量限制：单笔不超过 bar.volume × volume_limit_ratio
"""

from typing import Tuple

from data.bar import Bar
from portfolio.order import Order
from core.enums import Side, OrderType, OrderStatus


def _is_up_bar(bar: Bar) -> bool:
    return bar.close >= bar.open


def _is_down_bar(bar: Bar) -> bool:
    return bar.close < bar.open


class OrderMatcher:

    def __init__(self, volume_limit_ratio: float = 0.1, use_price_limit: bool = True):
        self.volume_limit_ratio = volume_limit_ratio
        self.use_price_limit = use_price_limit

    def match(self, order: Order, bar: Bar) -> Tuple[OrderStatus, float, float, str]:
        if bar.flags and bar.flags.is_suspended:
            return OrderStatus.REJECTED, 0.0, 0.0, "标的停牌，无法成交"
        if bar.flags and bar.flags.is_delisted:
            return OrderStatus.REJECTED, 0.0, 0.0, "标的已退市"

        limit_rejected, reason = self._check_price_limit(order, bar)
        if limit_rejected:
            return OrderStatus.REJECTED, 0.0, 0.0, reason

        fillable, fill_price = self._determine_fill(order, bar)
        if not fillable:
            return OrderStatus.NEW, 0.0, 0.0, ""

        max_volume = self._max_fill_volume(bar)
        remaining = order.remaining_qty
        fill_qty = min(remaining, max_volume)

        if fill_qty <= 0:
            return OrderStatus.NEW, 0.0, 0.0, "无可用流动性"

        if fill_qty >= remaining:
            return OrderStatus.FILLED, fill_price, fill_qty, ""
        else:
            return OrderStatus.PART_FILLED, fill_price, fill_qty, ""

    def _check_price_limit(self, order: Order, bar: Bar) -> Tuple[bool, str]:
        """
        涨跌停 / 一字板检查

        成交规则（用户约定）：
        - 以产生信号的下一个交易日（bar）撮合成交
        - 除了一字板外均可成交
        - 一字板：当日 high == low。一字涨停买单无法成交、一字跌停卖单无法成交。
        """
        flags = bar.flags
        is_yiziban = (bar.high == bar.low)
        up_bar = flags.limit_up if (flags is not None and flags.limit_up) else (is_yiziban and _is_up_bar(bar))
        down_bar = flags.limit_down if (flags is not None and flags.limit_down) else (is_yiziban and _is_down_bar(bar))

        if self.use_price_limit:
            if order.side == Side.BUY and up_bar:
                return True, "一字涨停，买入无法成交"
            if order.side == Side.SELL and down_bar:
                return True, "一字跌停，卖出无法成交"
        return False, ""

    def _determine_fill(self, order: Order, bar: Bar) -> Tuple[bool, float]:
        if order.order_type == OrderType.MARKET:
            return True, bar.open
        elif order.order_type == OrderType.LIMIT:
            if order.side == Side.BUY:
                if bar.low <= order.price:
                    return True, min(bar.open, order.price)
            else:
                if bar.high >= order.price:
                    return True, max(bar.open, order.price)
            return False, 0.0
        elif order.order_type == OrderType.STOP:
            if order.side == Side.BUY:
                if bar.high >= order.stop_price:
                    return True, max(bar.open, order.stop_price)
            else:
                if bar.low <= order.stop_price:
                    return True, min(bar.open, order.stop_price)
            return False, 0.0
        elif order.order_type == OrderType.STOP_LIMIT:
            triggered = False
            if order.side == Side.BUY and bar.high >= order.stop_price:
                triggered = True
            elif order.side == Side.SELL and bar.low <= order.stop_price:
                triggered = True
            if not triggered:
                return False, 0.0
            if order.side == Side.BUY:
                if bar.low <= order.price:
                    return True, min(bar.open, order.price)
            else:
                if bar.high >= order.price:
                    return True, max(bar.open, order.price)
            return False, 0.0
        return False, 0.0

    def _max_fill_volume(self, bar: Bar) -> float:
        if bar.volume <= 0:
            return float("inf")
        return bar.volume * self.volume_limit_ratio
