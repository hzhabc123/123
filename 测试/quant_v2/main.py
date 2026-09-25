#!/usr/bin/env python3
"""
Quant V2 回测系统主入口

完整链路：
  Data -> Strategy -> Signal -> RiskManager -> PositionSizer
       -> Broker(撮合+费用) -> Portfolio -> PerformanceAnalyzer -> Report
"""

import sys
import os
import random
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from data.bar import Bar, BarFlags
from strategy.donchian import DonchianStrategy
from risk.risk_manager import RiskManager, RiskConfig
from risk.position_sizer import ATRSizer
from risk.stop_manager import StopManager
from portfolio.portfolio import Portfolio
from broker.fee_model import ChinaAFeeModel
from broker.backtest_broker import BacktestBroker
from engine.backtest_engine import BacktestEngine
from performance import ReportGenerator


def load_sample_data(symbol: str = "TEST001", n: int = 300) -> list:
    import random
    import datetime as _dt

    random.seed(123)
    bars = []
    base_price = 100.0
    segments = [
        (50, 0.004, 0.006),
        (40, -0.001, 0.010),
        (60, 0.006, 0.008),
        (50, -0.005, 0.010),
        (60, 0.005, 0.007),
        (40, -0.002, 0.009),
    ]
    start_date = _dt.date(2023, 1, 3)
    day = 0

    for seg_len, drift, vol in segments:
        for _ in range(seg_len):
            day += 1
            dt = _dt.datetime.combine(start_date + _dt.timedelta(days=day), _dt.time(15, 0))
            while dt.weekday() >= 5:
                day += 1
                dt = _dt.datetime.combine(start_date + _dt.timedelta(days=day), _dt.time(15, 0))

            ret = drift + random.gauss(0, vol)
            open_price = base_price
            close_price = base_price * (1 + ret)
            high_price = max(open_price, close_price) * (1 + abs(random.gauss(0, vol * 0.5)))
            low_price = min(open_price, close_price) * (1 - abs(random.gauss(0, vol * 0.5)))

            bars.append(Bar(symbol=symbol, datetime=dt, open=round(open_price, 4),
                            high=round(high_price, 4), low=round(low_price, 4), close=round(close_price, 4),
                            volume=random.uniform(5000, 50000), amount=close_price * random.uniform(5000, 50000),
                            flags=BarFlags()))
            base_price = close_price

    return bars


def run_backtest(bars: list, symbol: str = "TEST001") -> BacktestEngine:
    portfolio = Portfolio(initial_cash=100000.0)
    strategy = DonchianStrategy(name="Donchian_Demo", entry_period=20, exit_period=10, atr_period=20, atr_multiplier=2.0)
    risk_manager = RiskManager(config=RiskConfig(max_position_ratio=0.3, max_single_trade_ratio=0.25, max_drawdown=0.2, max_daily_loss=5000.0))
    position_sizer = ATRSizer(risk_percent=0.02, atr_multiplier=2.0)
    stop_manager = StopManager()
    fee_model = ChinaAFeeModel()
    broker = BacktestBroker(fee_model=fee_model, on_trade_callback=portfolio.on_trade)
    engine = BacktestEngine(strategy=strategy, portfolio=portfolio, broker=broker, risk_manager=risk_manager, position_sizer=position_sizer, symbol=symbol)
    engine.run(bars)
    return engine


def main():
    print("=" * 60)
    print("Quant V2 回测系统")
    print("=" * 60)
    print("\n[1] 加载数据...")
    bars = load_sample_data(n=200)
    print(f"    加载 {len(bars)} 根Bar")
    print("\n[2] 运行回测引擎...")
    engine = run_backtest(bars)
    print(f"    事件数: {engine.event_count}  |  成交数: {len(engine.get_all_trades())}")
    print("\n[3] 绩效分析...")
    analyzer = engine.analyzer()
    metrics = analyzer.compute()
    print(analyzer.summary())
    print("\n[4] 生成报告...")
    report = ReportGenerator(analyzer, engine.get_all_trades(), engine.get_equity_curve())
    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "outputs")
    os.makedirs(out_dir, exist_ok=True)
    html_path = os.path.join(out_dir, "report.html")
    equity_csv = os.path.join(out_dir, "equity_curve.csv")
    report.generate_html(html_path)
    report.export_equity_csv(equity_csv)
    print(f"    HTML报告: {html_path}")
    print(f"    净值CSV:  {equity_csv}")
    print("\n" + "=" * 60)
    print("回测完成")
    print("=" * 60)
    return engine


if __name__ == "__main__":
    main()
