"""
Quant V2 回测可视化演示脚本

链路：Data -> Strategy -> Signal -> Risk -> Broker -> Portfolio
     -> BacktestRecorder(全程记录) -> VisualExporter(导出 HTML/JSON/CSV)

核心验证（口径一致）：
  图上的 sell/buy 点来自 recorder 记录的 Trade（与 portfolio 入账一致）；
  指标由引擎在 bar 处附带上报（与策略实际计算一致），不做事后重算。

用法：
  python3 scripts/visualize_backtest.py [symbol] [out_prefix]
"""

import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data.bar import Bar, BarFlags
from strategy.donchian import DonchianStrategy
from risk.risk_manager import RiskManager, RiskConfig
from risk.position_sizer import ATRSizer
from portfolio.portfolio import Portfolio
from broker.fee_model import ChinaAFeeModel
from broker.backtest_broker import BacktestBroker
from engine.backtest_engine import BacktestEngine
from visualization.recorder import BacktestRecorder
from visualization.exporter import VisualExporter


def load_sample_data(symbol: str = "TEST001", n: int = 300) -> list:
    """与 main.py 一致的分段示例数据（趋势 + 盘整，触发多次突破）"""
    import random
    import datetime as _dt

    random.seed(123)
    bars = []
    base = 100.0
    segments = [
        (50, 0.004, 0.006), (40, -0.001, 0.010),
        (60, 0.006, 0.008), (50, -0.005, 0.010),
        (60, 0.005, 0.007), (40, -0.002, 0.009),
    ]
    start = _dt.date(2023, 1, 3)
    day = 0
    price = base
    for seg_len, drift, vol in segments:
        for _ in range(seg_len):
            day += 1
            dt = _dt.datetime.combine(start + _dt.timedelta(days=day), _dt.time(15, 0))
            while dt.weekday() >= 5:
                day += 1
                dt = _dt.datetime.combine(start + _dt.timedelta(days=day), _dt.time(15, 0))
            returns = random.gauss(drift, vol)
            prev_close = price
            price = max(1.0, price * (1 + returns))
            o = prev_close
            c = price
            h = max(o, c) * (1 + abs(random.gauss(0, vol / 3)))
            l = min(o, c) * (1 - abs(random.gauss(0, vol / 3)))
            bars.append(Bar(symbol=symbol, datetime=dt, open=o, high=h, low=l,
                            close=c, volume=random.randint(5000, 300000), amount=0.0))
    return bars


def run(symbol="TEST001", out_prefix="outputs/visual"):
    os.makedirs(os.path.dirname(out_prefix) or ".", exist_ok=True)

    bars = load_sample_data(symbol)
    print(f"[data] 加载 {len(bars)} 根 bar")

    # --- 组装回测 ---
    strategy = DonchianStrategy(entry_period=20, exit_period=10, atr_period=20, atr_multiplier=2)
    portfolio = Portfolio(initial_cash=100000.0)
    risk = RiskManager(RiskConfig(max_single_trade_amount=1e9, max_single_trade_ratio=0.9,
                                  max_position_ratio=0.6))
    sizer = ATRSizer(risk_percent=0.02, atr_multiplier=2.0, atr_period=20, min_qty=100.0)
    broker = BacktestBroker(fee_model=ChinaAFeeModel())

    # 记录器：可选注入，不改变回测行为
    recorder = BacktestRecorder()
    engine = BacktestEngine(
        strategy=strategy, portfolio=portfolio, broker=broker,
        risk_manager=risk, position_sizer=sizer,
        symbol=symbol, recorder=recorder,
    )

    # --- 运行 ---
    result = engine.run(bars)
    print(f"[backtest] {result}")

    # --- 可视化 ---
    # 指标已由 BacktestEngine 在 strategy.on_bar 后调用 record_indicator 自动上报，
    # 口径 = 策略内部真实计算（entry_high/exit_low/atr/close），此处不再重复上报。
    exporter = VisualExporter(recorder)

    html = exporter.render_html(f"{out_prefix}.html", symbol=symbol)
    exporter.to_json(f"{out_prefix}.json")
    exporter.export_equity_csv(f"{out_prefix}_equity.csv")
    print(f"[export] 已生成：{html}")

    # --- 一致性自检 ---
    check(recorder, engine, portfolio)
    return recorder, engine


def check(recorder, engine, portfolio):
    """口径一致性自检：交易点=Trade、净值=Portfolio、记录与引擎一致"""
    ok = True
    trades = recorder.get("trade")
    # 1. 成交点 == portfolio.trades
    n_rec = len(trades)
    n_port = len(portfolio.trades)
    if n_rec == n_port and all(
        t["trade_id"] == pt.trade_id for t, pt in zip(trades, portfolio.trades)
    ):
        print("[check] 交易点 == Portfolio.trades ✓")
    else:
        print(f"[check] ✗ 交易点数不一致 recorder={n_rec} portfolio={n_port}")
        ok = False
    # 2. 净值末点 == 最终权益
    eq = recorder.get("equity")
    eq_final = [r for r in eq if "equity" in r]
    if eq_final:
        last_eq = eq_final[-1]["equity"]
        port_eq = portfolio.account.equity
        if abs(last_eq - port_eq) < 1e-6:
            print(f"[check] 净值末点 == Portfolio 权益({last_eq:.2f}) ✓")
        else:
            print(f"[check] ✗ 净值不一致 recorder={last_eq} portfolio={port_eq}")
            ok = False
    # 3. 信号数 >= 成交数 + 拒绝数（有意图不一定成交）
    n_sig = len(recorder.get("signal"))
    n_rej = len(recorder.get("risk_reject"))
    print(f"[check] 信号={n_sig} 订单={len(recorder.get('order'))} 成交={n_rec} 拒绝={n_rej}")
    return ok


if __name__ == "__main__":
    sym = sys.argv[1] if len(sys.argv) > 1 else "TEST001"
    out = sys.argv[2] if len(sys.argv) > 2 else "outputs/visual"
    run(sym, out)
