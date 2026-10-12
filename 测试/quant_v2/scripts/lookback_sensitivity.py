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
    python3 scripts/lookback_sensitivity.py --score-hist 300750 512880 588000
        # 输出各标的 bottom_enter 评分直方图，诊断 min_score 能否救稀疏
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


def _run_engine(symbol, lookback, min_score=None):
    """跑一次引擎，返回 (bars, closes, events) —— run_one 与 score_hist 共用，避免重复拉行情"""
    min_score = MIN_SCORE if min_score is None else min_score
    bars, source = _bars_for(symbol)
    closes = [float(b.close) for b in bars]

    from strategy.timing_strategy import TimingStrategy
    from engine.backtest_engine import BacktestEngine
    from portfolio.portfolio import Portfolio
    from risk.risk_manager import RiskManager, RiskConfig
    from risk.position_sizer import PercentSizer

    strat = TimingStrategy(min_score=min_score, direction_mode="both", lookback=lookback)
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
    return bars, closes, events


def run_one(symbol, lookback):
    """对单个 标的×lookback 跑引擎，返回 (n_bottom, n_top, n_total, hit, hit_rate, note)"""
    bars, closes, events = _run_engine(symbol, lookback)
    atr = calc_atr(closes)

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


def score_hist(symbol, lookback=LOOKBACKS[0], min_score=MIN_SCORE, ms_scan=(2, 3, 4)):
    """对单标的输出 bottom_enter 的 bottom_score 分布直方图（诊断评分卡区分度）。

    同时输出 min_score 敏感性（ms_scan：各 min_score 下的信号数），回答"降阈值能不能救"：
    - 若 min_score 3→2 信号翻倍 → 是阈值卡点，可先降；
    - 若 3→2 仍不翻倍（或 even 更高分档才有量）→ 是评分卡结构问题。
    """
    bars, closes, events = _run_engine(symbol, lookback, min_score=min_score)
    scores = [round(e.get("bottom_score", 0.0), 1)
              for e in events if e["trigger_type"] == "bottom_enter"]
    from collections import Counter
    hist = dict(sorted(Counter(scores).items()))
    # min_score 敏感性：各阈值下信号数（各跑一次引擎）
    ms = {m: _count_bottom(symbol, lookback, m) for m in ms_scan}
    return {"symbol": symbol, "lookback": lookback, "min_score": min_score,
            "n_bottom": len(scores), "hist": hist,
            "score_range": (min(scores), max(scores)) if scores else (None, None),
            "ms_scan": ms}


def _count_bottom(symbol, lookback, min_score):
    _, _, events = _run_engine(symbol, lookback, min_score=min_score)
    return sum(1 for e in events if e["trigger_type"] == "bottom_enter")


def classify(rows):
    """根据各 lookback 的 bottom_enter 信号数判定稀疏主因（纯函数，可测）

    两个条件任一即为 lookback 主因（且 30 信号量 >= MIN 保底，防 4 之类小样本被误判）：
      A) 30 >= 2×90                —— 强倍数递减
      B) 30 > 45 > 60 >= 90        —— 单调递减 + 最低信号量
      否则 30->4/90->3 这类噪声抖动不会被当成递减。
    """
    n_by_lb = [r["n_bottom"] for r in rows]
    all_sparse = all(r["n_bottom"] < HIT_MIN_SAMPLES for r in rows)
    min_ok = n_by_lb[0] >= HIT_MIN_SAMPLES
    strong_decrease = min_ok and (
        n_by_lb[0] >= 2 * n_by_lb[-1] or                     # A) 强倍数递减
        (n_by_lb[0] > n_by_lb[1] > n_by_lb[2] >= n_by_lb[3])  # B) 单调递减
    )
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


def render_score_hist(reports):
    """渲染各标的 bottom_enter 评分直方图 + min_score 敏感性（--score-hist）。"""
    L = []
    L.append("## bottom_enter 评分直方图（min_score 敏感性诊断）")
    L.append("")
    L.append(f"> 统一 min_score={MIN_SCORE}，冻结命中标准 k={HIT_K}×ATR/{HIT_HORIZON}根。")
    L.append("> 判定：评分集中在 0–2 → 降 min_score 无用；集中在 3–4 → 降一档可能翻倍；")
    L.append("> 双峰（大量 1–2 + 少量 5–6）→ 评分卡区分不出中段，是结构问题非阈值。")
    L.append("")
    for r in reports:
        L.append(f"### {r['symbol']}  (lookback={r['lookback']}, bottom_enter={r['n_bottom']})")
        L.append("")
        if not r["hist"]:
            L.append("无 bottom_enter 信号。")
        else:
            lo, hi = r["score_range"]
            L.append(f"评分区间 [{lo}, {hi}]")
            L.append("")
            L.append("| bottom_score | 信号数 | 迷你直方图 |")
            L.append("|-------------|--------|-----------|")
            for sc, cnt in r["hist"].items():
                bar = "█" * max(1, int(round(cnt / max(1, r["n_bottom"]) * 40)))
                L.append(f"| {sc} | {cnt} | {bar} |")
        # min_score 敏感性
        L.append("")
        ms = r.get("ms_scan") or {}
        if ms:
            L.append("min_score 敏感性（各阈值 bottom_enter 数）：")
            L.append("")
            L.append("| min_score | bottom_enter |")
            L.append("|-----------|-------------|")
            for m in sorted(ms):
                L.append(f"| {m} | {ms[m]} |")
            L.append("")
            base = r.get("min_score")
            if base in ms and base in ms and base - 1 in ms:
                n_hi, n_lo = ms[base], ms[base - 1]
                ratio = (n_lo / n_hi) if n_hi else 0
                if n_hi < 10:
                    verdict = (f"{base}→{base-1} 信号 {n_hi}→{n_lo}"
                               + ("（翻倍，阈值卡点，可降）" if ratio >= 2
                                  else "（仍不足，评分卡整体太弱，非单纯阈值）"))
                    L.append(f"**{verdict}**")
                    L.append("")
    L.append("### 判定口径")
    L.append("")
    L.append("- **min_score 3→2 翻倍**：阈值是卡点，可先降 min_score 试扩信号。")
    L.append("- **3→2 不翻倍**：评分卡在这些标的分不出中段，调阈值无益，需改评分卡结构。")
    L.append("- 评分普遍压死在最低触发档（如全 3）→ 信号全靠阈值边缘擦过，无排序力，")
    L.append("  即便命中率看着可以，也无法支撑打分驱动仓位。")
    return "\n".join(L)


if __name__ == "__main__":
    out = None
    score_hist_mode = "--score-hist" in sys.argv
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
    if score_hist_mode:
        reports = [score_hist(s) for s in args]
        md = render_score_hist(reports)
    else:
        reports = [analyze(s) for s in args]
        md = render_md(reports)
    if out:
        open(out, "w", encoding="utf-8").write(md)
        print(f"已存: {out}")
    else:
        print(md)
