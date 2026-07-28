#!/usr/bin/env python3
"""Offline 3-way calibration for proppricer.EVENT_CURVE.

Lays the event-timing CDF (cumulative share of full-match events by minute) side by
side from three sources, so we can decide the F(23)/F(45)/F(68) nodes jointly instead
of overfitting any single dataset:

  * prior      -- HALF_SHARE (domain prior, lambda_reference.md; only specifies F(45),
                  plus within-half anchors for goals). Currently in EVENT_CURVE.
  * 2018-22    -- StatsBomb Open Data men's WC 2018+2022 event JSON. Per-second
                  timestamps -> exact quarter buckets for every event type.
  * 2026       -- ESPN summary API (keyEvents). Carries minutes for GOALS / CARDS /
                  SUBS / PENALTIES only; corners/offsides/fouls/shots/SOT are boxscore
                  TOTALS with no minute, so 2026 cannot time them ("n/a — aggregates").

2026 is the structurally relevant distribution (mandatory mid-half hydration breaks
~23'/68'), but small-n on most events; 2018-22 is event-level but pre-hydration-break;
the prior is mechanism-justified and validated on our 2026 half-prop results. The table
this writes (calibration_output.md) is the deliverable — choose final nodes from it.

Offline calibration ONLY — never imported by pricing. JSON is cached (refreshable as
knockouts play; ESPN scoreboard for today/future is never cached). HALF_SHARE / F(45)
stay pinned unless we deliberately change the tested constant.

    python3 calibrate_curve.py
"""
import csv, json, math, os, re, sys, urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

import proppricer as P

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_MD = os.path.join(HERE, "calibration_output.md")
PRED_CSV = os.path.join(HERE, "predictions.csv")

SCRATCH = os.path.join(HERE, ".cache")   # local cache for downloaded StatsBomb/ESPN data
SB_CACHE = os.path.join(SCRATCH, "sb_cache")
ESPN_CACHE = os.path.join(SCRATCH, "espn_cache")

SB_BASE = "https://raw.githubusercontent.com/statsbomb/open-data/master/data"
SB_COMPS = [(43, 3), (43, 106)]  # WC 2018, WC 2022

ESPN = "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world"
WC2026_START = date(2026, 6, 11)
# events ESPN keyEvents timestamps; the rest are boxscore aggregates (no minute)
ESPN_TIMED = ("goals", "cards", "penalties")


def _get(url, path, timeout=60):
    if path and os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    data = json.load(urllib.request.urlopen(url, timeout=timeout))
    if path:
        with open(path, "w") as f:
            json.dump(data, f)
    return data


def quarter(period, minute):
    """Index 0..3 for Q1/Q2/Q3/Q4 (stoppage folds into Q2/Q4); None for ET/pens.

    `minute` is the elapsed MATCH minute (period 2 runs 45..90+). Shared by both
    sources: StatsBomb's `minute` is already match-minute; ESPN's clock.value is
    match-clock seconds (period 2 starts at 2700s), so minute = int(value/60)."""
    if period == 1:
        return 0 if minute < 23 else 1
    if period == 2:
        return 2 if minute < 68 else 3
    return None


# ---------------------------------------------------------------- StatsBomb 2018-22
def sb_classify(ev):
    """Yield the EVENT_CURVE keys a StatsBomb event counts toward."""
    t = ev.get("type", {}).get("name")
    if t == "Shot":
        out = ev.get("shot", {}).get("outcome", {}).get("name")
        yield "shots"
        if out in ("Goal", "Saved", "Saved To Post"):
            yield "sot"
        if out == "Goal":
            yield "goals"
        if ev.get("shot", {}).get("type", {}).get("name") == "Penalty":
            yield "penalties"
    elif t == "Foul Committed":
        yield "fouls"
        if ev.get("foul_committed", {}).get("card"):
            yield "cards"
    elif t == "Bad Behaviour":
        if ev.get("bad_behaviour", {}).get("card"):
            yield "cards"
    elif t == "Offside":
        yield "offsides"
    elif t == "Pass":
        if ev.get("pass", {}).get("type", {}).get("name") == "Corner":
            yield "corners"
        if ev.get("pass", {}).get("outcome", {}).get("name") == "Pass Offside":
            yield "offsides"


