#!/usr/bin/env python3
"""analyze.py — recompute all results_log.md aggregates straight from
predictions.csv. The log's "Findings" section is just the latest output of this;
never hand-edit those numbers — rerun `python3 analyze.py` instead.

doc-edge = (crowd_brier - your_brier)*100, the edge vs a consensus-copier (the
only thing that ranks you vs other sharps). Platform RBP includes the universal
+~3.2/prop variance cushion on top.
"""
import csv
import statistics as st
from collections import defaultdict, OrderedDict


def load(path="predictions.csv"):
    rows = [r for r in csv.DictReader(open(path))
            if r["you_pct"] != "NA" and r["crowd_pct"] != "NA"]   # settled rows only
    for r in rows:
        r["you"] = float(r["you_pct"]); r["crowd"] = float(r["crowd_pct"])
        r["plat"] = float(r["rbp_platform"]); r["doc"] = float(r["rbp_docformula"])
        r["by"] = float(r["brier_you"]); r["bc"] = float(r["brier_crowd"])
    return rows


def main():
    rows = load()
    n = len(rows)
    plat = sum(r["plat"] for r in rows); doc = sum(r["doc"] for r in rows)
    se_tot = st.pstdev([r["doc"] for r in rows]) * n ** 0.5
    print(f"CUMULATIVE  n={n} played props")
    print(f"  platform RBP  {plat:+.1f}  ({plat/n:+.2f}/prop)")
    print(f"  doc-edge      {doc:+.1f}  ({doc/n:+.3f}/prop)  "
          f"total SE ~±{se_tot:.0f} -> {doc/se_tot:+.2f} SE from zero")
    print(f"  mean Brier    you {st.mean(r['by'] for r in rows):.3f}  "
          f"crowd {st.mean(r['bc'] for r in rows):.3f}")
    print(f"  beat crowd    {sum(r['plat'] > 0 for r in rows)}/{n}")

    print("\nBY CATEGORY  doc/prop (sorted)")
    cat = defaultdict(list)
    for r in rows:
        cat[r["category"]].append(r["doc"])
    for c, v in sorted(cat.items(), key=lambda x: -sum(x[1]) / len(x[1])):
        se = st.pstdev(v) / len(v) ** 0.5 if len(v) > 1 else 0
        print(f"  {c:16} n={len(v):>2}  tot={sum(v):+6.1f}  "
              f"mean={sum(v)/len(v):+5.2f}  SE={se:.2f}")

    print("\nBY DIRECTION  doc/prop")
    for lbl, f in [("below crowd", lambda r: r["you"] < r["crowd"] - 0.5),
                   ("above crowd", lambda r: r["you"] > r["crowd"] + 0.5),
                   ("~match", lambda r: abs(r["you"] - r["crowd"]) <= 0.5)]:
        v = [r["doc"] for r in rows if f(r)]
        if v:
            print(f"  {lbl:12} n={len(v):>2}  tot={sum(v):+6.1f}  mean={sum(v)/len(v):+5.2f}")

    print("\nBY HALF-SCOPE  doc/prop")
    for h in ("true", "false"):
        v = [r["doc"] for r in rows if r["is_half_scoped"] == h]
        print(f"  half={h:5} n={len(v):>3}  mean={sum(v)/len(v):+5.2f}")

    print("\nPER MATCH")
    mg = OrderedDict()
    for r in rows:
        mg.setdefault((int(r["match_id"]), r["team_a"], r["team_b"]), []).append(r)
    for (mid, a, b), rs in sorted(mg.items()):
        p = sum(x["plat"] for x in rs); d = sum(x["doc"] for x in rs)
        beat = sum(x["plat"] > 0 for x in rs)
        star = max(rs, key=lambda x: x["plat"])
        print(f"  M{mid:>2} {a[:12]:12} v {b[:12]:12} "
              f"plat {p:+6.1f}  doc {d:+6.1f}  {beat}/{len(rs)}  "
              f"top: {star['prop'][:32]} (+{star['plat']:.1f})")


if __name__ == "__main__":
    main()
