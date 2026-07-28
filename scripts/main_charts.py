#!/usr/bin/env python3
"""Generate the README charts from predictions.csv into images/.

Four figures: reliability curve, cumulative doc-edge with null band,
crowd-model fit, and doc-edge by category. Run: python3 scripts/main_charts.py
"""
import csv, math, os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# --- validated palette (light surface) ---
SURFACE   = "#fcfcfb"
INK       = "#0b0b0b"
INK2      = "#52514e"
MUTED     = "#898781"
GRID      = "#e1e0d9"
AXIS      = "#c3c2b7"
BLUE      = "#2a78d6"   # series 1 / positive
ORANGE    = "#eb6834"   # series 2
RED       = "#e34948"   # negative pole
BANDGRAY  = "#e1e0d9"

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT  = os.path.join(HERE, "images")
os.makedirs(OUT, exist_ok=True)

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "font.family": "sans-serif", "font.size": 11,
    "axes.edgecolor": AXIS, "axes.labelcolor": INK2, "axes.titlecolor": INK,
    "xtick.color": MUTED, "ytick.color": MUTED, "text.color": INK2,
    "axes.spines.top": False, "axes.spines.right": False,
})

def load():
    rows = [r for r in csv.DictReader(open(os.path.join(HERE, "predictions.csv")))
            if r["outcome"] in ("0", "1")]
    for r in rows:
        r["mid"] = int(r["match_id"]); r["q"] = int(r["q"])
        r["you"] = float(r["you_pct"]); r["out"] = float(r["outcome"])
        r["doc"] = float(r["rbp_docformula"])
        r["crowd"] = float(r["crowd_pct"]) if r["crowd_pct"] not in ("", "NA") else None
        r["chat"] = float(r["crowd_hat"]) if r["crowd_hat"] not in ("", "NA") else None
    return sorted(rows, key=lambda r: (r["mid"], r["q"]))

def style(ax):
    ax.grid(axis="y", color=GRID, linewidth=0.8, zorder=0)
    ax.set_axisbelow(True)
    ax.tick_params(length=0)

def reliability(rows):
    fig, ax = plt.subplots(figsize=(6.2, 4.6))
    ax.plot([0,100],[0,100], color=MUTED, lw=1, ls=(0,(4,4)), zorder=1)
    for key, color, label in [("you", BLUE, "Forecast"), ("crowd", ORANGE, "Crowd")]:
        pts = [(r[key], r["out"]) for r in rows if r[key] is not None]
        xs, ys = [], []
        for lo in range(0, 100, 10):
            b = [o for p,o in pts if lo <= p < lo+10]
            if b:
                xs.append(lo+5); ys.append(100*sum(b)/len(b))
        ax.plot(xs, ys, color=color, lw=2, marker="o", ms=7, label=label, zorder=3)
    style(ax)
    ax.set_xlim(0,100); ax.set_ylim(0,100)
    ax.set_xlabel("Predicted probability"); ax.set_ylabel("Observed frequency")
    ax.set_title("Reliability — forecast vs. crowd", loc="left", fontweight="bold", pad=12)
    ax.legend(frameon=False, loc="upper left")
    fig.tight_layout(); fig.savefig(os.path.join(OUT,"reliability.png"), dpi=150); plt.close(fig)