def sb_counts():
    """Quarter counts per event from StatsBomb WC 2018+2022. Returns (counts, n_matches)."""
    os.makedirs(SB_CACHE, exist_ok=True)
    match_ids = []
    for cid, sid in SB_COMPS:
        ms = _get(f"{SB_BASE}/matches/{cid}/{sid}.json", f"{SB_CACHE}/matches_{cid}_{sid}.json")
        match_ids += [m["match_id"] for m in ms]

    def fetch(mid):
        return _get(f"{SB_BASE}/events/{mid}.json", f"{SB_CACHE}/ev_{mid}.json")

    counts = {k: [0, 0, 0, 0] for k in P.EVENT_CURVE}
    done = 0
    with ThreadPoolExecutor(max_workers=12) as ex:
        for evs in ex.map(fetch, match_ids):
            for ev in evs:
                q = quarter(ev.get("period"), ev.get("minute", 0))
                if q is None:
                    continue
                for key in sb_classify(ev):
                    counts[key][q] += 1
            done += 1
    return counts, done


# -------------------------------------------------------------------- ESPN 2026
def espn_event_ids():
    """Completed 2026 WC event IDs (deduped). Scoreboard for today/future is not cached."""
    os.makedirs(ESPN_CACHE, exist_ok=True)
    ids = {}
    d = WC2026_START
    today = date.today()
    while d <= today:
        ds = d.strftime("%Y%m%d")
        cache = f"{ESPN_CACHE}/sb_{ds}.json" if d < today else None
        try:
            j = _get(f"{ESPN}/scoreboard?dates={ds}", cache)
        except Exception:
            d += timedelta(days=1)
            continue
        for e in j.get("events", []):
            comp = (e.get("competitions") or [{}])[0]
            if comp.get("status", {}).get("type", {}).get("completed"):
                ids[e["id"]] = e.get("shortName", "")
        d += timedelta(days=1)
    return ids


def espn_classify(ev):
    """Yield EVENT_CURVE keys an ESPN keyEvent counts toward (timed types only)."""
    t = (ev.get("type", {}).get("text") or "")
    txt = (ev.get("text") or "").lower()
    if t == "Goal":
        yield "goals"
        if "penalt" in txt:
            yield "penalties"
    elif "Card" in t:                      # Yellow Card, Red Card, Yellow Red Card
        yield "cards"
    # standalone penalty miss/save (rare); penalty *goals* already counted above
    elif "Penalty" in t and "Missed" not in txt:
        yield "penalties"


def espn_counts():
    """Quarter counts for ESPN-timed events (goals/cards/penalties). Returns (counts, n)."""
    ids = espn_event_ids()

    def fetch(eid):
        return _get(f"{ESPN}/summary?event={eid}", f"{ESPN_CACHE}/sum_{eid}.json")

    counts = {k: [0, 0, 0, 0] for k in ESPN_TIMED}
    done = 0
    with ThreadPoolExecutor(max_workers=12) as ex:
        for j in ex.map(fetch, list(ids)):
            for ev in j.get("keyEvents", []):
                per = (ev.get("period") or {}).get("number")
                clk = (ev.get("clock") or {}).get("value")
                if per is None or clk is None:
                    continue
                q = quarter(per, int(clk / 60))
                if q is None:
                    continue
                for key in espn_classify(ev):
                    counts[key][q] += 1
            done += 1
    return counts, done, ids


def espn_spotcheck(eid="760447"):
    """Return goal (period, minute, text) tuples for one match to verify the parse."""
    j = _get(f"{ESPN}/summary?event={eid}", f"{ESPN_CACHE}/sum_{eid}.json")
    out = []
    for ev in j.get("keyEvents", []):
        if ev.get("type", {}).get("text") == "Goal":
            per = (ev.get("period") or {}).get("number")
            clk = (ev.get("clock") or {}).get("value")
            out.append((per, int(clk / 60), quarter(per, int(clk / 60)),
                        (ev.get("text") or "")[:40]))
    return out


# ----------------------------------------- rare-event shares (outside-box goal, OG)
# The rare props ("goal from OUTSIDE the box", "own goal") price as a SHARE of the
# game's goals, not a flat per-match rate:  E[event] = share * lambda_goals(match),
# P(>=1) = 1 - exp(-E).  We estimate `share` from both cached sources and decide it
# jointly.  Denominator = ALL regulation goals (scoreboard goals: open-play + pens +
# own goals) so it lines up with the lambda_goals we de-vig from the O/U market.

