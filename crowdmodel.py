#!/usr/bin/env python3
"""crowdmodel.py — estimate where the CROWD will land given our own number.

Why: the contest score (doc-formula RBP) only rewards being closer to the truth
than the crowd. To act on the deviate-down/up edge BEFORE settlement we need a
prior for the unseen crowd_pct. Empirically (139 staked props) the crowd is a
*shrunk* version of our number toward the mid-50s, plus a per-category offset:

    crowd ≈ A_c + B_c · (you − 50)          (you, crowd in 0–100 points)

with A_c the crowd level at you=50 and B_c<1 the compression slope. Per-category
(A_c, B_c) are partially pooled toward the global line (empirical-Bayes shrink,
strength k props) so thin buckets don't overfit. An optional additive
is_half_scoped offset is pooled the same way.

CLI:
    python3 crowdmodel.py fit                 # fit table + leave-one-match-out CV
    python3 crowdmodel.py predict 30 fav_player [--half]
    python3 crowdmodel.py card mycard.txt     # whole match at once (see `card` below)

`card` input file: one prop per line, `you,category,half,label`
  half = 0/1 or true/false ; label optional ; blank lines and #comments ignored
  e.g.   16,race,1,Jordan more 2H SOT
"""
import csv
import sys
from collections import defaultdict

CSV = "predictions.csv"
K_CAT = 10.0    # shrink strength for per-category (A,B), in equivalent props
K_HALF = 8.0    # shrink strength for the half offset


def load(path=CSV):
    rows = []
    for r in csv.DictReader(open(path)):
        if r["you_pct"] == "NA" or r["crowd_pct"] == "NA":   # skip unplayed/unsettled
            continue
        rows.append({
            "you": float(r["you_pct"]),
            "crowd": float(r["crowd_pct"]),
            "cat": r["category"],
            "half": r["is_half_scoped"] == "true",
            "match": int(r["match_id"]),
        })
    return rows


def _fit_line(rows):
    """OLS crowd = A + B*(you-50); returns (A, B). A = crowd at you=50."""
    n = len(rows)
    xs = [r["you"] - 50 for r in rows]
    ys = [r["crowd"] for r in rows]
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx < 1e-9:                      # no spread in you -> intercept only
        return my, 0.0
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    return my - b * mx, b


def fit(rows, k_cat=K_CAT, k_half=K_HALF):
    """Returns a model dict: global line, shrunk per-cat lines, half offsets."""
    A0, B0 = _fit_line(rows)
    bycat = defaultdict(list)
    for r in rows:
        bycat[r["cat"]].append(r)
    cats = {}
    for c, rs in bycat.items():
        Ac, Bc = _fit_line(rs)
        n = len(rs)
        w = n / (n + k_cat)
        cats[c] = {
            "n": n,
            "A": w * Ac + (1 - w) * A0,
            "B": w * Bc + (1 - w) * B0,
            "A_raw": Ac, "B_raw": Bc,
        }
    # half offset = mean residual of (crowd - base_pred) among half-scoped props,
    # shrunk toward 0; computed against the (already shrunk) category line.
    def base_pred(r):
        m = cats[r["cat"]]
        return m["A"] + m["B"] * (r["you"] - 50)
    half_res = [r["crowd"] - base_pred(r) for r in rows if r["half"]]
    if half_res:
        nh = len(half_res)
        half_off = (nh / (nh + k_half)) * (sum(half_res) / nh)
    else:
        half_off = 0.0
    return {"A0": A0, "B0": B0, "cats": cats, "half_off": half_off,
            "k_cat": k_cat, "k_half": k_half}


def predict(model, you, cat, half=False):
    m = model["cats"].get(cat)
    if m is None:                              # unseen category -> global line
        A, B = model["A0"], model["B0"]
    else:
        A, B = m["A"], m["B"]
    p = A + B * (you - 50)
    if half:
        p += model["half_off"]
    return max(1.0, min(99.0, p))


# ----------------------------------------------------------- validation
def _mae(rows, fn):
    return sum(abs(fn(r) - r["crowd"]) for r in rows) / len(rows)


