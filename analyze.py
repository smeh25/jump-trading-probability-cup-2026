#!/usr/bin/env python3
"""analyze.py — recompute all results_log.md aggregates straight from
predictions.csv. The log's "Findings" section is just the latest output of this;
never hand-edit those numbers — rerun `python3 analyze.py` instead.

doc-edge = (crowd_brier - your_brier)*100, the edge vs a consensus-copier (the
only thing that ranks you vs other sharps). Platform RBP includes the universal
+~3.2/prop variance cushion on top.
"""
import csv
import math
import sys
import statistics as st
from collections import defaultdict, OrderedDict


def load(path="predictions.csv"):
    rows = [r for r in csv.DictReader(open(path))
            if r["you_pct"] != "NA" and r["crowd_pct"] != "NA"]   # settled rows only
    for r in rows:
        r["you"] = float(r["you_pct"]); r["crowd"] = float(r["crowd_pct"])
        r["plat"] = float(r["rbp_platform"]); r["doc"] = float(r["rbp_docformula"])
        r["by"] = float(r["brier_you"]); r["bc"] = float(r["brier_crowd"])
        r["out"] = float(r["outcome"])                            # 0/1 realized
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


# ------------------------------------------------------------------ reliability
# Everything below is the `analyze.py reliability` calibration audit. It touches
# none of the default `main()` path above. Pure stdlib. Unweighted: each prop is
# one Bernoulli trial (stage_weight is a points multiplier, irrelevant to whether
# our PROBABILITIES are accurate).

Z95 = 1.959963985


def _clip01(p, eps=1e-6):
    return min(1 - eps, max(eps, p))


def _logit(p):
    p = _clip01(p)
    return math.log(p / (1 - p))


def _sigmoid(z):
    if z >= 0:
        e = math.exp(-z); return 1 / (1 + e)
    e = math.exp(z); return e / (1 + e)


def _wilson(k, n):
    """Wilson 95% CI for a binomial rate k/n -> (lo, hi)."""
    if n == 0:
        return (0.0, 1.0)
    p = k / n; z2 = Z95 * Z95
    denom = 1 + z2 / n
    center = (p + z2 / (2 * n)) / denom
    half = (Z95 * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n))) / denom
    return (max(0.0, center - half), min(1.0, center + half))


def _bin_stats(rows):
    """Per-bin dict from a list of rows: n, mean forecast, realized, gap, Wilson CI."""
    n = len(rows)
    f = sum(r["you"] for r in rows) / n / 100.0
    k = sum(r["out"] for r in rows)
    realized = k / n
    lo, hi = _wilson(k, n)
    return dict(n=n, f=f, realized=realized, gap=realized - f, lo=lo, hi=hi,
                sig=not (lo <= f <= hi))   # sig = forecast outside realized CI


def _quantile_bins(rows, nbins=8):
    """Equal-count bins by you_pct (tight, roughly equal CIs)."""
    s = sorted(rows, key=lambda r: r["you"])
    n = len(s); out = []
    for i in range(nbins):
        a = i * n // nbins; b = (i + 1) * n // nbins
        chunk = s[a:b]
        if chunk:
            st_ = _bin_stats(chunk)
            st_["edge"] = (chunk[0]["you"], chunk[-1]["you"])
            out.append(st_)
    return out


def _fixed_bins(rows):
    """Fixed 10-wide bins, pooled at the sparse tails: [0-20),20-30,...,70-80,[80-100]."""
    edges = [0, 20, 30, 40, 50, 60, 70, 80, 100]
    out = []
    for lo, hi in zip(edges[:-1], edges[1:]):
        chunk = [r for r in rows if (lo <= r["you"] < hi) or (hi == 100 and r["you"] == 100)]
        if chunk:
            st_ = _bin_stats(chunk)
            st_["edge"] = (lo, hi)
            out.append(st_)
    return out