# StatsBomb penalty-area rectangle on the 120x80 pitch (goal mouth at x=120, y=40):
# 18-yd box spans x in [102,120], y in [18,62].  A goal struck OUTSIDE this box counts.
PBOX_X, PBOX_YLO, PBOX_YHI = 102.0, 18.0, 62.0

# ESPN has no structured outside-box / own-goal flag -> parse the narrative `text`.
OUTSIDE_RE = re.compile(r"outside the box|from outside|long[- ]?range", re.I)
OG_RE = re.compile(r"own goal|own-goal|\(o\.?g\.?\)", re.I)


def _sb_outside_box(loc):
    """True if a StatsBomb shot `location` [x,y] is outside the penalty area.
    Missing/short location -> treat as INSIDE (don't credit an unknown as outside)."""
    if not loc or len(loc) < 2:
        return False
    x, y = loc[0], loc[1]
    return not (x >= PBOX_X and PBOX_YLO <= y <= PBOX_YHI)


def sb_rare_shares():
    """StatsBomb 2018-22: outside-box-goal & own-goal counts as a share of all
    regulation goals. Returns counts, totals, shares, n_matches, spot samples."""
    os.makedirs(SB_CACHE, exist_ok=True)
    match_ids = []
    for cid, sid in SB_COMPS:
        ms = _get(f"{SB_BASE}/matches/{cid}/{sid}.json", f"{SB_CACHE}/matches_{cid}_{sid}.json")
        match_ids += [m["match_id"] for m in ms]

    def fetch(mid):
        return _get(f"{SB_BASE}/events/{mid}.json", f"{SB_CACHE}/ev_{mid}.json")

    total = outside = own = head = n = 0
    samples = []
    with ThreadPoolExecutor(max_workers=12) as ex:
        for evs in ex.map(fetch, match_ids):
            n += 1
            for ev in evs:
                if quarter(ev.get("period"), ev.get("minute", 0)) is None:
                    continue                       # regulation (period 1/2) only
                t = ev.get("type", {}).get("name")
                if t == "Shot":
                    sh = ev.get("shot", {})
                    if sh.get("outcome", {}).get("name") == "Goal":
                        total += 1
                        if sh.get("body_part", {}).get("name") == "Head":
                            head += 1
                        if sh.get("type", {}).get("name") != "Penalty" \
                                and _sb_outside_box(ev.get("location")):
                            outside += 1
                            if len(samples) < 6:
                                loc = ev.get("location", [0, 0])
                                samples.append(f"[{loc[0]:.1f},{loc[1]:.1f}]")
                elif t == "Own Goal For":          # one side of the pair -> no double count
                    total += 1
                    own += 1
    return {"src": "SB 2018-22", "n_matches": n, "total": total, "outside": outside,
            "own": own, "head": head, "share_outside": outside / total,
            "share_own": own / total, "share_head": head / total, "samples": samples}


def espn_rare_shares():
    """ESPN 2026 (text-parse): same two shares, current-rules cross-check."""
    ids = espn_event_ids()

    def fetch(eid):
        return _get(f"{ESPN}/summary?event={eid}", f"{ESPN_CACHE}/sum_{eid}.json")

    total = outside = own = head = n = 0
    samples = []
    with ThreadPoolExecutor(max_workers=12) as ex:
        for j in ex.map(fetch, list(ids)):
            n += 1
            for ev in j.get("keyEvents", []):
                # scoring events span 6 type.texts (Goal, Goal - Header/Volley/
                # Free-kick, Own Goal, Penalty - Scored) -> key off scoringPlay,
                # not type.text, so the denominator = real scoreboard goals.
                if not ev.get("scoringPlay"):
                    continue
                if (ev.get("period") or {}).get("number") not in (1, 2):
                    continue                       # regulation only
                tt = (ev.get("type", {}) or {}).get("text") or ""
                txt = ev.get("text") or ""
                total += 1
                if tt == "Goal - Header":                      # structured header flag
                    head += 1
                if tt == "Own Goal" or OG_RE.search(txt):     # structured OG flag
                    own += 1
                elif "Penalty" in tt:                          # spot kick = inside box
                    continue
                elif OUTSIDE_RE.search(txt):
                    outside += 1
                    if len(samples) < 6:
                        samples.append(txt[:78])
    share_o = outside / total if total else 0.0
    share_g = own / total if total else 0.0
    share_h = head / total if total else 0.0
    return {"src": "ESPN 2026", "n_matches": n, "total": total, "outside": outside,
            "own": own, "head": head, "share_outside": share_o, "share_own": share_g,
            "share_head": share_h, "samples": samples}


