#!/usr/bin/env python3
"""
相关性矩阵 + 层次聚类分析（扩样本前的标的筛选）

用法：
    python3 scripts/correlation_matrix.py \
        --codes 510300,510500,512100,510050,159949,512800,512170,512480,512690,513050,510880,600519,300750,512880,588000 \
        --start 2019-01-01 --end 2024-12-31 \
        --adjust hfq \
        --baseline 600519,300750,512880,588000

输出：
    outputs/corr_matrix_full.csv      全样本相关矩阵
    outputs/corr_matrix_yearly.csv    按年分层（长格式）
    outputs/corr_clusters.md          聚类分组 + 与基准均值相关 + 建议名单
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# 确保从 scripts/ 运行时能 import utils/ 和 data/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Python 3.13 兼容补丁，必须在 import akshare 之前
from utils.compat import patch_imp_importer
patch_imp_importer()

from data.akshare_source import AkshareDataSource
import datetime as _dt


def _as_date(v, default):
    """把 'YYYY-MM-DD' 字符串或 date 转成 datetime.date（fetch_daily 需要 date 对象）"""
    if isinstance(v, str):
        return _dt.datetime.strptime(v, "%Y-%m-%d").date()
    return v


def parse_args():
    p = argparse.ArgumentParser(description="相关性矩阵 + 聚类分析")
    p.add_argument("--codes", required=True, help="逗号分隔的标的代码")
    p.add_argument("--baseline", default="600519,300750,512880,588000",
                   help="基准标的（固定保留，逗号分隔）")
    p.add_argument("--start", default="2019-01-01")
    p.add_argument("--end", default="2024-12-31")
    p.add_argument("--adjust", default="hfq", choices=["qfq", "hfq", ""])
    p.add_argument("--linkage", default="average",
                   choices=["average", "complete", "single"])
    p.add_argument("--min-clusters", type=int, default=4)
    p.add_argument("--max-clusters", type=int, default=8)
    p.add_argument("--output-dir", default="outputs")
    return p.parse_args()


def load_returns(codes, start, end, adjust):
    """加载 hfq 日简单收益，返回 (returns_df, failed_list)"""
    src = AkshareDataSource()
    close_series, failed = {}, []
    start_d = _as_date(start, None)
    end_d = _as_date(end, None)

    for code in codes:
        try:
            bars = src.fetch_daily(code, start_d, end_d, adjust=adjust)
            if not bars:
                failed.append((code, "empty bars"))
                continue
            s = pd.Series(
                [b.close for b in bars],
                index=pd.to_datetime([b.datetime for b in bars]),
                name=code,
            )
            s = s[~s.index.duplicated(keep="last")].sort_index()
            close_series[code] = s
            print(f"  {code}: {len(s)} bars  {s.index[0].date()} ~ {s.index[-1].date()}")
        except Exception as e:
            failed.append((code, str(e)))
            print(f"  {code}: FAILED - {e}")

    if len(close_series) < 2:
        raise RuntimeError("有效标的不足 2 个")

    close_df = pd.DataFrame(close_series).dropna()  # 取交集
    print(f"\n对齐后共同交易日：{len(close_df)} 天，有效标的：{len(close_df.columns)} 只")

    returns = close_df.pct_change(fill_method=None).dropna()
    return returns, failed


def yearly_corr(returns):
    """按年分层，返回长格式 df（year/code1/code2/corr）"""
    rows = []
    for year, group in returns.groupby(returns.index.year):
        if len(group) < 20:
            continue
        mat = group.corr()
        cols = list(mat.columns)
        for i, c1 in enumerate(cols):
            for c2 in cols[i + 1:]:
                rows.append({"year": int(year), "code1": c1,
                             "code2": c2, "corr": float(mat.loc[c1, c2])})
    return pd.DataFrame(rows)


def hierarchical_cluster(corr, linkage_method, min_k, max_k):
    """距离 = 1 - corr，平均连锁，silhouette 选簇数"""
    try:
        from scipy.cluster.hierarchy import linkage, fcluster
        from scipy.spatial.distance import squareform
    except ImportError:
        raise RuntimeError("需要 scipy：pip install scipy")

    codes = list(corr.columns)
    dist = 1 - corr.values
    np.fill_diagonal(dist, 0)
    dist = np.clip((dist + dist.T) / 2, 0, None)
    condensed = squareform(dist, checks=False)
    Z = linkage(condensed, method=linkage_method)

    try:
        from sklearn.metrics import silhouette_score
        use_sil = True
    except ImportError:
        use_sil = False

    scores, best_k, best_score = {}, None, -np.inf
    for k in range(min_k, min(max_k, len(codes) - 1) + 1):
        labels = fcluster(Z, k, criterion="maxclust")
        if len(set(labels)) < 2:
            continue
        score = (silhouette_score(dist, labels, metric="precomputed")
                 if use_sil else _fallback_score(dist, labels))
        scores[k] = score
        if score > best_score:
            best_score, best_k = score, k

    if best_k is None:
        best_k = min_k
    labels = fcluster(Z, best_k, criterion="maxclust")

    # 重新编号（大簇在前）
    uniq, counts = np.unique(labels, return_counts=True)
    order = uniq[np.argsort(-counts)]
    remap = {old: i + 1 for i, old in enumerate(order)}
    labels = [remap[l] for l in labels]

    return {c: int(l) for c, l in zip(codes, labels)}, best_k, scores


def _fallback_score(dist, labels):
    intra, inter = [], []
    for i in range(len(labels)):
        for j in range(i + 1, len(labels)):
            (intra if labels[i] == labels[j] else inter).append(dist[i, j])
    if not intra or not inter:
        return -np.inf
    return -np.mean(intra) / max(np.mean(inter), 1e-9)


def mean_corr_with_baseline(corr, baseline):
    base = [c for c in baseline if c in corr.columns]
    out = {}
    for code in corr.columns:
        if code in base:
            continue
        vals = [corr.loc[code, b] for b in base if b != code]
        out[code] = float(np.mean(vals)) if vals else float("nan")
    return out


def df_to_md(df, fmt=".3f"):
    cols = list(df.columns)
    header = "| | " + " | ".join(str(c) for c in cols) + " |"
    sep = "|" + "|".join(["---"] * (len(cols) + 1)) + "|"
    rows = []
    for idx, row in df.iterrows():
        vals = [str(idx)] + [f"{row[c]:{fmt}}" if isinstance(row[c], float) else str(row[c])
                             for c in cols]
        rows.append("| " + " | ".join(vals) + " |")
    return "\n".join([header, sep] + rows)


def build_report(args, corr, yearly_df, cluster_map, best_k, scores,
                 mean_corr, baseline, failed, n_days):
    lines = ["# 相关性矩阵 + 聚类分析\n"]
    lines += [f"- 期间：{args.start} ~ {args.end}",
              f"- 复权：{args.adjust}",
              f"- 有效标的：{len(corr.columns)} 只",
              f"- 共同交易日：{n_days} 天",
              f"- 聚类方式：{args.linkage} linkage，距离 = 1 − 相关系数",
              f"- 最优簇数 G：{best_k}",
              f"- 各簇数 silhouette：{ {k: round(v,4) for k,v in scores.items()} }\n"]

    if failed:
        lines.append("## 加载失败\n")
        lines += [f"- {c}: {r}" for c, r in failed]
        lines.append("")

    clusters = {}
    for code, cid in cluster_map.items():
        clusters.setdefault(cid, []).append(code)

    lines.append("## 聚类分组\n")
    for cid in sorted(clusters):
        members = clusters[cid]
        lines.append(f"### 簇 {cid}（{len(members)} 只）\n")
        lines.append("| 代码 | 基准 | 与基准均值相关 |")
        lines.append("|------|------|---------------|")
        for code in members:
            is_base = "是" if code in baseline else ""
            mc = mean_corr.get(code, float("nan"))
            mc_s = f"{mc:.3f}" if not np.isnan(mc) else "—"
            lines.append(f"| {code} | {is_base} | {mc_s} |")
        if len(members) > 1:
            sub = corr.loc[members, members].values
            n = len(members)
            intra = [sub[i, j] for i in range(n) for j in range(i + 1, n)]
            lines.append(f"\n簇内平均相关：{np.mean(intra):.3f}\n")
        else:
            lines.append("")

    lines.append("## 全样本相关矩阵\n")
    lines.append(df_to_md(corr.round(3)))
    return "\n".join(lines)


def main():
    args = parse_args()
    codes = [c.strip() for c in args.codes.split(",") if c.strip()]
    baseline = {c.strip() for c in args.baseline.split(",") if c.strip()}
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"加载 {len(codes)} 个标的，{args.start} ~ {args.end}，adjust={args.adjust}\n")
    returns, failed = load_returns(codes, args.start, args.end, args.adjust)

    corr = returns.corr()
    corr.to_csv(out_dir / "corr_matrix_full.csv")
    yearly_df = yearly_corr(returns)
    yearly_df.to_csv(out_dir / "corr_matrix_yearly.csv", index=False)
    print(f"\n全样本矩阵 → {out_dir/'corr_matrix_full.csv'}")
    print(f"按年分层 → {out_dir/'corr_matrix_yearly.csv'}")

    cluster_map, best_k, scores = hierarchical_cluster(
        corr, args.linkage, args.min_clusters, args.max_clusters)
    print(f"\n聚类（{args.linkage}）：最优 {best_k} 簇，silhouette={ {k:round(v,4) for k,v in scores.items()} }")

    mean_corr = mean_corr_with_baseline(corr, baseline)
    report = build_report(args, corr, yearly_df, cluster_map, best_k,
                          scores, mean_corr, baseline, failed, len(returns))
    md_path = out_dir / "corr_clusters.md"
    md_path.write_text(report, encoding="utf-8")
    print(f"聚类报告 → {md_path}")

    # 终端摘要 + 建议名单
    print("\n" + "=" * 60)
    clusters = {}
    for code, cid in cluster_map.items():
        clusters.setdefault(cid, []).append(code)
    for cid in sorted(clusters):
        members = clusters[cid]
        print(f"\n簇 {cid}（{len(members)} 只）: {', '.join(members)}")
        for code in members:
            if code not in baseline:
                mc = mean_corr.get(code, float("nan"))
                print(f"  {code}: 与基准均值相关 {mc:.3f}" if not np.isnan(mc) else f"  {code}")

    suggested = []
    for cid in sorted(clusters):
        members = clusters[cid]
        base_here = [c for c in members if c in baseline]
        non_base = sorted([c for c in members if c not in baseline],
                          key=lambda c: mean_corr.get(c, float("inf")))
        keep = non_base[:1] if base_here else non_base[:2]
        suggested.extend(base_here + keep)

    print("\n" + "=" * 60)
    print(f"建议保留名单（{len(suggested)} 只，基准固定 + 每簇 1–2 只）")
    print("=" * 60)
    print(", ".join(suggested))
    print("\n最终名单请你按业务偏好拍板；本脚本只给数据与建议。")


if __name__ == "__main__":
    main()