def _platt_fit(rows, l2=1e-6, iters=100):
    """2-param logistic recal:  out ~ sigmoid(a + b * logit(you/100)).
    Newton/IRLS. Returns (a, b). b<1 => overconfident (extremes too extreme);
    b>1 => underconfident. a != 0 => directional YES/NO bias at the midpoint."""
    zs = [_logit(r["you"] / 100.0) for r in rows]
    ys = [r["out"] for r in rows]
    a, b = 0.0, 1.0
    for _ in range(iters):
        # gradient g (2,) and Hessian H (2x2) of penalized log-likelihood
        g0 = g1 = 0.0
        h00 = h01 = h11 = 0.0
        for z, y in zip(zs, ys):
            p = _sigmoid(a + b * z)
            w = p * (1 - p)
            r = y - p
            g0 += r; g1 += r * z
            h00 += w; h01 += w * z; h11 += w * z * z
        # L2 on b only (keep a free); regularize Hessian for stability
        g1 -= l2 * b
        h00 += 1e-9; h11 += l2 + 1e-9
        det = h00 * h11 - h01 * h01
        if abs(det) < 1e-12:
            break
        da = (h11 * g0 - h01 * g1) / det
        db = (-h01 * g0 + h00 * g1) / det
        a += da; b += db
        if abs(da) < 1e-9 and abs(db) < 1e-9:
            break
    return a, b


def _recal(a, b, you):
    """Apply the fitted Platt map to a raw you_pct (0-100) -> corrected pct."""
    return 100.0 * _sigmoid(a + b * _logit(you / 100.0))


def _ece(bins):
    N = sum(x["n"] for x in bins)
    ece = sum(x["n"] * abs(x["gap"]) for x in bins) / N
    mce = max(abs(x["gap"]) for x in bins)
    return ece, mce


def _brier_decomp(rows, bins):
    """Murphy decomposition of mean Brier over the given bins:
       BS = reliability - resolution + uncertainty."""
    N = len(rows)
    obar = sum(r["out"] for r in rows) / N
    reliab = sum(x["n"] * (x["f"] - x["realized"]) ** 2 for x in bins) / N
    resol = sum(x["n"] * (x["realized"] - obar) ** 2 for x in bins) / N
    uncert = obar * (1 - obar)
    return reliab, resol, uncert, obar


def _fmt_bin_table(bins, label):
    lines = [f"### {label}",
             "",
             "| bin | n | mean(you) | realized | gap | 95% CI (realized) | flag |",
             "|---|---:|---:|---:|---:|---|:--:|"]
    for x in bins:
        e = x["edge"]
        rng = f"{e[0]:.0f}–{e[1]:.0f}"
        flag = "**≠**" if x["sig"] else ""
        lines.append(f"| {rng} | {x['n']} | {x['f']*100:.1f} | {x['realized']*100:.1f} | "
                     f"{x['gap']*100:+.1f} | [{x['lo']*100:.0f}, {x['hi']*100:.0f}] | {flag} |")
    lines.append("")
    return "\n".join(lines)


