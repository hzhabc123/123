"""策略库测试：双均线/布林带/RSI/海龟/动量"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from datetime import datetime, timedelta

from data.bar import Bar
from portfolio.portfolio import Portfolio
from broker.backtest_broker import BacktestBroker
from broker.matcher import OrderMatcher
from broker.fee_model import ChinaAFeeModel
from risk.risk_manager import RiskManager, RiskConfig
from risk.position_sizer import FixedSizer
from engine.backtest_engine import BacktestEngine
from strategy.ma_cross import MACrossStrategy
from strategy.bollinger import BollingerStrategy
from strategy.rsi import RSIStrategy
from strategy.turtle import TurtleStrategy
from strategy.momentum import MomentumStrategy


def make_bars(closes, start=datetime(2024, 1, 1)):
    bars = []
    prev_close = closes[0]
    for i, c in enumerate(closes):
        dt = start + timedelta(days=i)
        high = max(c, prev_close) * 1.01
        low = min(c, prev_close) * 0.99
        o = prev_close
        bars.append(Bar(symbol="TEST", datetime=dt, open=o, high=high, low=low, close=c, volume=10_000, flags=None))
        prev_close = c
    return bars


def run_strategy(strategy, bars, initial_cash=1_000_000.0):
    portfolio = Portfolio(initial_cash=initial_cash)
    risk_cfg = RiskConfig(max_position_ratio=0.9, max_single_trade_ratio=0.95, max_single_trade_amount=1e9)
    engine = BacktestEngine(
        strategy=strategy, portfolio=portfolio, symbol="TEST",
        broker=BacktestBroker(fee_model=ChinaAFeeModel(), matcher=OrderMatcher(use_price_limit=True)),
        risk_manager=RiskManager(config=risk_cfg),
        position_sizer=FixedSizer(qty=100),
    )
    engine.run(bars)
    return len(portfolio.trades)


def _trend_up(n=60):
    base = 100.0
    return [base + 0.5 * i for i in range(n)]

def _trend_down(n=60):
    base = 200.0
    return [base - 0.4 * i for i in range(n)]

def _oscillating(n=80):
    import math
    base = 100.0
    return [base + 15 * math.sin(i / 5) for i in range(n)]


class TestMACrossStrategy:
    def test_golden_cross_and_death_cross(self):
        data = [100 - i for i in range(30)] + [70 + i * 2 for i in range(30)] + [130 - i * 3 for i in range(20)]
        bars = make_bars(data)
        trades = run_strategy(MACrossStrategy(), bars)
        assert trades >= 1

    def test_no_trade_when_flat(self):
        bars = make_bars([100.0] * 60)
        trades = run_strategy(MACrossStrategy(), bars)
        assert trades == 0


class TestBollingerStrategy:
    def test_mean_reversion_entry_exit(self):
        bars = make_bars(_oscillating())
        trades = run_strategy(BollingerStrategy(), bars)
        assert trades >= 1

    def test_no_trade_when_flat(self):
        bars = make_bars([100.0] * 50)
        trades = run_strategy(BollingerStrategy(), bars)
        assert trades == 0


class TestRSIStrategy:
    def test_oversold_entry(self):
        data = [100 - i * 1.5 for i in range(25)] + [65 + i for i in range(30)]
        bars = make_bars(data)
        trades = run_strategy(RSIStrategy(), bars)
        assert trades >= 1


class TestTurtleStrategy:
    def test_breakout_entry_exit(self):
        data = [100 + (i % 3) for i in range(22)] + [103 + i * 2.5 for i in range(35)] + [190 - i * 5 for i in range(25)]
        bars = make_bars(data)
        trades = run_strategy(TurtleStrategy(), bars)
        assert trades >= 1


class TestMomentumStrategy:
    def test_momentum_entry_exit(self):
        data = [100 + i * 1.5 for i in range(35)] + [155 - i * 3 for i in range(25)]
        bars = make_bars(data)
        trades = run_strategy(MomentumStrategy(), bars)
        assert trades >= 1

    def test_no_trade_when_flat(self):
        bars = make_bars([100.0] * 40)
        trades = run_strategy(MomentumStrategy(), bars)
        assert trades == 0