def cumulative(rows):
    docs = [r["doc"] for r in rows]
    n = len(docs)
    sd = (sum((d-sum(docs)/n)**2 for d in docs)/(n-1))**0.5
    # cumulative after each match
    per_match, cum, xs, ys = {}, 0.0, [], []
    counts = {}
    for r in rows:
        per_match[r["mid"]] = per_match.get(r["mid"],0)+r["doc"]
        counts[r["mid"]] = counts.get(r["mid"],0)+1
    run=0.0; k=0
    for m in sorted(per_match):
        run += per_match[m]; k += counts[m]
        xs.append(m); ys.append(run)
    band1 = [sd*math.sqrt(sum(counts[j] for j in sorted(per_match) if j<=m)) for m in xs]
    fig, ax = plt.subplots(figsize=(6.2, 4.6))
    ax.fill_between(xs, [-2*b for b in band1], [2*b for b in band1], color=BANDGRAY, alpha=0.45, lw=0, zorder=1, label="±2σ null")
    ax.fill_between(xs, [-b for b in band1], band1, color=BANDGRAY, alpha=0.8, lw=0, zorder=2, label="±1σ null")
    ax.axhline(0, color=AXIS, lw=1, zorder=2)
    ax.plot(xs, ys, color=BLUE, lw=2.2, zorder=4)
    ax.text(xs[-1], ys[-1], f"  +{ys[-1]:.0f}", color=BLUE, va="center", fontweight="bold")
    style(ax)
    ax.set_xlabel("Match"); ax.set_ylabel("Cumulative doc-edge")
    ax.set_title("Cumulative doc-edge vs. a zero-edge null", loc="left", fontweight="bold", pad=12)
    ax.legend(frameon=False, loc="upper left")
    fig.tight_layout(); fig.savefig(os.path.join(OUT,"cumulative_edge.png"), dpi=150); plt.close(fig)

def crowd_fit(rows):
    pts = [(r["chat"], r["crowd"]) for r in rows if r["chat"] is not None and r["crowd"] is not None]
    mae = sum(abs(a-b) for a,b in pts)/len(pts)
    fig, ax = plt.subplots(figsize=(6.2, 4.6))
    ax.plot([0,100],[0,100], color=MUTED, lw=1, ls=(0,(4,4)), zorder=1)
    ax.scatter([a for a,_ in pts],[b for _,b in pts], s=16, color=BLUE, alpha=0.35,
               edgecolors="none", zorder=3)
    style(ax)
    ax.set_xlim(0,100); ax.set_ylim(0,100)
    ax.set_xlabel("Predicted crowd %"); ax.set_ylabel("Actual crowd %")
    ax.set_title(f"Crowd-model fit — in-sample (n={len(pts)})", loc="left", fontweight="bold", pad=12)
    ax.text(0.97, 0.05, f"MAE {mae:.1f} in-sample · 3.58 LOOCV", transform=ax.transAxes,
            ha="right", va="bottom", color=MUTED, fontsize=9)
    fig.tight_layout(); fig.savefig(os.path.join(OUT,"crowd_model_fit.png"), dpi=150); plt.close(fig)

def by_category(rows):
    agg = {}
    for r in rows:
        agg.setdefault(r["category"], []).append(r["doc"])
    items = sorted(((c, sum(v)/len(v), len(v)) for c,v in agg.items()), key=lambda t: t[1])
    labels = [f"{c}  (n={n})" for c,_,n in items]
    vals   = [m for _,m,_ in items]
    colors = [BLUE if v>=0 else RED for v in vals]
    fig, ax = plt.subplots(figsize=(6.6, 4.8))
    ax.barh(range(len(vals)), vals, color=colors, height=0.66, zorder=3)
    ax.axvline(0, color=AXIS, lw=1, zorder=2)
    ax.set_yticks(range(len(vals))); ax.set_yticklabels(labels, color=INK2, fontsize=9)
    for i,v in enumerate(vals):
        ax.text(v + (0.03 if v>=0 else -0.03), i, f"{v:+.1f}", va="center",
                ha="left" if v>=0 else "right", color=INK2, fontsize=9)
    ax.grid(axis="x", color=GRID, linewidth=0.8, zorder=0); ax.set_axisbelow(True)
    ax.tick_params(length=0)
    ax.set_xlabel("Mean doc-edge per prop")
    ax.set_title("Doc-edge by category", loc="left", fontweight="bold", pad=12)
    fig.tight_layout(); fig.savefig(os.path.join(OUT,"edge_by_category.png"), dpi=150); plt.close(fig)

if __name__ == "__main__":
    rows = load()
    reliability(rows); cumulative(rows); crowd_fit(rows); by_category(rows)
    print(f"wrote 4 charts to {OUT}")