def rare(lam_sample=2.6, w_2026=0.65):
    """Stage-B deliverable: outside-box & own-goal share, both sources side by side,
    plus P(>=1) at a sample goal lambda. STOP here and pick the final share jointly."""
    print("StatsBomb 2018-22 (cached)...")
    sb = sb_rare_shares()
    print(f"  {sb['n_matches']} matches, {sb['total']} regulation goals")
    print(f"  outside-box goals: {sb['outside']:>3}  -> share {sb['share_outside']:.3f}"
          f"   sample locs {sb['samples']}")
    print(f"  own goals (OG For): {sb['own']:>3}  -> share {sb['share_own']:.3f}")
    print(f"  header goals:      {sb['head']:>3}  -> share {sb['share_head']:.3f}")

    print("\nESPN 2026 (cached; text-parse)...")
    e = espn_rare_shares()
    print(f"  {e['n_matches']} matches, {e['total']} regulation goals")
    print(f"  outside-box goals: {e['outside']:>3}  -> share {e['share_outside']:.3f}")
    for s in e["samples"]:
        print(f"      · {s}")
    print(f"  own goals:         {e['own']:>3}  -> share {e['share_own']:.3f}")
    print(f"  header goals:      {e['head']:>3}  -> share {e['share_head']:.3f}")

    def line(label, s_sb, s_26):
        rec = w_2026 * s_26 + (1 - w_2026) * s_sb           # lean-2026 blend
        e_ev = rec * lam_sample
        p = 1 - math.exp(-e_ev)
        assert abs(p - P.p_at_least(1, e_ev)) < 1e-9        # round-trips with proppricer
        flag = " <-- >3pt divergence" if abs(s_26 - s_sb) > 0.03 else ""
        print(f"  {label:14} SB {s_sb:.3f} | 2026 {s_26:.3f} | rec {rec:.3f} "
              f"| E {e_ev:.3f} | P(>=1) {p*100:4.1f}%{flag}")

    print(f"\nDECISION TABLE  (rec = {w_2026:.0%}*2026 + {1-w_2026:.0%}*SB;  "
          f"P at sample lambda_goals={lam_sample})")
    line("outside-box", sb["share_outside"], e["share_outside"])
    line("own-goal", sb["share_own"], e["share_own"])
    line("header", sb["share_head"], e["share_head"])
    print("\n  P(>=1) = 1 - exp(-share * lambda_goals(match)). Plug M77's real "
          "lambda_goals here. STOP: pick each final share together before pricing.")


# ------------------------------------------- first-half substitution base rate
# A sub before the halftime whistle is almost entirely INJURY-driven (nobody spends
# a tactical sub in the 1st half), so this is a FLAT per-match base rate -- NOT scaled
# by goals like GOAL_SHARE. Definition: period 1, minute < 45 (halftime subs made for
# the 2nd half land at >=45'/period 2 and are excluded).
def sb_first_half_subs():
    """StatsBomb 2018-22: fraction of matches with >=1 in-play first-half sub."""
    os.makedirs(SB_CACHE, exist_ok=True)
    match_ids = []
    for cid, sid in SB_COMPS:
        ms = _get(f"{SB_BASE}/matches/{cid}/{sid}.json", f"{SB_CACHE}/matches_{cid}_{sid}.json")
        match_ids += [m["match_id"] for m in ms]

    def fetch(mid):
        return _get(f"{SB_BASE}/events/{mid}.json", f"{SB_CACHE}/ev_{mid}.json")

    n = with_sub = total = ge45 = 0
    with ThreadPoolExecutor(max_workers=12) as ex:
        for evs in ex.map(fetch, match_ids):
            n += 1
            hit = False
            for ev in evs:
                if ev.get("type", {}).get("name") != "Substitution" or ev.get("period") != 1:
                    continue
                if ev.get("minute", 0) >= 45:      # de-facto halftime -> exclude
                    ge45 += 1
                    continue
                total += 1
                hit = True
            if hit:
                with_sub += 1
    return {"src": "SB 2018-22", "n_matches": n, "with_sub": with_sub,
            "frac": with_sub / n, "total": total, "ge45_excluded": ge45}


