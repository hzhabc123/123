"""Engine 模块测试 + 事件引擎"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from datetime import datetime, timedelta

from core.enums import EventType, Side, OrderStatus
from data.bar import Bar, BarFlags
from event.event_engine import EventEngine, Event
from portfolio.portfolio import Portfolio
from broker.backtest_broker import BacktestBroker
from broker.matcher import OrderMatcher
from risk.risk_manager import RiskManager, RiskConfig
from risk.position_sizer import FixedSizer
from strategy.base_strategy import BaseStrategy
from strategy.donchian import DonchianStrategy
from engine.backtest_engine import BacktestEngine


class TestEventEngine:
    def test_subscribe_put(self):
        engine = EventEngine()
        received = []
        engine.subscribe(EventType.BAR, lambda ev: received.append(ev.data))
        engine.put(Event(EventType.BAR, {"close": 10}))
        assert received == [{"close": 10}]

    def test_emit(self):
        engine = EventEngine()
        received = []
        engine.subscribe(EventType.TRADE, lambda ev: received.append(ev))
        engine.emit(EventType.TRADE, 42, sender="test")
        assert received[0].data == 42
        assert received[0].sender == "test"

    def test_unsubscribe(self):
        engine = EventEngine()
        cb = lambda ev: None
        engine.subscribe(EventType.BAR, cb)
        assert engine.unsubscribe(EventType.BAR, cb) is True
        assert len(engine._subscribers[EventType.BAR]) == 0

    def test_priority_order(self):
        engine = EventEngine()
        order = []
        engine.subscribe(EventType.BAR, lambda ev: order.append("low"), priority=1)
        engine.subscribe(EventType.BAR, lambda ev: order.append("high"), priority=10)
        engine.emit(EventType.BAR, None)
        assert order == ["high", "low"]

    def test_handler_error_does_not_break(self):
        engine = EventEngine()
        received = []
        def bad(ev): raise RuntimeError("boom")
        engine.subscribe(EventType.BAR, bad)
        engine.subscribe(EventType.BAR, lambda ev: received.append("ok"))
        engine.emit(EventType.BAR, None)
        assert received == ["ok"]


class BuyHoldStrategy(BaseStrategy):
    def __init__(self, name="BuyHold", **kw):
        super().__init__(name=name, **kw)
        self.bought = False
    def on_bar(self, bar):
        if not self.bought and bar.close < 11:
            self.buy(bar.symbol, bar.close, qty=100, reason="test")
            self.bought = True


def make_bars(prices, volume=1_000_000, symbol="TEST"):
    bars = []
    for i, p in enumerate(prices):
        bars.append(Bar(symbol=symbol, datetime=datetime(2024, 1, 1 + i),
                        open=p, high=p*1.005, low=p*0.995, close=p, volume=volume, flags=BarFlags()))
    return bars


class TestBacktestEngine:
    def test_buy_and_sell_cycle(self):
        prices = [10.0, 12.0, 8.0]
        bars = make_bars(prices)
        portfolio = Portfolio(initial_cash=100000)
        engine = BacktestEngine(strategy=BuyHoldStrategy(), portfolio=portfolio, symbol="TEST", position_sizer=FixedSizer(100))
        result = engine.run(bars)
        assert result["trades"] >= 1
        first_fill = engine.all_trades[0]
        assert first_fill.price == pytest.approx(12.0)
        assert first_fill.qty == 100

    def test_cash_decreases_after_buy(self):
        prices = [10.0, 100.0, 101.0]
        bars = make_bars(prices)
        portfolio = Portfolio(initial_cash=100000)
        engine = BacktestEngine(strategy=BuyHoldStrategy(), portfolio=portfolio, symbol="TEST")
        engine.run(bars)
        assert portfolio.account.cash < 100000

    def test_equity_curve_recorded(self):
        prices = [10.0, 11.0, 12.0]
        bars = make_bars(prices)
        portfolio = Portfolio(initial_cash=100000)
        engine = BacktestEngine(strategy=BuyHoldStrategy(), portfolio=portfolio, symbol="TEST")
        engine.run(bars)
        assert len(engine.equity_curve) == 3

    def test_market_order_fills_next_bar_open(self):
        prices = [5.0, 100.0]
        bars = make_bars(prices)
        portfolio = Portfolio(initial_cash=100000)
        engine = BacktestEngine(strategy=BuyHoldStrategy(), portfolio=portfolio, symbol="TEST")
        engine.run(bars)
        trade = engine.all_trades[0]
        assert trade.price == pytest.approx(100.0)

    def test_fill_next_trading_day_not_same_day(self):
        bars = [
            Bar(symbol="TEST", datetime=datetime(2024,1,1), open=10.0, high=10.1, low=9.9, close=10.0, volume=1_000_000, flags=BarFlags()),
            Bar(symbol="TEST", datetime=datetime(2024,1,2), open=12.0, high=12.2, low=11.8, close=12.0, volume=1_000_000, flags=BarFlags()),
            Bar(symbol="TEST", datetime=datetime(2024,1,3), open=13.0, high=13.3, low=12.7, close=13.0, volume=1_000_000, flags=BarFlags()),
        ]
        portfolio = Portfolio(100000)
        engine = BacktestEngine(strategy=BuyHoldStrategy(), portfolio=portfolio, symbol="TEST")
        engine.run(bars)
        assert len(engine.all_trades) == 1
        trade = engine.all_trades[0]
        assert trade.trade_time == datetime(2024, 1, 2)
        assert trade.price == pytest.approx(12.0)
        assert bars[1].high != bars[1].low

    def test_fill_skipped_on_yiziban_next_day(self):
        class AlwaysBuy(BaseStrategy):
            def __init__(self, **kw):
                super().__init__(name="AlwaysBuy", **kw)
                self.done = False
            def on_bar(self, bar):
                if not self.done and bar.close < 11.0:
                    self.buy(bar.symbol, bar.close, qty=100)
                    self.done = True
        bars = [
            Bar(symbol="TEST", datetime=datetime(2024,1,1), open=10.0, high=10.1, low=9.9, close=10.0, volume=1_000_000, flags=BarFlags()),
            Bar(symbol="TEST", datetime=datetime(2024,1,2), open=10.5, high=10.5, low=10.5, close=10.5, volume=1_000_000, flags=BarFlags()),
            Bar(symbol="TEST", datetime=datetime(2024,1,3), open=11.0, high=11.2, low=10.8, close=11.0, volume=1_000_000, flags=BarFlags()),
        ]
        portfolio = Portfolio(100000)
        engine = BacktestEngine(strategy=AlwaysBuy(), portfolio=portfolio, symbol="TEST", broker=BacktestBroker(matcher=OrderMatcher(use_price_limit=True)))
        engine.run(bars)
        assert len(engine.all_trades) == 0

    def test_sell_reduces_position(self):
        class RoundTrip(BaseStrategy):
            def __init__(self, **kw):
                super().__init__(name="RoundTrip", **kw)
                self.step = 0
            def on_bar(self, bar):
                self.step += 1
                if self.step == 1:
                    self.buy(bar.symbol, bar.close, qty=100)
                elif self.step == 2:
                    self.sell(bar.symbol, bar.close, qty=100)
        bars = make_bars([10.0, 11.0, 12.0, 13.0])
        portfolio = Portfolio(100000)
        engine = BacktestEngine(strategy=RoundTrip(), portfolio=portfolio, symbol="TEST")
        engine.run(bars)
        assert len(portfolio.trades) == 2
        pos = portfolio.get_position("TEST")
        assert pos.qty == 0

    def test_donchian_runs_without_error(self):
        import random
        random.seed(42)
        bars = []
        price = 100.0
        base = datetime(2024, 1, 1)
        for i in range(200):
            price *= (1 + random.uniform(-0.02, 0.02))
            bars.append(Bar(symbol="TEST", datetime=base + timedelta(days=i),
                            open=price, high=price*1.01, low=price*0.99, close=price,
                            volume=5_000_000, flags=BarFlags()))
        portfolio = Portfolio(100000)
        engine = BacktestEngine(strategy=DonchianStrategy(entry_period=15, exit_period=8), portfolio=portfolio, symbol="TEST")
        result = engine.run(bars)
        assert result["bars"] == 200
        assert isinstance(result["final_equity"], (int, float))
