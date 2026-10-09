"""
scripts/review_triggers.py 失败模式预判规则引擎测试

覆盖 predict_mode 的 5 类失败模式 + hit 判定，确保人工验收工具的自动预判可靠。
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.review_triggers import (predict_mode, HIT, EARLY, LATE, FAKE,
                                     TREND_SEG, market_state)


def _ev(i=20, tt="bottom_enter", **fwd):
    ev = {"index": i, "trigger_type": tt,
          "forward_return_5": fwd.get("f5", 0.0),
          "forward_return_10": fwd.get("f10", 0.0),
          "forward_return_20": fwd.get("f20", 0.0)}
    return ev


def _closes(n=60, base=50.0):
    return [base] * n


def test_hit_bottom():
    closes = [50.0] * 20 + [49.0] + [52.0, 53.0, 54.0]
    ev = _ev(i=20, tt="bottom_enter", f5=0.04, f10=0.07, f20=0.10)
    assert predict_mode(ev, closes)[0] == HIT


def test_early_bottom():
    ev = _ev(tt="bottom_enter", f5=-0.03, f10=0.0, f20=0.05)
    assert predict_mode(ev, _closes())[0] == EARLY


def test_late_bottom():
    closes = [50.0] * 10 + [49.0] + [50.0, 51.0, 52.0, 53.0, 54.0, 55.0, 56.0, 57.0]
    ev = _ev(i=18, tt="bottom_enter", f5=0.03, f10=0.05, f20=0.08)
    assert predict_mode(ev, closes)[0] == LATE


def test_fake_bottom():
    ev = _ev(tt="bottom_enter", f5=0.03, f10=-0.01, f20=-0.04)
    assert predict_mode(ev, _closes())[0] == FAKE


def test_trend_seg_bottom():
    ev = _ev(tt="bottom_enter", f5=-0.04, f10=-0.06, f20=-0.09)
    assert predict_mode(ev, _closes())[0] == TREND_SEG


def test_sell_orientation():
    ev = _ev(tt="top_exit", f5=-0.04, f10=-0.06, f20=-0.09)
    assert predict_mode(ev, _closes())[0] == HIT


def test_top_no_pos_fake():
    ev = _ev(tt="top_no_pos", f5=-0.03, f10=0.0, f20=0.05)
    assert predict_mode(ev, _closes())[0] == FAKE


def test_market_state_basic():
    closes = [50 * (1 + 0.002 * i) for i in range(60)]
    assert market_state(closes, 30) in ("趋势", "高波动")
    flat = [50.0] * 60
    assert market_state(flat, 30) == "区间"