def espn_first_half_subs():
    """ESPN 2026: fraction of matches with >=1 in-play first-half sub."""
    ids = espn_event_ids()

    def fetch(eid):
        return _get(f"{ESPN}/summary?event={eid}", f"{ESPN_CACHE}/sum_{eid}.json")

    n = with_sub = total = ge45 = 0
    with ThreadPoolExecutor(max_workers=12) as ex:
        for j in ex.map(fetch, list(ids)):
            n += 1
            hit = False
            for ev in j.get("keyEvents", []):
                if (ev.get("type", {}) or {}).get("text") != "Substitution":
                    continue
                if (ev.get("period") or {}).get("number") != 1:
                    continue
                clk = (ev.get("clock") or {}).get("value")
                if clk is not None and int(clk / 60) >= 45:
                    ge45 += 1
                    continue
                total += 1
                hit = True
            if hit:
                with_sub += 1
    return {"src": "ESPN 2026", "n_matches": n, "with_sub": with_sub,
            "frac": with_sub / n if n else 0.0, "total": total, "ge45_excluded": ge45}


def subs():
    """Stage-B deliverable: in-play first-half sub base rate, both sources side by
    side. FLAT per-match rate (injury-driven, NOT goal-scaled). STOP, pick jointly."""
    print("StatsBomb 2018-22 (cached)...")
    sb = sb_first_half_subs()
    print(f"  {sb['with_sub']}/{sb['n_matches']} matches with an in-play 1H sub "
          f"-> {100*sb['frac']:.1f}%   ({sb['total']} subs; {sb['ge45_excluded']} at >=45' excluded)")
    print("ESPN 2026 (cached)...")
    e = espn_first_half_subs()
    print(f"  {e['with_sub']}/{e['n_matches']} matches with an in-play 1H sub "
          f"-> {100*e['frac']:.1f}%   ({e['total']} subs; {e['ge45_excluded']} at >=45' excluded)")
    pooled = (sb["with_sub"] + e["with_sub"]) / (sb["n_matches"] + e["n_matches"])
    lean26 = 0.65 * e["frac"] + 0.35 * sb["frac"]
    print("\nDECISION TABLE (FLAT per-match rate -- injury-driven, NOT goal-scaled)")
    print(f"  SB 2018-22 {100*sb['frac']:.1f}% (n={sb['n_matches']}) | "
          f"2026 {100*e['frac']:.1f}% (n={e['n_matches']}) | "
          f"pooled {100*pooled:.1f}% | lean-2026 {100*lean26:.1f}%")
    print("  P(>=1 in-play first-half sub) = the chosen flat rate (no lambda scaling). "
          "STOP: pick the final rate together.")


# ---------------------------------------------------- predictions.csv half backtest
def classify_prop(prop):
    """Map a prop's wording to an EVENT_CURVE event type (best-effort, for backtest)."""
    p = prop.lower()
    if "penalt" in p:
        return "penalties"
    if "on target" in p or "sot" in p:
        return "sot"
    if "corner" in p:
        return "corners"
    if "card" in p or "booking" in p or "yellow" in p or " red " in p:
        return "cards"
    if "offside" in p:
        return "offsides"
    if "foul" in p:
        return "fouls"
    if "shot" in p:
        return "shots"
    if "goal" in p or "score" in p or "nil" in p or "lead" in p:
        return "goals"
    return None