def reliability(path="predictions.csv", out_path="self_calibration.md"):
    rows = load(path)
    N = len(rows)
    a, b = _platt_fit(rows)
    qb = _quantile_bins(rows, 8)
    fb = _fixed_bins(rows)
    ece_q, mce_q = _ece(qb)
    reliab, resol, uncert, obar = _brier_decomp(rows, fb)
    bs_recon = reliab - resol + uncert
    bs_mean = st.mean(r["by"] for r in rows)

    # global segmentation: per-category / direction / half-scope Platt slopes,
    # EB-shrunk toward the global slope (K-shrink, same idea as crowdmodel.py).
    K = 60.0

    def seg(groups):
        out = []
        for name, sub in groups:
            if len(sub) < 8:
                out.append((name, len(sub), None, None, None, None)); continue
            sa, sb = _platt_fit(sub)
            n = len(sub)
            sb_shr = (n / (n + K)) * sb + (K / (n + K)) * b
            fb_s = _fixed_bins(sub)
            ece_s, _ = _ece(fb_s)
            # does any bin clear its CI?
            clears = any(x["sig"] for x in fb_s)
            out.append((name, n, sa, sb, sb_shr, (ece_s, clears)))
        return out

    cat_groups = sorted(
        {c: [r for r in rows if r["category"] == c] for c in {r["category"] for r in rows}}.items(),
        key=lambda kv: -len(kv[1]))
    dir_groups = [
        ("below crowd", [r for r in rows if r["you"] < r["crowd"] - 0.5]),
        ("above crowd", [r for r in rows if r["you"] > r["crowd"] + 0.5]),
        ("~match", [r for r in rows if abs(r["you"] - r["crowd"]) <= 0.5]),
    ]
    half_groups = [
        ("half-scoped", [r for r in rows if r["is_half_scoped"] == "true"]),
        ("full-match", [r for r in rows if r["is_half_scoped"] == "false"]),
    ]

    def seg_table(title, segd):
        L = [f"### {title}", "",
             "| segment | n | raw slope b | EB-shrunk b | ECE | a bin clears CI? |",
             "|---|---:|---:|---:|---:|:--:|"]
        for name, n, sa, sb, sb_shr, ec in segd:
            if sb is None:
                L.append(f"| {name} | {n} | — | — | — | (n<8) |"); continue
            ece_s, clears = ec
            L.append(f"| {name} | {n} | {sb:.3f} | {sb_shr:.3f} | {ece_s*100:.1f} | "
                     f"{'**yes**' if clears else 'no'} |")
        L.append("")
        return "\n".join(L)

    conf = ("OVERCONFIDENT (extremes too extreme, shrink toward 50)" if b < 0.97 else
            "UNDERCONFIDENT (push extremes out)" if b > 1.03 else
            "WELL-CALIBRATED on slope")
    bias = ("YES-biased (lower everything)" if a > 0.05 else
            "NO-biased (raise everything)" if a < -0.05 else "no directional bias")

    doc = []
    doc.append("# Self-calibration audit")
    doc.append("")
    doc.append("_auto-generated by `python3 analyze.py reliability` — do not hand-edit; rerun._")
    doc.append("")
    doc.append(f"**n = {N} settled props** (unweighted: one Bernoulli each; "
               f"`stage_weight` is a points multiplier, irrelevant to probability accuracy). "
               f"Realized YES base rate = {obar*100:.1f}%.")
    doc.append("")
    doc.append("## Global Platt fit  `out ~ sigmoid(a + b·logit(you/100))`")
    doc.append("")
    doc.append(f"- **slope b = {b:.3f}** → {conf}")
    doc.append(f"- **intercept a = {a:+.3f}** → {bias}")
    doc.append(f"- **ECE = {ece_q*100:.2f}%** (quantile bins), **MCE = {mce_q*100:.1f}%**")
    doc.append("")
    doc.append("Worked corrections (raw you_pct → recalibrated):")
    doc.append("")
    doc.append("| raw | 20 | 30 | 40 | 50 | 60 | 70 | 80 |")
    doc.append("|---|---|---|---|---|---|---|---|")
    doc.append("| recal | " + " | ".join(f"{_recal(a,b,x):.0f}" for x in (20,30,40,50,60,70,80)) + " |")
    doc.append("")
    doc.append("## Reliability tables")
    doc.append("")
    doc.append("`flag = ≠` marks a bin whose mean forecast falls **outside** the Wilson CI of the "
               "realized rate — a gap too big to be noise.")
    doc.append("")
    doc.append(_fmt_bin_table(qb, "Quantile bins (equal-count, ~%d each — primary)" % (N // len(qb))))
    doc.append(_fmt_bin_table(fb, "Fixed 10-wide bins (tails pooled — readability)"))
    doc.append("## Brier decomposition (Murphy, over fixed bins)")
    doc.append("")
    doc.append(f"- reliability (lower=better) = **{reliab:.4f}**")
    doc.append(f"- resolution  (higher=better) = **{resol:.4f}**")
    doc.append(f"- uncertainty (base)          = **{uncert:.4f}**")
    doc.append(f"- reconstructed BS = rel − res + unc = **{bs_recon:.4f}**  "
               f"(analyze.py mean Brier = {bs_mean:.4f})")
    doc.append("")
    doc.append("## Segmentation (slopes EB-shrunk toward global b, K=%.0f)" % K)
    doc.append("")
    doc.append("Per-segment slopes are noisy at these n — the shrunk column is the honest read; "
               "trust a per-segment correction only where a bin clears its CI.")
    doc.append("")
    doc.append(seg_table("By category", seg(cat_groups)))
    doc.append(seg_table("By direction vs crowd", seg(dir_groups)))
    doc.append(seg_table("By half-scope", seg(half_groups)))

    open(out_path, "w").write("\n".join(doc))
    # console summary
    print(f"reliability: n={N}  slope b={b:.3f} ({conf})  a={a:+.3f} ({bias})")
    print(f"  ECE={ece_q*100:.2f}%  MCE={mce_q*100:.1f}%  base rate={obar*100:.1f}%")
    print(f"  Brier decomp: rel={reliab:.4f} res={resol:.4f} unc={uncert:.4f} "
          f"-> BS={bs_recon:.4f} (mean {bs_mean:.4f})")
    print(f"  wrote {out_path}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "reliability":
        reliability()
    else:
        main()
