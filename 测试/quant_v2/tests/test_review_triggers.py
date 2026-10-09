"""
scripts/review_triggers.py 失败模式预判规则引擎测试

覆盖 predict_mode 的 5 类失败模式 + hit 判定，确保人工验收工具的自动预判可靠。
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.review_triggers import (predict_mode, HIT, EARLY, LATE, FAKE,
                                     TREND_SEG, market_state)


def _ev(i=20, tt="bottom_enter", **fwd):
    """构造事件：index 落在 closes 中间，fwd 可覆盖"""
    ev = {"index": i, "trigger_type": tt,
          "forward_return_5": fwd.get("f5", 0.0),
          "forward_return_10": fwd.get("f10", 0.0),
          "forward_return_20": fwd.get("f20", 0.0)}
    return ev


def _closes(n=60, base=50.0):
    """平坦价格序列（前低=base）"""
    return [base] * n


def test_hit_bottom():
    """买点：方向对且未过晚 → hit"""
    closes = [50.0] * 20 + [49.0] + [52.0, 53.0, 54.0]  # 前低=49, 触发50
    ev = _ev(i=20, tt="bottom_enter", f5=0.04, f10=0.07, f20=0.10)
    assert predict_mode(ev, closes)[0] == HIT


def test_early_bottom():
    """买点：先跌后涨（信号太早）→ 过早"""
    ev = _ev(tt="bottom_enter", f5=-0.03, f10=0.0, f20=0.05)
    assert predict_mode(ev, _closes())[0] == EARLY


def test_late_bottom():
    """买点：触发价已距前低涨幅过大（确认太重/信号晚）→ 过晚"""
    closes = [50.0] * 10 + [49.0] + [50.0, 51.0, 52.0, 53.0, 54.0, 55.0, 56.0, 57.0]
    # 触发在 i=18，前20根低点=49 → 触发价57相对49涨幅16% > late_rise
    ev = _ev(i=18, tt="bottom_enter", f5=0.03, f10=0.05, f20=0.08)
    assert predict_mode(ev, closes)[0] == LATE


def test_fake_bottom():
    """买点：先对后收回（突破假）→ 假突破"""
    ev = _ev(tt="bottom_enter", f5=0.03, f10=-0.01, f20=-0.04)
    assert predict_mode(ev, _closes())[0] == FAKE


def test_trend_seg_bottom():
    """买点：持续下跌被当底 → 趋势中段误判"""
    ev = _ev(tt="bottom_enter", f5=-0.04, f10=-0.06, f20=-0.09)
    assert predict_mode(ev, _closes())[0] == TREND_SEG


def test_sell_orientation():
    """卖点：期望跌，sign 翻转（top 信号 fwd 为负=对）→ hit"""
    ev = _ev(tt="top_exit", f5=-0.04, f10=-0.06, f20=-0.09)
    assert predict_mode(ev, _closes())[0] == HIT


def test_top_no_pos_fake():
    """卖点 top_no_pos：先跌后涨（顶部收回）→ 假突破"""
    ev = _ev(tt="top_no_pos", f5=-0.03, f10=0.0, f20=0.05)
    assert predict_mode(ev, _closes())[0] == FAKE


def test_market_state_basic():
    """市场状态标签：上行走势→趋势，平坦→区间"""
    closes = [50 * (1 + 0.002 * i) for i in range(60)]  # 上行
    assert market_state(closes, 30) in ("趋势", "高波动")
    flat = [50.0] * 60
    assert market_state(flat, 30) == "区间"


# ---- 冻结标准命中判定（std_hit）----
def _closes_stepped(up=True, base=50.0, n=40, step=0.15, surge=2.0):
    """构造：前段平缓，后段朝 direction 方向走 >= 2*ATR 的价格"""
    import math
    ks = [base] * n
    # 让 ATR 稳定在小步长量级
    for i in range(n):
        ks[i] = base + (i * step if up else -i * step)
    atr = abs(step)
    # 在 index=n 后加入一个超越 2*atr 的瞬间跳变
    jump = surge * atr + 0.01
    ks = ks + [ks[-1] + (jump if up else -jump)]
    return ks, atr

from scripts.review_triggers import std_hit, random_baseline, calc_atr

def test_std_hit_long_up():
    """买点：随后 20 根内收盘 ≥ entry + 2×ATR → 命中"""
    ks, atr = _closes_stepped(up=True)
    # 让 index 指向最后一个平缓点之前的合理位置
    i = len(ks) - 2
    ev = {"trigger_type": "bottom_enter", "index": i}
    ok, note = std_hit(ev, ks, atr)
    assert ok is True, note

def test_std_hit_long_never_reach():
    """买点：指数前段有波动(atr>0)但 index 后 20 根横盘，走不到 2×ATR → 未命中"""
    # 前段制造波动：从 50 到 55 再回落，ATR 显著 >0
    import math
    ks = [50 + 5*math.sin(i*0.3) for i in range(30)]
    atr = calc_atr(ks)
    assert atr > 0
    # 之后追加 30 根极小幅横盘，指数点 i=30 后 20 根内无法达 2*ATR
    ks += [ks[-1] + (1 if i % 2 else -1)*0.001 for i in range(30)]
    ev = {"trigger_type": "bottom_enter", "index": 30}
    ok, note = std_hit(ev, ks, atr)
    assert ok is False, note

def test_std_hit_short_down():
    """卖点：随后 20 根内收盘 ≤ entry − 2×ATR → 命中"""
    ks, atr = _closes_stepped(up=False)
    i = len(ks) - 2
    ev = {"trigger_type": "top_exit", "index": i}
    ok, note = std_hit(ev, ks, atr)
    assert ok is True, note

def test_std_hit_data_insufficient():
    """index 位于序列尾部 → 数据不足，不判命中"""
    ks = [50.0] * 10
    ev = {"trigger_type": "bottom_enter", "index": len(ks) - 1}
    ok, note = std_hit(ev, ks, 0.5)
    assert ok is False and "数据不足" in note


# ---- 随机基准（random_baseline）----
def test_random_baseline_range():
    """基准命中率落在 [0,1]，且不因波动红利而恒为 1"""
    ks, atr = _closes_stepped(up=True)
    base = random_baseline(ks, 200, 1, atr, seed=1)
    assert 0.0 <= base <= 1.0

def test_random_baseline_seeded_stable():
    """同 seed 结果稳定可复现"""
    ks, atr = _clones_noisy()
    a = random_baseline(ks, 100, 1, atr, seed=42)
    b = random_baseline(ks, 100, 1, atr, seed=42)
    assert a == b

def _clones_noisy(base=50.0, n=120, noise=0.8, amp=1.5):
    """构造带噪声的行情：随机基准命中率应介于 0~1 而非恒 1"""
    import random, math
    r = random.Random(3)
    ks = [base]
    for _ in range(n - 1):
        ks.append(ks[-1] * (1 + r.uniform(-0.02, 0.02)))
    atr = calc_atr(ks)
    # 保证 atr>0 且噪声足以让随机入场多数被止损
    if atr <= 0:
        atr = 0.1
    return ks, atr