def half_backtest():
    """Aggregate half-scoped predictions by inferred event type. Returns list of dicts."""
    rows = list(csv.DictReader(open(PRED_CSV)))
    hs = [r for r in rows if r.get("is_half_scoped") == "true"]
    agg = {}
    for r in hs:
        ev = classify_prop(r["prop"])
        if ev is None:
            continue
        a = agg.setdefault(ev, {"n": 0, "you": 0.0, "out": 0.0, "crowd": 0.0,
                                "rbp_p": 0.0, "rbp_d": 0.0})
        a["n"] += 1
        a["you"] += float(r["you_pct"])
        a["out"] += float(r["outcome"]) * 100
        a["crowd"] += float(r["crowd_pct"])
        a["rbp_p"] += float(r["rbp_platform"])
        a["rbp_d"] += float(r["rbp_docformula"])
    out = []
    for ev, a in agg.items():
        n = a["n"]
        out.append({"event": ev, "n": n, "you": a["you"] / n, "out": a["out"] / n,
                    "crowd": a["crowd"] / n, "rbp_p": a["rbp_p"] / n, "rbp_d": a["rbp_d"] / n})
    out.sort(key=lambda x: -x["n"])
    return out


# ------------------------------------------------------------------------- output
def cdf(counts):
    """(n, [q1..q4 share], F(23), F(45), F(68)) from a 4-quarter count list; None if n=0."""
    n = sum(counts)
    if n == 0:
        return None
    q = [c / n for c in counts]
    return n, q, q[0], q[0] + q[1], q[0] + q[1] + q[2]


