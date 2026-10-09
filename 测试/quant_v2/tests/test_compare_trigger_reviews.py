"""
scripts/compare_trigger_reviews.py 测试：多标的横向对照 + 随机基准列 + 样本量告警。
"""
import sys, os, json, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.compare_trigger_reviews import analyze_symbol, render_md, TNAME


def _mk_review(path, symbol, n=12, hit=6, state="趋势"):
    evs = []
    for i in range(n):
        evs.append({
            "symbol": symbol, "datetime": f"2024-0{i % 9 + 1}-0{i % 26 + 1}",
            "index": 200 + i, "trigger_type": "bottom_enter",
            "price_at_signal": 50.0 + i, "bottom_score": 6, "top_score": 2,
            "level": "3", "strength": "0.6", "forward_return_5": 0.01,
            "forward_return_10": 0.02, "forward_return_20": 0.03,
            "market_state": state, "mode": "hit" if i < hit else "过早",
            "mode_note": "", "std_hit": i < hit, "std_hit_note": "",
            "atr": 0.5, "hit_std": "k=2.0×ATR/20根", "source": "真实行情 " + symbol,
        })
    os.makedirs(os.path.dirname(path), exist_ok=True)
    json.dump(evs, open(path, "w", encoding="utf-8"))


def test_analyze_basic():
    """analyze_symbol：读取 review json，算出总体/方向命中率 + 随机基准"""
    with tempfile.TemporaryDirectory() as d:
        jp = os.path.join(d, "review_600519.json")
        _mk_review(jp, "600519")
        # analyze 会再去 load_bars(600519) 拉真实行情，用合成兜底也能跑
        try:
            r = analyze_symbol("600519", out_root=d)
        except FileNotFoundError:
            return  # 无行情源时跳过，不在 CI 崩
        assert r["n"] == 12
        assert r["n_hit"] == 6
        assert 0.0 <= r["rate"] <= 1.0
        assert "long" in r and "short" in r
        assert r["rate"] == 0.5


def test_analyze_excludes_top_no_pos():
    """top_no_pos 不进方向命中统计，但计入总体"""
    import scripts.compare_trigger_reviews as ctr

    def _synth(symbol):
        from datetime import datetime, timedelta
        from data.bar import Bar
        base = datetime(2024, 1, 1)
        bars = [Bar(symbol, base + timedelta(days=k), 1.0, 1.01, 0.99, 1.0, 1e6)
                for k in range(300)]
        return bars, f"合成行情 {symbol}"

    ctr.load_bars = _synth  # 替换真实行情为合成，隔离网络
    with tempfile.TemporaryDirectory() as d:
        jp = os.path.join(d, "review_512880.json")
        evs = [
            {"symbol": "512880", "datetime": "2024-01-01", "index": 50,
             "trigger_type": "bottom_enter", "price_at_signal": 1.0,
             "bottom_score": 6, "top_score": 2, "level": "3", "strength": "0.5",
             "std_hit": True, "market_state": "趋势", "mode": "hit",
             "mode_note": "", "std_hit_note": "", "atr": 0.1,
             "hit_std": "", "source": "合成"},
            {"symbol": "512880", "datetime": "2024-01-02", "index": 60,
             "trigger_type": "top_no_pos", "price_at_signal": 1.02,
             "bottom_score": 2, "top_score": 7, "level": "3", "strength": "0.5",
             "std_hit": True, "market_state": "趋势", "mode": "hit",
             "mode_note": "", "std_hit_note": "", "atr": 0.1,
             "hit_std": "", "source": "合成"},
        ]
        json.dump(evs, open(jp, "w", encoding="utf-8"))
        r = analyze_symbol("512880", out_root=d)
        assert r["n"] == 2        # 总体含 top_no_pos
        assert r["long"]["n"] == 1  # 方向只含 bottom_enter


def test_render_md_has_columns():
    """render_md：输出含随机基准列与样本量告警行"""
    reps = [{"symbol": "A", "source": "s", "n": 12, "n_hit": 6, "rate": 0.5,
             "long": {"n": 6, "hit": 3, "rate": 0.5, "base": 0.4, "edge": 0.1},
             "short": None, "atr": 0.5,
             "states": [{"state": "趋势", "n": 20, "hit": 10, "rate": 0.5, "enough": True},
                        {"state": "区间", "n": 3, "hit": 1, "rate": 0.33, "enough": False}],
             "state_avg": 0.5}]
    md = render_md(reps)
    assert "随机基准" in md
    assert "样本<10" in md
    assert "显著优于基准" in md or "无优势" in md or "劣于基准" in md
