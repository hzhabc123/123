"""Broker 模块测试：费用模型 + 撮合器"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from datetime import datetime

from core.enums import Side, OrderType, OrderStatus, TimeInForce
from data.bar import Bar, BarFlags
from broker.fee_model import ChinaAFeeModel, USStockFeeModel, CryptoFeeModel, create_fee_model
from broker.matcher import OrderMatcher
from broker.backtest_broker import BacktestBroker
from portfolio.order import Order


class TestChinaAFeeModel:
    def test_buy_commission(self):
        m = ChinaAFeeModel()
        fees = m.calculate(Side.BUY, 10.0, 1000)
        assert fees.commission == pytest.approx(5.0)
        assert fees.stamp_tax == 0.0
        assert fees.transfer_fee == pytest.approx(0.1)

    def test_sell_stamp_tax(self):
        m = ChinaAFeeModel()
        fees = m.calculate(Side.SELL, 10.0, 1000)
        assert fees.stamp_tax == pytest.approx(10000 * 0.0005)

    def test_total_handwr_check(self):
        m = ChinaAFeeModel()
        fees = m.calculate(Side.BUY, 10.0, 1000)
        assert fees.total == pytest.approx(5.1)
        assert fees.all_in_cost == pytest.approx(6.1)


class TestFeeFactory:
    def test_create_china(self):
        assert isinstance(create_fee_model("china_stock"), ChinaAFeeModel)
    def test_create_us(self):
        assert isinstance(create_fee_model("us_stock"), USStockFeeModel)
    def test_create_crypto(self):
        assert isinstance(create_fee_model("crypto"), CryptoFeeModel)
    def test_unknown(self):
        with pytest.raises(ValueError):
            create_fee_model("mars")


def make_bar(open_, high, low, close, volume=1000000, timestamp=datetime(2024,1,1), suspended=False, limit_up=False, limit_down=False):
    return Bar(symbol="TEST", datetime=timestamp, open=open_, high=high, low=low, close=close,
               volume=volume, flags=BarFlags(is_suspended=suspended, limit_up=limit_up, limit_down=limit_down))


class TestOrderMatcher:
    def test_market_buy_fills_at_open(self):
        matcher = OrderMatcher()
        order = Order("O1", "TEST", Side.BUY, OrderType.MARKET, price=0, qty=100)
        bar = make_bar(10.0, 10.5, 9.8, 10.2)
        status, price, qty, _ = matcher.match(order, bar)
        assert status == OrderStatus.FILLED
        assert price == pytest.approx(10.0)
        assert qty == 100

    def test_limit_buy_when_low_below_price(self):
        matcher = OrderMatcher()
        order = Order("O1", "TEST", Side.BUY, OrderType.LIMIT, price=10.0, qty=100)
        bar = make_bar(10.2, 10.5, 9.8, 10.0)
        status, price, qty, _ = matcher.match(order, bar)
        assert status == OrderStatus.FILLED
        assert price == pytest.approx(10.0)

    def test_limit_buy_not_filled_when_not_touch(self):
        matcher = OrderMatcher()
        order = Order("O1", "TEST", Side.BUY, OrderType.LIMIT, price=9.5, qty=100)
        bar = make_bar(9.8, 10.0, 9.7, 9.9)
        status, _, _, _ = matcher.match(order, bar)
        assert status == OrderStatus.NEW

    def test_limit_sell_fills(self):
        matcher = OrderMatcher()
        order = Order("O1", "TEST", Side.SELL, OrderType.LIMIT, price=10.0, qty=100)
        bar = make_bar(9.9, 10.2, 9.8, 10.1)
        status, price, qty, _ = matcher.match(order, bar)
        assert status == OrderStatus.FILLED
        assert price == pytest.approx(10.0)

    def test_suspended_rejected(self):
        matcher = OrderMatcher()
        order = Order("O1", "TEST", Side.BUY, OrderType.MARKET, price=0, qty=100)
        bar = make_bar(10, 10, 10, 10, suspended=True)
        status, _, _, reason = matcher.match(order, bar)
        assert status == OrderStatus.REJECTED
        assert "停牌" in reason

    def test_limit_up_buy_rejected(self):
        matcher = OrderMatcher()
        order = Order("O1", "TEST", Side.BUY, OrderType.MARKET, price=0, qty=100)
        bar = make_bar(10, 10, 10, 10, limit_up=True)
        status, _, _, _ = matcher.match(order, bar)
        assert status == OrderStatus.REJECTED

    def test_volume_limit_partial_fill(self):
        matcher = OrderMatcher(volume_limit_ratio=0.1)
        order = Order("O1", "TEST", Side.BUY, OrderType.MARKET, price=0, qty=200)
        bar = make_bar(10, 10.2, 9.8, 10, volume=1000)
        status, _, qty, _ = matcher.match(order, bar)
        assert status == OrderStatus.PART_FILLED
        assert qty == 100

    def test_stop_loss_sell(self):
        matcher = OrderMatcher()
        order = Order("O1", "TEST", Side.SELL, OrderType.STOP, price=0, qty=100, stop_price=9.5)
        bar = make_bar(9.8, 9.9, 9.3, 9.4)
        status, price, _, _ = matcher.match(order, bar)
        assert status == OrderStatus.FILLED
        assert price == pytest.approx(9.5)


class TestBacktestBroker:
    def test_submit_and_match_buy(self):
        broker = BacktestBroker()
        order = broker.create_order("TEST", Side.BUY, OrderType.MARKET, price=0, qty=100)
        assert order.status == OrderStatus.NEW
        trades = broker.match_orders(make_bar(10, 10.5, 9.8, 10.2))
        assert len(trades) == 1
        assert trades[0].qty == 100
        assert trades[0].price == pytest.approx(10.0)
        assert trades[0].commission == pytest.approx(5.01)

    def test_pending_after_match(self):
        broker = BacktestBroker()
        broker.create_order("TEST", Side.BUY, OrderType.MARKET, price=0, qty=100)
        broker.match_orders(make_bar(10, 10.2, 9.8, 10))
        assert len(broker.pending_orders()) == 0

    def test_pending_limit_not_filled(self):
        broker = BacktestBroker()
        broker.create_order("TEST", Side.BUY, OrderType.LIMIT, price=9.0, qty=100)
        broker.match_orders(make_bar(9.5, 9.6, 9.4, 9.5))
        assert len(broker.pending_orders()) == 1

    def test_cancel_order(self):
        broker = BacktestBroker()
        order = broker.create_order("TEST", Side.BUY, OrderType.MARKET, price=0, qty=100)
        assert broker.cancel_order(order.order_id) is True
        assert order.status == OrderStatus.CANCELLED
        assert len(broker.pending_orders()) == 0

    def test_partial_fill_keeps_pending(self):
        broker = BacktestBroker(matcher=OrderMatcher(volume_limit_ratio=0.1))
        broker.create_order("TEST", Side.BUY, OrderType.MARKET, price=0, qty=500)
        trades = broker.match_orders(make_bar(10, 10.2, 9.8, 10, volume=1000))
        assert len(trades) == 1
        assert trades[0].qty == 100
        assert len(broker.pending_orders()) == 1

    def test_callback(self):
        received = []
        broker = BacktestBroker(on_trade_callback=lambda t: received.append(t))
        broker.create_order("TEST", Side.BUY, OrderType.MARKET, price=0, qty=100)
        broker.match_orders(make_bar(10, 10.2, 9.8, 10))
        assert len(received) == 1


class TestOneBoard:
    def _broker_with_matcher(self, **kw):
        return BacktestBroker(matcher=OrderMatcher(use_price_limit=True))

    def test_yiziban_up_buy_rejected(self):
        broker = self._broker_with_matcher()
        broker.create_order("TEST", Side.BUY, OrderType.MARKET, price=0, qty=100)
        trades = broker.match_orders(make_bar(10, 10, 10, 10))
        assert len(trades) == 0
        assert len(broker.pending_orders()) == 0

    def test_yiziban_down_sell_rejected(self):
        broker = self._broker_with_matcher()
        broker.create_order("TEST", Side.SELL, OrderType.MARKET, price=0, qty=100)
        trades = broker.match_orders(make_bar(10, 10, 10, 9.9))
        assert len(trades) == 0

    def test_yiziban_up_sell_fills(self):
        broker = self._broker_with_matcher()
        broker.create_order("TEST", Side.SELL, OrderType.MARKET, price=0, qty=100)
        trades = broker.match_orders(make_bar(10, 10, 10, 10))
        assert len(trades) == 1

    def test_yiziban_down_buy_fills(self):
        broker = self._broker_with_matcher()
        broker.create_order("TEST", Side.BUY, OrderType.MARKET, price=0, qty=100)
        trades = broker.match_orders(make_bar(10, 10, 10, 9.9))
        assert len(trades) == 1

    def test_normal_bar_all_fill(self):
        broker = self._broker_with_matcher()
        broker.create_order("TEST", Side.BUY, OrderType.MARKET, price=0, qty=100)
        trades = broker.match_orders(make_bar(10, 10.5, 9.8, 10.2))
        assert len(trades) == 1

    def test_flagged_limit_up_buy_rejected(self):
        broker = self._broker_with_matcher()
        broker.create_order("TEST", Side.BUY, OrderType.MARKET, price=0, qty=100)
        trades = broker.match_orders(make_bar(11, 11, 10, 10.9, limit_up=True))
        assert len(trades) == 0