def loocv_by_match(rows):
    """Leave-one-MATCH-out CV: refit on the other matches, predict the held-out
    match. Match-level (not row-level) so we never leak within-match info."""
    matches = sorted({r["match"] for r in rows})
    preds = {"model": [], "global": [], "copy": []}
    for held in matches:
        train = [r for r in rows if r["match"] != held]
        test = [r for r in rows if r["match"] == held]
        mdl = fit(train)
        A0, B0 = mdl["A0"], mdl["B0"]
        for r in test:
            preds["model"].append((predict(mdl, r["you"], r["cat"], r["half"]), r["crowd"]))
            preds["global"].append((max(1, min(99, A0 + B0 * (r["you"] - 50))), r["crowd"]))
            preds["copy"].append((r["you"], r["crowd"]))
    out = {}
    for k, pl in preds.items():
        mae = sum(abs(p - c) for p, c in pl) / len(pl)
        rmse = (sum((p - c) ** 2 for p, c in pl) / len(pl)) ** 0.5
        out[k] = (mae, rmse)
    return out


def main(argv):
    if not argv or argv[0] == "fit":
        rows = load()
        mdl = fit(rows)
        print(f"n={len(rows)} staked props.  global: crowd = {mdl['A0']:.1f} "
              f"+ {mdl['B0']:.3f}*(you-50)   half_offset={mdl['half_off']:+.2f}\n")
        print(f"{'category':16} {'n':>3} {'A(@50)':>7} {'B':>6} | {'A_raw':>6} {'B_raw':>6}")
        for c, m in sorted(mdl["cats"].items(), key=lambda x: -x[1]["n"]):
            print(f"{c:16} {m['n']:>3} {m['A']:>7.1f} {m['B']:>6.3f} | "
                  f"{m['A_raw']:>6.1f} {m['B_raw']:>6.3f}")
        cv = loocv_by_match(rows)
        print("\nleave-one-MATCH-out CV (predicting unseen crowd_pct):")
        print(f"  {'method':10} {'MAE':>6} {'RMSE':>6}")
        for k in ("copy", "global", "model"):
            mae, rmse = cv[k]
            print(f"  {k:10} {mae:>6.2f} {rmse:>6.2f}")
        print("  (copy = predict crowd==you; global = one line; model = per-category)")
    elif argv[0] == "predict":
        you = float(argv[1]); cat = argv[2]; half = "--half" in argv[3:]
        mdl = fit(load())
        ch = predict(mdl, you, cat, half)
        print(f"you={you:.0f}  cat={cat}  half={half}  ->  crowd_hat={ch:.1f}  "
              f"(gap {ch-you:+.1f})")
    elif argv[0] == "card":
        mdl = fit(load())                       # fit on ALL logged matches
        cats = set(mdl["cats"])
        # gap = crowd_hat - you. E[RBP if your number is the truth] = gap^2 / 100
        # (in points), the prize you collect for that deviation IF you're right.
        print(f"{'prop':24} {'you':>3} {'crowd':>5} {'gap':>5} {'E[RBP]':>6}  zone / note")
        for ln in open(argv[1]):
            ln = ln.split("#")[0].strip()
            if not ln:
                continue
            parts = [p.strip() for p in ln.split(",")]
            you = float(parts[0]); cat = parts[1]
            half = len(parts) > 2 and parts[2].lower() in ("1", "true", "t", "yes")
            label = parts[3] if len(parts) > 3 else cat
            if cat not in cats:
                print(f"{label:24}  !! unknown category '{cat}' (using global line)")
            ch = predict(mdl, you, cat, half)
            gap = ch - you
            erbp = gap ** 2 / 100.0
            if gap > 1.5:            # you sit BELOW crowd = our reliable direction
                note = "below crowd -> collect (our +EV side)"
            elif gap < -1.5:         # you sit ABOVE crowd = our leak direction
                note = f"ABOVE crowd -> trim to ~{round(ch)} UNLESS you have a reason"
            else:
                note = "~at crowd -> small edge, banks the cushion"
            print(f"{label:24} {you:>3.0f} {ch:>5.1f} {gap:>+5.1f} {erbp:>6.2f}  {note}")
    else:
        print(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
