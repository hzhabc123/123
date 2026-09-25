#!/usr/bin/env python3
"""模块5验收：常见策略库在真实行情上的擂台对比"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from datetime import datetime

from data.data_manager import DataManager
from data.akshare_source import AkshareDataSource
from portfolio.portfolio import Portfolio
from broker.fee_model import ChinaAFeeModel
from broker.backtest_broker import BacktestBroker
from broker.matcher import OrderMatcher
from risk.risk_manager import RiskManager, RiskConfig
from risk.position_sizer import FixedSizer
from engine.backtest_engine import BacktestEngine
from performance.analyzer import PerformanceAnalyzer

from strategy.ma_cross import MACrossStrategy
from strategy.bollinger import BollingerStrategy
from strategy.rsi import RSIStrategy
from strategy.turtle import TurtleStrategy
from strategy.momentum import MomentumStrategy


def backtest(strategy, bars, symbol):
    portfolio = Portfolio(initial_cash=1_000_000.0)
    risk_cfg = RiskConfig(max_position_ratio=0.9, max_single_trade_ratio=0.95, max_single_trade_amount=1e9)
    engine = BacktestEngine(
        strategy=strategy, portfolio=portfolio, symbol=symbol,
        broker=BacktestBroker(fee_model=ChinaAFeeModel(), matcher=OrderMatcher(use_price_limit=True)),
        risk_manager=RiskManager(config=risk_cfg),
        position_sizer=FixedSizer(qty=100),
    )
    engine.run(bars)
    m = PerformanceAnalyzer(engine.get_equity_curve(), portfolio.trades).compute()
    return len(portfolio.trades), m


def fmt_percent(v): return f"{v*100:7.2f}%"


def main():
    dm = DataManager({"akshare": AkshareDataSource()})
    specs = [("600519", "贵州茅台"), ("000001", "平安银行"), ("600036", "招商银行")]
    strategies = [("双均线", MACrossStrategy), ("布林带", BollingerStrategy), ("RSI", RSIStrategy), ("海龟", TurtleStrategy), ("动量", MomentumStrategy)]
    print(f"{'策略':<8}{'标的':<10}{'成交':<6}{'收益':<10}{'回撤':<10}{'夏普':<8}{'胜率':<8}")
    print("-" * 62)
    for sym, name in specs:
        bars = dm.get_bars(sym, datetime(2024, 1, 1).date(), datetime(2024, 12, 31).date(), adjust="qfq")
        if not bars:
            print(f"{'':<8}{name}: 无数据"); continue
        for sname, cls in strategies:
            try:
                trades, m = backtest(cls(), bars, sym)
                print(f"{sname:<8}{name:<10}{trades:<6}{fmt_percent(m.total_return):<10}{fmt_percent(m.max_drawdown):<10}{m.sharpe_ratio:<8.2f}{fmt_percent(m.win_rate):<8}")
            except Exception as e:
                print(f"{sname:<8}{name:<10} ERR: {e}")


if __name__ == "__main__":
    main()
