#!/usr/bin/env python3
"""真实行情回测脚本 —— 模块4验证入口"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from datetime import datetime

from data.data_manager import DataManager
from data.akshare_source import AkshareDataSource
from strategy.donchian import DonchianStrategy
from risk.risk_manager import RiskManager, RiskConfig
from risk.position_sizer import ATRSizer
from portfolio.portfolio import Portfolio
from broker.fee_model import ChinaAFeeModel
from broker.backtest_broker import BacktestBroker
from broker.matcher import OrderMatcher
from engine.backtest_engine import BacktestEngine
from performance.analyzer import PerformanceAnalyzer


def parse_date(s):
    return datetime.strptime(s, "%Y%m%d").date()


def main():
    symbol = sys.argv[1] if len(sys.argv) > 1 else "600519"
    start = parse_date(sys.argv[2]) if len(sys.argv) > 2 else datetime(2024, 1, 1).date()
    end = parse_date(sys.argv[3]) if len(sys.argv) > 3 else datetime(2024, 12, 31).date()

    dm = DataManager({"akshare": AkshareDataSource()})
    bars = dm.get_bars(symbol, start, end, adjust="qfq")
    print(f"[data] {symbol}: {len(bars)} bars, {start} -> {end}")
    if not bars:
        print("[data] 无数据"); return

    risk_cfg = RiskConfig(max_position_ratio=0.90, max_single_trade_ratio=0.95, max_single_trade_amount=1e9)
    portfolio = Portfolio(initial_cash=1_000_000.0)
    engine = BacktestEngine(
        strategy=DonchianStrategy(entry_period=20, exit_period=10, atr_period=20, atr_multiplier=2.0),
        portfolio=portfolio, symbol=symbol,
        broker=BacktestBroker(fee_model=ChinaAFeeModel(), matcher=OrderMatcher(use_price_limit=True)),
        risk_manager=RiskManager(config=risk_cfg),
        position_sizer=ATRSizer(risk_percent=0.02, atr_multiplier=2.0),
    )
    engine.run(bars)

    summary = engine._summarize()
    print("\n===== 回测结果 =====")
    print(f"成交笔数 : {len(portfolio.trades)}")
    print(f"初始权益 : {portfolio.account.initial_cash:,.0f}")
    print(f"期末权益 : {summary.get('final_equity', 0):,.0f}")
    perf = PerformanceAnalyzer(engine.get_equity_curve(), portfolio.trades)
    m = perf.compute()
    print(f"{'总收益率':<10}: {m.total_return:8.2%}")
    print(f"{'年化收益':<10}: {m.annual_return:8.2%}")
    print(f"{'最大回撤':<10}: {m.max_drawdown:8.2%}")
    print(f"{'夏普比率':<10}: {m.sharpe_ratio:8.2f}")
    print(f"{'年化波动':<10}: {m.annual_volatility:8.2%}")
    print(f"{'胜率':<10}: {m.win_rate:8.2%}")
    print(f"{'盈亏比':<10}: {m.profit_loss_ratio:8.2f}")
    print(f"{'换手率':<10}: {m.turnover:8.2%}")
    print(f"\n[成交明细]")
    for t in portfolio.trades:
        print(f"  {t.side.value:<5} {t.symbol} @ {t.price:9,.2f} x {t.qty:6.0f}  佣金 {t.commission:.2f}")


if __name__ == "__main__":
    main()
