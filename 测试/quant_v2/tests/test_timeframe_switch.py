#!/usr/bin/env python3
"""timeframe_switch.py（周线框架验证）测试
覆盖：周线聚合 OHLCV 正确性、ISO 周分组、双跑对照字段完整性、
标的<10 时净超额汇总只给均值+区间（不报 X/N）、周线/日线可产出净超额。
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
from datetime import datetime, timedelta
from data.bar import Bar
from scripts.timeframe_switch import aggregate_weekly, _net_excess_stat


def _mk_daily(n_days=80, start=None):
    """构造 n_days 根日线（连续自然日，覆盖多个 ISO 周）"""
    start = start or datetime(2023, 4, 3)  # 周一
    bars = []
    prev = 100.0
    for i in range(n_days):
        dt = start + timedelta(days=i)
        o = prev
        c = o * (1 + np.sin(i / 7) * 0.02)
        h = max(o, c) * 1.005
        lo = min(o, c) * 0.995
        bars.append(Bar("SYN", dt, o, h, lo, c, volume=1000 + i))
        prev = c
    return bars


def test_weekly_group_count():
    """80 个连续自然日应聚合成 ≥10 个 ISO 周（80 天 ≈ 11.4 周）"""
    years = aggregate_weekly(_mk_daily(80))
    assert len(years) >= 10, f"80 天应聚合出 ≥10 周，实际 {len(years)}"
    assert len(years) <= 12, f"80 天聚合周数应在 11 左右，实际 {len(years)}"


def test_weekly_ohlc_aggregation():
    """周 K 的 O/H/L/C 聚合：open=周内首日 open，high=max，low=min，close=周内末日 close"""
    bars = _mk_daily(1)          # 只含 1 天 => 1 周
    wk = aggregate_weekly(bars)
    assert len(wk) == 1
    assert wk[0].open == bars[0].open
    assert wk[0].high == bars[0].high
    assert wk[0].low == bars[0].low
    assert wk[0].close == bars[0].close


def test_weekly_ohlc_high_low():
    """多日周：high 为周内 max、low 为周内 min（人为构造日内高低跨越）"""
    bars = _mk_daily(4)         # 周一~周四，同属 1 个 ISO 周
    # 人为把某日 high 抬到绝对最高、某日 low 压到绝对最低
    bars[1] = Bar(bars[1].symbol, bars[1].datetime, bars[1].open,
                  bars[1].open * 1.02, bars[1].low, bars[1].close,
                  volume=bars[1].volume)
    bars[2] = Bar(bars[2].symbol, bars[2].datetime, bars[2].open,
                  bars[2].high, bars[2].open * 0.98, bars[2].close,
                  volume=bars[2].volume)
    wk = aggregate_weekly(bars)
    assert len(wk) == 1
    assert wk[0].high == max(b.high for b in bars)
    assert wk[0].low == min(b.low for b in bars)
    assert wk[0].open == bars[0].open
    assert wk[0].close == bars[-1].close


def test_weekly_datetime_is_last_trading_day():
    """周 K 的 datetime 取周内最后交易日"""
    bars = _mk_daily(4)
    wk = aggregate_weekly(bars)
    assert wk[0].datetime == bars[-1].datetime


def test_weekly_volume_sum():
    """周成交量 = 周内日成交量之和"""
    bars = _mk_daily(4)
    wk = aggregate_weekly(bars)
    assert abs(wk[0].volume - sum(b.volume for b in bars)) < 1e-6


def test_month_boundary_split():
    """跨月/跨 ISO 周的相邻自然日要分到不同周（周日->下周一不同 ISO 周）"""
    # 2023-04-03 是周一；加 6 天到周日(4-9)，再加 1 天到周一(4-10) 属下一 ISO 周
    bars = _mk_daily(8, start=datetime(2023, 4, 3))   # 4/3~4/10
    wk = aggregate_weekly(bars)
    assert len(wk) == 2, f"4/3~4/10 应聚合成 2 个 ISO 周，实际 {len(wk)}"
    assert wk[0].close == bars[6].close          # 第 1 周末日 = 周日 4/9
    assert wk[1].open == bars[7].open            # 第 2 周首日 = 周一 4/10


def test_net_excess_stat_under_10():
    """标的<10：净超额汇总只给 均值+区间（含 n），不含任何 X/N 计数"""
    stat = _net_excess_stat([0.01, -0.03, 0.02, -0.01])
    assert stat["n"] == 4
    assert abs(stat["mean_pp"] - (-0.01 / 4 * 100)) < 1e-9
    assert stat["lo_pp"] <= stat["hi_pp"]
    assert "n" in stat and "mean_pp" in stat and "lo_pp" in stat and "hi_pp" in stat
    # 不含计数字段
    assert "win_count" not in stat and "wins" not in stat


def test_net_excess_stat_empty():
    assert _net_excess_stat([]) is None


def test_net_excess_stat_single():
    st = _net_excess_stat([0.05])
    assert st["n"] == 1
    assert abs(st["mean_pp"] - 5.0) < 1e-9


def test_timeframe_switch_runs_syn():
    """SYN 冒烟：周线/日线双跑各产出净超额数值（不抛异常）"""
    from scripts.timeframe_switch import timeframe_switch
    import io, contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        timeframe_switch(["SYN_TS"], mode="momentum", lookback=10)
    out = buf.getvalue()
    assert "日线 vs固定低仓位" in out
    assert "周线 vs固定低仓位" in out


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))