def main(argv=()):
    if argv and argv[0] == "rare":
        rare()
        return
    if argv and argv[0] == "subs":
        subs()
        return
    print("StatsBomb 2018-22 (cached)...")
    sb, sb_n = sb_counts()
    print(f"  parsed {sb_n} matches")
    print("ESPN 2026 (cached; today/future re-fetched)...")
    esp, esp_n, ids = espn_counts()
    print(f"  parsed {esp_n} completed matches")

    print("\nspot-check 760447 (Netherlands 5-1 Sweden) goals:")
    for per, mn, q, txt in espn_spotcheck():
        print(f"  P{per} {mn:>2}'  Q{(q or 0)+1}  {txt}")

    bt = half_backtest()

    L = []
    L.append("# EVENT_CURVE calibration — 3-way comparison (prior / 2018-22 / 2026)")
    L.append("")
    L.append(f"*Auto-generated by `calibrate_curve.py` on {date.today().isoformat()} — "
             "do not hand-edit; rerun the script.*")
    L.append("")
    L.append("Cumulative share of full-match events by minute, F(t). Quarters from the "
             "mandatory hydration breaks: **Q1 0–23' · Q2 23–45'(+1H stop) · Q3 45–68' · "
             "Q4 68–90'(+2H stop)**; ET/shootout excluded. F(45) is the 1H share.")
    L.append("")
    L.append("Sources: **prior** = HALF_SHARE (domain, lambda_reference.md — only fixes "
             "F(45)); **2018-22** = StatsBomb event JSON (per-second, exact); **2026** = "
             "ESPN keyEvents (minutes for goals/cards/penalties only — "
             f"corners/offsides/fouls/shots/SOT are boxscore totals). 2026 n = {esp_n} matches.")
    L.append("")

    # ---- Table 1: 1H/2H split, the clean 3-way ----
    L.append("## 1. First-half share F(45) — three sources")
    L.append("")
    L.append("| event | prior 1H | 2018-22 1H (n) | 2026 1H (n) | spread |")
    L.append("|-------|---------:|---------------:|------------:|:------:|")
    for e in P.EVENT_CURVE:
        prior1h = P.HALF_SHARE[e][0]
        s = cdf(sb[e])
        sb_cell = f"{s[3]:.3f} ({s[0]})" if s else "—"
        if e in ESPN_TIMED:
            c = cdf(esp[e])
            esp_cell = f"{c[3]:.3f} ({c[0]})" if c else "— (0)"
            esp1h = c[3] if c else None
        else:
            esp_cell = "n/a — aggregates"
            esp1h = None
        vals = [prior1h] + ([s[3]] if s else []) + ([esp1h] if esp1h is not None else [])
        spread = max(vals) - min(vals)
        flag = " ⚠️" if spread > 0.02 else ""
        L.append(f"| {e} | {prior1h:.2f} | {sb_cell} | {esp_cell} | {spread:.3f}{flag} |")
    L.append("")

    # ---- Table 2: quarter nodes F(23)/F(68) ----
    L.append("## 2. Quarter nodes F(23') / F(68') — the genuinely new granularity")
    L.append("")
    L.append("Prior is **1H/2H only** (no 23/68 split) except goals, which has within-half "
             "anchors (0–15'≈0.11, 76–90'≈0.23) — shown as context, not a hard node.")
    L.append("")
    L.append("| event | 2018-22 F(23) | 2018-22 F(68) | 2026 F(23) | 2026 F(68) | 2026 n | current EVENT_CURVE F(23)/F(68) |")
    L.append("|-------|-------------:|-------------:|----------:|----------:|------:|:-------------------------------:|")
    for e in P.EVENT_CURVE:
        s = cdf(sb[e])
        sb23 = f"{s[2]:.3f}" if s else "—"
        sb68 = f"{s[4]:.3f}" if s else "—"
        if e in ESPN_TIMED:
            c = cdf(esp[e])
            esp23 = f"{c[2]:.3f}" if c else "—"
            esp68 = f"{c[4]:.3f}" if c else "—"
            espn_n = str(c[0]) if c else "0"
        else:
            esp23 = esp68 = "n/a"
            espn_n = "—"
        cur = P.EVENT_CURVE[e]
        L.append(f"| {e} | {sb23} | {sb68} | {esp23} | {esp68} | {espn_n} "
                 f"| {cur[1]:.2f}/{cur[3]:.2f} |")
    L.append("")

    # ---- Table 3: half-prop backtest ----
    L.append("## 3. Half-prop backtest (predictions.csv, is_half_scoped=true)")
    L.append("")
    L.append("Did our HALF_SHARE-based half-prop pricing actually work? mean(you) vs "
             "mean(outcome) tests calibration; RBP(plat)/RBP(doc) tests profitability.")
    L.append("")
    L.append("| inferred event | n | mean you | mean outcome | mean crowd | mean RBP(plat) | mean RBP(doc) |")
    L.append("|----------------|--:|---------:|-------------:|-----------:|---------------:|--------------:|")
    for r in bt:
        L.append(f"| {r['event']} | {r['n']} | {r['you']:.1f} | {r['out']:.1f} "
                 f"| {r['crowd']:.1f} | {r['rbp_p']:+.2f} | {r['rbp_d']:+.2f} |")
    L.append("")

    L.append("## Decisions applied (2026-06-28)")
    L.append("")
    L.append("Chosen jointly from the three sources above; live in `proppricer.EVENT_CURVE`.")
    L.append("")
    L.append("| event | F(23)/F(45)/F(68) | source of the 23/68 nodes |")
    L.append("|-------|-------------------|---------------------------|")
    L.append("| goals | 0.16 / 0.44 / 0.68 | 2018-22 (2026 confirms F45=0.44; 0.389 was the outlier) |")
    L.append("| shots | 0.21 / 0.47 / 0.69 | 2018-22 (no 2026 timing) |")
    L.append("| sot | 0.20 / 0.47 / 0.67 | 2018-22 (no 2026 timing) |")
    L.append("| corners | 0.22 / 0.45 / 0.71 | 2018-22 (no 2026 timing; 1H split matches prior) |")
    L.append("| cards | 0.14 / 0.35 / 0.60 | **blend** toward 2026 early-card signal (n=189); F45 kept 0.35 |")
    L.append("| penalties | 0.25 / 0.52 / 0.74 | **pooled** 2018-22+2026; both skew earlier than old prior; HALF_SHARE 0.45→0.52 |")
    L.append("| offsides | 0.23 / 0.50 / 0.74 | 2018-22 (no 2026 timing) |")
    L.append("| fouls | 0.23 / 0.48 / 0.71 | 2018-22 (no 2026 timing) |")
    L.append("")
    L.append("## Notes")
    L.append("")
    L.append("- F(45) in EVENT_CURVE is **pinned** to HALF_SHARE so `window 0 45` == `half 1H`. "
             "Only HALF_SHARE change made was **penalties 0.45→0.52** (both datasets agree).")
    L.append("- 2026 times **goals/cards/penalties** only (ESPN keyEvents). The other five "
             "events have no minute data for 2026 — decided from prior vs 2018-22.")
    L.append("- ⚠️ in Table 1 = the three sources disagree on the 1H split by >2 pts.")
    L.append("- The 'current EVENT_CURVE' column in Table 2 reflects the **applied** decisions.")
    L.append("")

    with open(OUT_MD, "w") as f:
        f.write("\n".join(L) + "\n")
    print(f"\nwrote {OUT_MD}")


if __name__ == "__main__":
    main(sys.argv[1:])
