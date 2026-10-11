# -*- coding: utf-8 -*-
"""
lookback 敏感性测试：判断"信号过稀"是参数问题（lookback）还是阈值/评分问题。

背景：科创50 两年仅 2 个 bottom_enter，可能不是"样本不够"，而是该参数组合
对多数标的基本不产生信号。扩样本前先定参数，否则扩了也白扩。

做法：同一批标的，把 lookback 在 [30,45,60,90] 各跑一遍，统计
bottom_enter / top_exit / 全部信号数 + 冻结命中率（同一把尺子）。

判定：
  - 若 30 → 信号多、90 → 信号少（递减明显）→ lookback 是信号稀疏主因，
    扩样本前先定 lookback（如取信号量适中的值）
  - 若三种 lookback 都 <5 个信号 → 是阈值/评分太严，调 min_score 或评分卡，
    不是 lookback 的事

用法:
    python3 scripts/lookback_sensitivity.py 600519 300750 512880 588000
    python3 scripts/lookback_sensitivity.py 600519 --out report.md
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.review_triggers import load_bars, calc_atr, std_hit
from scripts.review_triggers import HIT_K, HIT_HORIZON, HIT_MIN_SAMPLES

LOOKBACKS = [30, 45, 60, 90]
MIN_SCORE = 3

# 每个标的行情只拉一次缓存（多 lookback 共享），避免重复网络请求
_load_cache = {}


def _bars_for(symbol):
    if symbol not in _load_cache:
        _load_cache[symbol] = load_bars(symbol)
    return _load_cache[symbol]


def run_one(symbol, lookback):
    """对单个 标的×lookback 跑引擎，返回 (n_bottom, n_top, n_total, hit, hit_rate, note)"""
    bars, source = _bars_for(symbol)
    closes = [float(b.close) for b in bars]
    atr = calc_atr(closes)

    from strategy.timing_strategy import TimingStrategy
    from engine.backtest_engine import BacktestEngine
    from portfolio.portfolio import Portfolio
    from risk.risk_manager import RiskManager, RiskConfig
    from risk.position_sizer import PercentSizer

    strat = TimingStrategy(min_score=MIN_SCORE, direction_mode="both", lookback=lookback)
    portfolio = Portfolio(initial_cash=500_000.0)
    rc = RiskConfig()
    rc.max_single_trade_amount = 1_000_000.0
    rc.max_single_trade_ratio = 0.4
    rc.max_position_ratio = 0.8
    engine = BacktestEngine(strategy=strat, portfolio=portfolio,
                            risk_manager=RiskManager(rc),
                            position_sizer=PercentSizer(percent=0.3, min_amount=1000.0),
                            symbol=strat.name, lookback=500)
    engine.run(bars)
    events = strat.get_trigger_events(annotate=True)

    n_bottom = sum(1 for e in events if e["trigger_type"] == "bottom_enter")
    n_top = sum(1 for e in events if e["trigger_type"] == "top_exit")
    n_total = len(events)
    # 冻结命中（方向命中只看 bottom_enter/top_exit）
    dir_hits = [e for e in events if e["trigger_type"] in ("bottom_enter", "top_exit")]
    n_hit = sum(1 for e in dir_hits if std_hit(e, closes, atr)[0]) if dir_hits else 0
    rate = n_hit / len(dir_hits) if dir_hits else 0.0
    sparse = (n_bottom < HIT_MIN_SAMPLES)
    return {"lookback": lookback, "n_bottom": n_bottom, "n_top": n_top,
            "n_total": n_total, "n_hit": n_hit, "n_dir": len(dir_hits),
            "rate": rate, "sparse": sparse, "atr": round(atr, 4)}


def classify(rows):
    """根据各 lookback 的 bottom_enter 信号数判定稀疏主因（纯函数，可测）"""
    n_by_lb = [r["n_bottom"] for r in rows]
    all_sparse = all(r["n_bottom"] < HIT_MIN_SAMPLES for r in rows)
    # lookback 主因须真实递减：30 信号量 >= MIN 且显著多于 90（>=2倍），
    # 否则 30->4/90->3 这类噪声抖动会被误判成递减
    strong_decrease = (n_by_lb[0] >= HIT_MIN_SAMPLES and
                       n_by_lb[0] >= 2 * n_by_lb[-1])
    if strong_decrease:
        return ("信号稀疏主要来自 lookback：lookback 越大信号越稀（30→多、90→少），"
                "扩样本前先定 lookback（如取信号量适中且命中率不塌的值）")
    if all_sparse:
        return ("该标的所有 lookback 均 <10 信号 → 是阈值/评分太严（min_score 或评分卡），"
                "不是 lookback 的事，扩样本前先调阈值/评分")
    return "lookback 相关性弱；信号量主要由阈值/市场结构决定，先做人工复核校准"


def analyze(symbol, lookbacks=LOOKBACKS):
    rows = [run_one(symbol, lb) for lb in lookbacks]
    return {"symbol": symbol, "rows": rows, "diag": classify(rows)}


def render_md(reports):
    L = []
    L.append("## lookback 敏感性测试（信号稀疏主因诊断）")
    L.append("")
    L.append(f"> 统一 min_score={MIN_SCORE}，冻结命中标准 k={HIT_K}×ATR/{HIT_HORIZON}根，"
             f"样本<{HIT_MIN_SAMPLES} 标稀疏。")
    L.append("")
    for r in reports:
        L.append(f"### {r['symbol']}")
        L.append("")
        L.append("| lookback | bottom_enter | top_exit | 全部 | 命中 | 方向命中率 | 稀疏 |")
        L.append("|----------|-------------|----------|------|------|-----------|------|")
        for row in r["rows"]:
            L.append(f"| {row['lookback']} | {row['n_bottom']} | {row['n_top']} | "
                     f"{row['n_total']} | {row['n_hit']}/{row['n_dir']} | "
                     f"{row['rate']*100:.0f}% | {'⚠️' if row['sparse'] else 'ok'} |")
        L.append("")
        L.append(f"**判定**：{r['diag']}")
        L.append("")
    L.append("### 汇总判定口径")
    L.append("")
    L.append("- **lookback 递减明显（30多→90少）→ lookback 是稀疏主因，扩样本前先定参数。")
    L.append("- **三种 lookback 都稀 → 阈值/评分问题，调 min_score 或评分卡，别靠扩样本。")
    L.append("- 稀疏是**诊断结果**不是样本量问题：某标的几乎不产生信号时，扩样本救不了，")
    L.append("  先解决\"为什么没信号\"再谈加标的。")
    return "\n".join(L)


if __name__ == "__main__":
    out = None
    args = []
    i = 1
    while i < len(sys.argv):
        a = sys.argv[i]
        if a == "--out" and i + 1 < len(sys.argv):
            out = sys.argv[i + 1]; i += 2; continue
        if not a.startswith("--"):
            args.append(a)
        i += 1
    if not args:
        print(__doc__); sys.exit(0)
    reports = [analyze(s) for s in args]
    md = render_md(reports)
    if out:
        open(out, "w", encoding="utf-8").write(md)
        print(f"已存: {out}")
    else:
        print(md)
