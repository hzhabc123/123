# -*- coding: utf-8 -*-
"""
多标的触发点命中对照表（含随机入场基准）。

用法:
    python3 scripts/compare_trigger_reviews.py 600519 300750 512880 588000 [--out report.md]

对每个标的：
  - 读取 outputs/review_{symbol}.json（含 std_hit / atr / market_state / trigger_type）
  - 重新载入同窗口行情计算随机入场基准（同标的"随机入场 + 持有 horizon 根"命中率）
  - 输出横向对照：总体命中率、做多/做空命中率 vs 随机基准、按状态分组
  - 市场状态样本 < HIT_MIN_SAMPLES 标记"仅供参考"，不纳入横向汇总

设计要点（对齐多标的可比性）：
  - 命中判定一律用冻结标准 k×ATR/horizon，与 review_triggers.py 同参数
  - 绝对命中率 vs 随机基准两列并排，用于剥离"高波动标的做多胜率高"的波动率红利
  - 只有某标的策略命中率显著高于同标的随机基准，才判定该方向有效
"""
import sys, os, json, random
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.review_triggers import calc_atr, random_baseline, load_bars, HIT_MIN_SAMPLES

TNAME = {"bottom_enter": "做多", "top_exit": "做空", "top_no_pos": "顶空仓"}


def analyze_symbol(symbol, out_root="outputs"):
    jp = os.path.join(out_root, f"review_{symbol}.json")
    if not os.path.isfile(jp):
        raise FileNotFoundError(f"缺少 {jp}，请先跑 review_triggers.py {symbol}")
    events = json.load(open(jp, encoding="utf-8"))
    bars, source = load_bars(symbol)
    closes = [float(b.close) for b in bars]
    atr = calc_atr(closes)

    n = len(events)
    n_hit = sum(1 for e in events if e.get("std_hit"))
    # 方向拆分（不含 top_no_pos）
    dir_of = lambda e: 1 if e["trigger_type"] == "bottom_enter" else (-1 if e["trigger_type"] == "top_exit" else None)

    def stat(sub):
        sub = [e for e in sub]
        if not sub:
            return None
        h = sum(1 for e in sub if e.get("std_hit"))
        d = dir_of(sub[0])
        base = None
        if d is not None and atr > 0:
            n_start = max(200, len(sub) * 10)
            base = random_baseline(closes, n_start, d, atr, seed=symbol)
        return {"n": len(sub), "hit": h, "rate": h / len(sub), "base": base,
                "edge": (h / len(sub) - base) if base is not None else None}

    long_s, short_s = stat([e for e in events if dir_of(e) == 1]), \
                      stat([e for e in events if dir_of(e) == -1])

    # 按状态分组
    by_state = {}
    for e in events:
        by_state.setdefault(e.get("market_state", "?"), []).append(e)
    states = []
    summable_rates = []
    for st, rs in by_state.items():
        h = sum(1 for e in rs if e.get("std_hit"))
        smp = len(rs) >= HIT_MIN_SAMPLES
        states.append({"state": st, "n": len(rs), "hit": h,
                       "rate": h / len(rs), "enough": smp})
        if smp:
            summable_rates.append(h / len(rs))
    state_avg = sum(summable_rates) / len(summable_rates) if summable_rates else None

    return {"symbol": symbol, "source": source, "n": n, "n_hit": n_hit,
            "rate": n_hit / n if n else 0.0,
            "long": long_s, "short": short_s, "states": states,
            "state_avg": state_avg, "atr": round(atr, 4)}


def fmt_rate(x, nd=1):
    return f"{x*100:.{nd}f}%" if x is not None else "-"


def render_md(reports):
    L = []
    L.append("## 多标的触发命中对照（冻结标准 k=2.0×ATR/20根）")
    L.append("")
    L.append("| 标的 | 方向 | n | 策略命中 | 随机基准 | 优势(pp) | 判定 |")
    L.append("|------|------|---|---------|---------|---------|------|")
    for r in reports:
        L.append(f"| **{r['symbol']}** | 全部 | {r['n']} | {r['rate']*100:.1f}% | - | - | - |")
        for dname, s in (("做多", r["long"]), ("做空", r["short"])):
            if not s:
                continue
            edge = s["edge"]
            if edge is None:
                verdict = "-"
            elif edge >= 0.10:
                verdict = "✅ 显著优于基准"
            elif edge >= 0:
                verdict = "🟡 无优势"
            else:
                verdict = "🔴 劣于基准"
            L.append(f"| | {dname} | {s['n']} | {s['rate']*100:.0f}% | "
                     f"{s['base']*100:.0f}% | {edge*100:+.0f} | {verdict} |")
    L.append("")
    L.append("> 优势 = 策略命中率 − 同标的随机入场基准命中率，≥10pp 视为显著有效。")
    L.append("> 正值代表策略在该方向确实优于\"随机买卖\"，负值则可能只是高波动红利。")
    L.append("")
    L.append("### 按市场状态分组")
    L.append("")
    L.append("| 标的 | 状态 | n | 命中 | 命中率 | 备注 |")
    L.append("|------|------|---|------|--------|------|")
    for r in reports:
        for s in r["states"]:
            note = "" if s["enough"] else "⚠️样本<10，仅供参考"
            L.append(f"| {r['symbol']} | {s['state']} | {s['n']} | {s['hit']} | "
                     f"{s['rate']*100:.0f}% | {note} |")
    L.append("")
    L.append("### 结论口径")
    L.append("")
    L.append("- 各标的用同一把冻结尺子（k×ATR/horizon），跨标的命中率可比。")
    L.append("- 只有样本 ≥10 的市场状态进入简单均值；样本不足状态仅作参考，不进入横向汇总。")
    L.append("- 人工 `--interactive` 复核完成前，以下命中率仍是**规则引擎/机械尺子**结果，"
             "不代表策略最终质量——需先比对该尺度与人工判定，差异 >30% 则先调判定标准。")
    return "\n".join(L)


if __name__ == "__main__":
    out = None
    rest = []
    i = 1  # 跳过脚本名
    while i < len(sys.argv):
        a = sys.argv[i]
        if a == "--out" and i + 1 < len(sys.argv):
            out = sys.argv[i + 1]; i += 2; continue
        if not a.startswith("--"):
            rest.append(a)
        i += 1
    args = rest
    if not args:
        print(__doc__); sys.exit(0)
    reports = [analyze_symbol(s) for s in args]
    md = render_md(reports)
    if out:
        open(out, "w", encoding="utf-8").write(md)
        print(f"已存: {out}")
    else:
        print(md)
