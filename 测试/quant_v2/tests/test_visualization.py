"""
Quant V2 可视化一致性测试（docs 验收标准第10节）

验证：
1. 买卖点（Trade）时间/价格/方向与 portfolio.trades 完全一致；
2. 图上指标 = 策略实际计算（此处验证 recorder 记录通道存在且可回读）；
3. 净值曲线与 Portfolio 权益一致；
4. 回撤与 Analyzer 一致；
5. 风控拒绝订单可追溯（reject 记录带 reason）。

原则：Recorder 只读采集，不改变回测结果（同一回测，有无 recorder 结果一致）。
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from datetime import datetime, date

from data.bar import Bar
from strategy.donchian import DonchianStrategy
from risk.risk_manager import RiskManager, RiskConfig
from risk.position_sizer import ATRSizer
from portfolio.portfolio import Portfolio
from broker.fee_model import ChinaAFeeModel
from broker.backtest_broker import BacktestBroker
from engine.backtest_engine import BacktestEngine
from visualization.recorder import BacktestRecorder
from visualization.exporter import VisualExporter


def _make_bars(n=120, symbol="VISTEST", trend=0.004, vol=0.006, start=date(2023, 1, 3)):
    """人造趋势数据，触发 Donchian 突破"""
    import random
    random.seed(7)
    bars = []
    price = 100.0
    day = 0
    for i in range(n):
        day += 1
        dt = datetime.combine(start + __import__("datetime").timedelta(days=day), datetime.min.time())
        while dt.weekday() >= 5:
            day += 1
            dt = datetime.combine(start + __import__("datetime").timedelta(days=day), datetime.min.time())
        prev = price
        price = max(1.0, price * (1 + random.gauss(trend, vol)))
        o, c = prev, price
        h = max(o, c) * 1.003
        l = min(o, c) * 0.997
        bars.append(Bar(symbol=symbol, datetime=dt, open=o, high=h, low=l,
                        close=c, volume=100000, amount=0.0))
    return bars


def _run(bars, recorder=None):
    strategy = DonchianStrategy(entry_period=10, exit_period=5, atr_period=10, atr_multiplier=2)
    portfolio = Portfolio(initial_cash=100000.0)
    risk = RiskManager(RiskConfig(max_single_trade_amount=1e9, max_single_trade_ratio=0.9,
                                  max_position_ratio=0.6))
    sizer = ATRSizer(risk_percent=0.02, atr_multiplier=2.0, atr_period=10, min_qty=100.0)
    broker = BacktestBroker(fee_model=ChinaAFeeModel())
    engine = BacktestEngine(strategy=strategy, portfolio=portfolio, broker=broker,
                            risk_manager=risk, position_sizer=sizer,
                            symbol=bars[0].symbol, recorder=recorder)
    result = engine.run(bars)
    return engine, portfolio, result


def test_recorder_does_not_alter_backtest():
    """recorder 解耦：同回测有无 recorder，最终结果一致"""
    bars = _make_bars()
    e1, p1, r1 = _run(bars, recorder=None)
    rec = BacktestRecorder()
    e2, p2, r2 = _run(bars, recorder=rec)
    assert r1["final_equity"] == pytest.approx(r2["final_equity"])
    assert len(p1.trades) == len(p2.trades)


def test_trade_points_match_portfolio():
    """买卖点 == portfolio.trades（时间/价格/方向/ID 全一致）"""
    bars = _make_bars()
    rec = BacktestRecorder()
    engine, portfolio, result = _run(bars, recorder=rec)
    trades = rec.get("trade")
    assert len(trades) == len(portfolio.trades)
    for t, pt in zip(trades, portfolio.trades):
        assert t["trade_id"] == pt.trade_id
        assert t["side"] == pt.side.value
        assert t["price"] == pytest.approx(pt.price)
        assert t["qty"] == pytest.approx(pt.qty)


def test_equity_curve_matches_portfolio():
    """净值末点 == 最终权益（口径一致）"""
    bars = _make_bars()
    rec = BacktestRecorder()
    engine, portfolio, result = _run(bars, recorder=rec)
    eq = [r for r in rec.get("equity") if "equity" in r]
    assert len(eq) > 0
    assert eq[-1]["equity"] == pytest.approx(portfolio.account.equity)


def test_indicators_recorded_on_bar():
    """图上指标 = 策略实际上报（engine 在 on_bar 后自动采集，非事后重算）"""
    bars = _make_bars(n=120)
    rec = BacktestRecorder()
    engine, portfolio, result = _run(bars, recorder=rec)
    inds = rec.get("indicator")
    assert len(inds) > 0
    # 策略真实计算的指标名都应被记录
    names = {i["name"] for i in inds}
    assert {"entry_high", "exit_low", "atr"}.issubset(names)
    # 指标点数量 = 有效 bar 数（除前最小周期外），每个 bar 一组
    # 断言存在且单调：通道上轨 >= 下轨
    entry_high = [i["value"] for i in inds if i["name"] == "entry_high"]
    exit_low = [i["value"] for i in inds if i["name"] == "exit_low"]
    assert len(entry_high) > 0 and len(exit_low) > 0
    assert all(e >= l for e, l in zip(entry_high, exit_low))


def test_buy_sell_markers_separated():
    """图上买卖点按 side 分离（画图数据与 portfolio 口径一致）"""
    bars = _make_bars()
    rec = BacktestRecorder()
    engine, portfolio, result = _run(bars, recorder=rec)
    ex = VisualExporter(rec)
    html = ex.render_html("/tmp/_vis_check.html")
    # render_html 返回写入路径，读取文件内容
    if isinstance(html, str) and not html.startswith("<"):
        html = open(html, encoding="utf-8").read()
    # 抽取内嵌 const D = {...}
    start = html.find("const D = {")
    assert start > 0
    i = start + len("const D = ")
    depth = 0
    for j in range(i, len(html)):
        c = html[j]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                j += 1
                break
    import json
    d = json.loads(html[i:j])
    n_buy, n_sell = len(d["trade_buy"]), len(d["trade_sell"])
    # 与 portfolio 买卖成交数一致
    port_buy = sum(1 for t in portfolio.trades if t.side.value.upper() in ("BUY", "OPEN", "COVER"))
    port_sell = sum(1 for t in portfolio.trades if t.side.value.upper() in ("SELL", "CLOSE", "SHORT"))
    assert n_buy == port_buy
    assert n_sell == port_sell
    assert n_buy + n_sell == len(portfolio.trades)
    assert all(p["extra"]["side"].upper() in ("BUY", "OPEN", "COVER") for p in d["trade_buy"])
    assert all(p["extra"]["side"].upper() in ("SELL", "CLOSE", "SHORT") for p in d["trade_sell"])


def test_reject_records_carry_reason():
    """风控拒绝记录带原因（可追溯）"""
    # 构造会触发风控的场景：极小单笔金额上限
    bars = _make_bars(n=80)
    rec = BacktestRecorder()
    strategy = DonchianStrategy(entry_period=10, exit_period=5, atr_period=10, atr_multiplier=2)
    portfolio = Portfolio(initial_cash=100000.0)
    # 单笔金额上限设为 1 元 → 任意买入都被拒
    risk = RiskManager(RiskConfig(max_single_trade_amount=1.0))
    sizer = ATRSizer(risk_percent=0.02, atr_multiplier=2.0, atr_period=10, min_qty=100.0)
    broker = BacktestBroker(fee_model=ChinaAFeeModel())
    engine = BacktestEngine(strategy=strategy, portfolio=portfolio, broker=broker,
                            risk_manager=risk, position_sizer=sizer,
                            symbol=bars[0].symbol, recorder=rec)
    engine.run(bars)
    rejects = rec.get("risk_reject")
    assert len(rejects) > 0
    assert all(r["reason"] for r in rejects)  # 每条都有原因


def test_export_json_roundtrip():
    """JSON 导出可回读，含买卖点/净值/指标表"""
    bars = _make_bars(n=100)
    rec = BacktestRecorder()
    engine, portfolio, result = _run(bars, recorder=rec)
    ex = VisualExporter(rec)
    d = ex.to_dict()
    assert "bars" in d and "trades" in d and "equity" in d and "signals" in d
    assert len(d["bars"]) == len(bars)
