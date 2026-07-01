#!/usr/bin/env python3
"""
proppricer.py — Poisson pricing toolkit + CLI for soccer props.

CLI quick reference (all probabilities 0-1 floats, American odds as ints):
    price 160 210 200            3-way odds -> devig -> fit lams -> full match card
    price 160 210 200 --power    same, power de-vig (better longshot handling)
    match 1.4 1.1                full match card straight from team lams
    advance 1.4 1.1              knockout: win-in-90 vs advance (ET + pens)
    devig 160 210 200            de-vig only (shows proportional AND power)
    odds -150  |  odds 0.62      convert American odds <-> probability
    anytime 285                  one-sided fair prob (auto odds-aware longshot shade)
    half sot 2H --lam 6.8        half-scoped P(>=1/2/3) from a full-game lam
    half sot 2H --mkt 8 400      ...deriving the full-game lam from an 'X+ at odds' line
    half corners 1H --lam 5.6 --vs-lam 3.3   HT race: P(team more / tie / opp more)
    pois 2.2                     distribution table for a lambda
    pois 3.5 --nb 8              negative binomial (overdispersed: cards, fouls)
    atleast 2 2.2                P(X >= 2) for lambda 2.2
    lam --atleast 9 0.50         invert "9+ at 50%" -> lambda
    lam --under 2.5 0.60         invert "under 2.5 at 60%" -> lambda
    race 2.1 1.7                 P(A more / tie / B more)
    handicap 5.2 4.1 --line -1.5 P(A beats B by 2+) etc. (corners, cards)
    player 1.3 0.31 --minutes 0.9   P(player scores), P(2+)
    blend 3.5 5.2 6              shrink prior toward observed (6 matches seen)
    rbp 0.45 0.65 0.46           expected RBP for (you, crowd, truth)
    priors                       show WC-calibrated lambda priors
    demo                         original Korea-Czechia walkthrough
"""
import argparse
import sys
from math import ceil, exp, log, lgamma, factorial

# ---------------------------------------------------------------- odds utils
def implied(odds: int) -> float:
    """American odds -> raw implied probability (includes vig)."""
    return 100 / (odds + 100) if odds > 0 else -odds / (-odds + 100)

def american(p: float) -> str:
    """Probability -> fair American odds string."""
    if not 0 < p < 1:
        return "n/a"
    return f"+{round(100 * (1 - p) / p)}" if p < 0.5 else f"-{round(100 * p / (1 - p))}"

def devig(*odds: int) -> list[float]:
    """Proportional de-vig across a mutually exclusive market."""
    raw = [implied(o) for o in odds]
    s = sum(raw)
    return [r / s for r in raw]

def devig_power(*odds: int, tol=1e-10) -> list[float]:
    """Power-method de-vig: solves sum(raw_i^k)=1. Better handles
    favorite-longshot bias than proportional (shades longshots more)."""
    raw = [implied(o) for o in odds]
    lo, hi = 0.5, 3.0
    while hi - lo > tol:
        k = (lo + hi) / 2
        s = sum(r ** k for r in raw)
        lo, hi = (k, hi) if s > 1 else (lo, k)
    return [r ** k for r in raw]

# --------------------------------------------------------- one-sided vig table
# Typical TWO-WAY hold (overround) for ONE-SIDED markets where the book quotes
# only the "Yes/Over" side, so we cannot de-vig against the opposite outcome.
# fair = raw_implied / (1 + vig).  Keyed by SOURCE-MARKET type (what we price
# OFF), NOT by our prop category. Values are web-researched two-way-hold anchors
# (2026-06-23): moneyline ~5%, Yes/No props ~7% (bettingusa); player props
# major 4-6% / secondary 6-10% / exotic 10-20% (Wizard of Odds); first-GS multiway
# 20-40%, anytime two-way lower (Pinnacle). Soccer runs higher-vig than US sports
# and DK is recreational. REFINE empirically: whenever both sides (or a paired
# threshold ladder) are seen, back out the hold with `observed_vig` and nudge.
# The single source of truth lives here; see toolkit.md for the documented table.
ONE_SIDED_VIG = {
    "two_way":        0.00,  # both sides quoted -> de-vig directly; no estimate
    "team_count":     0.07,  # one-sided team threshold (SOT/corners/fouls/offsides); Yes/No 7%, observed 7.3%
    "player_sot":     0.10,  # player shots on target -- secondary prop (volume-based, more predictable)
    "anytime_scorer": 0.15,  # anytime score / score-or-assist -- juiciest; two-way below the 20-40% multiway
    "penalty":        0.07,  # "penalty awarded? yes" -- Yes/No prop
    "red_card":       0.10,  # "a red card in the match" -- Yes/No + favorite-longshot premium on the rare side
    "default":        0.08,  # unknown one-sided market -> conservative middle
}
MARKET_CHOICES = sorted(ONE_SIDED_VIG)

def one_sided_vig(market: str) -> float:
    """Two-way hold for a one-sided market type (see ONE_SIDED_VIG)."""
    return ONE_SIDED_VIG.get(market, ONE_SIDED_VIG["default"])

def observed_vig(*odds: int) -> float:
    """Realized two-way/N-way hold from quoted odds: sum(raw_implied) - 1. Use to
    back out a market's true hold whenever both sides are seen, then update the
    ONE_SIDED_VIG prior for that market type."""
    return sum(implied(o) for o in odds) - 1.0

def fair_one_sided(odds: int, market: str = "default", shade=None) -> float:
    """Fair prob from a ONE-SIDED line, de-vigged by the market-type two-way hold:
    fair = raw / (1 + vig[market]).  Pass `shade` to override the table with an
    explicit (1+vig) factor (e.g. 1.15). Replaces the old odds-only `auto_shade`,
    which assumed every one-sided line carried only ~2-12% regardless of market —
    badly under-de-vigging juiced player/scorer props."""
    p = implied(odds)
    factor = (1.0 + one_sided_vig(market)) if shade is None else shade
    return p / factor

def fair_anytime(odds: int, shade=None) -> float:
    """Back-compat: fair prob for an anytime score/score-or-assist line."""
    return fair_one_sided(odds, "anytime_scorer", shade)

def one_sided_fair(odds: int, market: str = "default") -> float:
    """Alias kept for callers that don't pass an explicit shade."""
    return fair_one_sided(odds, market)

# ------------------------------------------------------------- poisson core
def pois_pmf(k: int, lam: float) -> float:
    return exp(-lam) * lam ** k / factorial(k)

def pois_cdf(k: int, lam: float) -> float:
    return sum(pois_pmf(i, lam) for i in range(k + 1)) if k >= 0 else 0.0

def p_at_least(k: int, lam: float) -> float:
    return 1 - pois_cdf(k - 1, lam)

def p_share_of_goals(share: float, lam_goals: float) -> float:
    """P(>=1 goal of a sub-type) when that sub-type is a `share` of all goals.
    Poisson thinning: if match goals ~ Poisson(lam_goals) and each goal is
    independently of the sub-type w.p. `share`, the sub-type count is
    Poisson(share*lam_goals). Used for 'goal from outside the box' / 'own goal'
    (see GOAL_SHARE). = 1 - exp(-share*lam_goals)."""
    return p_at_least(1, share * lam_goals)

def nb_pmf(k: int, mu: float, r: float) -> float:
    """Negative binomial pmf, mean mu, dispersion r (variance = mu + mu^2/r).
    Cards/fouls are overdispersed vs Poisson; r ~ 6-10 fits card data."""
    p = r / (r + mu)
    return exp(lgamma(k + r) - lgamma(r) - lgamma(k + 1)) * p ** r * (1 - p) ** k

def nb_at_least(k: int, mu: float, r: float) -> float:
    return 1 - sum(nb_pmf(i, mu, r) for i in range(k)) if k > 0 else 1.0

def lam_from_threshold(k: int, p_at_least_k: float) -> float:
    """Invert a market: find lam s.t. P(X >= k) = p. E.g. SOT 9+ at 50%."""
    lo, hi = 1e-6, 60.0
    for _ in range(200):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if p_at_least(k, mid) < p_at_least_k else (lo, mid)
    return (lo + hi) / 2

def lam_from_under(line: float, p_under: float) -> float:
    """Find total lam from an under price, e.g. under 2.5 at 0.60 -> ~2.3."""
    k = int(line)  # under 2.5 means <= 2
    lo, hi = 1e-6, 60.0
    for _ in range(200):
        mid = (lo + hi) / 2
        lo, hi = (lo, mid) if pois_cdf(k, mid) < p_under else (mid, hi)
    return (lo + hi) / 2

# ------------------------------------------------------- two-team race math
def race(lam_a: float, lam_b: float, nmax: int = 30) -> dict:
    """P(A>B), P(tie), P(B>A) for independent Poissons."""
    p_gt = sum(pois_pmf(a, lam_a) * pois_cdf(a - 1, lam_b) for a in range(1, nmax))
    p_tie = sum(pois_pmf(a, lam_a) * pois_pmf(a, lam_b) for a in range(nmax))
    return {"a_more": p_gt, "tie": p_tie, "b_more": 1 - p_gt - p_tie}

def diff_at_least(lam_a: float, lam_b: float, t: int, nmax: int = 60) -> float:
    """P(A - B >= t) for independent Poissons (Skellam tail by summation)."""
    return sum(pois_pmf(b, lam_b) * p_at_least(b + t, lam_a) for b in range(nmax))

# ------------------------------------------------------------ scoreline grid
def grid(lam_a: float, lam_b: float, rho: float = 0.0, nmax: int = 12):
    """Scoreline probability matrix with Dixon-Coles low-score correction.
    rho ~ -0.10 to -0.13 boosts 0-0/1-1/1-0/0-1 the way real data shows.
    Returns dict {(a,b): p} renormalized."""
    def tau(a, b):
        if a == 0 and b == 0: return 1 - lam_a * lam_b * rho
        if a == 0 and b == 1: return 1 + lam_a * rho
        if a == 1 and b == 0: return 1 + lam_b * rho
        if a == 1 and b == 1: return 1 - rho
        return 1.0
    g = {(a, b): pois_pmf(a, lam_a) * pois_pmf(b, lam_b) * tau(a, b)
         for a in range(nmax) for b in range(nmax)}
    s = sum(g.values())
    return {k: v / s for k, v in g.items()}

def market_pack(lam_a, lam_b, rho=-0.11):
    """Everything derivable from the scoreline grid in one call."""
    g = grid(lam_a, lam_b, rho)
    return {
        "win_a":   sum(p for (a, b), p in g.items() if a > b),
        "draw":    sum(p for (a, b), p in g.items() if a == b),
        "win_b":   sum(p for (a, b), p in g.items() if a < b),
        "btts":    sum(p for (a, b), p in g.items() if a >= 1 and b >= 1),
        "over15":  sum(p for (a, b), p in g.items() if a + b >= 2),
        "over25":  sum(p for (a, b), p in g.items() if a + b >= 3),
        "over35":  sum(p for (a, b), p in g.items() if a + b >= 4),
        "team_a_o05": sum(p for (a, b), p in g.items() if a >= 1),
        "team_a_o15": sum(p for (a, b), p in g.items() if a >= 2),
        "team_b_o05": sum(p for (a, b), p in g.items() if b >= 1),
        "team_b_o15": sum(p for (a, b), p in g.items() if b >= 2),
        "cs_a":    sum(p for (a, b), p in g.items() if b == 0),
        "cs_b":    sum(p for (a, b), p in g.items() if a == 0),
        "btts_and_over25": sum(p for (a, b), p in g.items()
                               if a >= 1 and b >= 1 and a + b >= 3),
        "p_00": g[(0, 0)], "p_11": g[(1, 1)],
        "_grid": g,
    }

def top_scorelines(g: dict, n: int = 8):
    cells = [(k, v) for k, v in g.items() if not isinstance(k, str)]
    return sorted(cells, key=lambda kv: -kv[1])[:n]

def fit_lams_to_market(p_win_a: float, p_draw: float, rho=-0.11):
    """Two-stage grid search for (lam_a, lam_b) matching a de-vigged 3-way."""
    def err(la, lb):
        m = market_pack(la, lb, rho)
        return (m["win_a"] - p_win_a) ** 2 + (m["draw"] - p_draw) ** 2
    best, best_err = (1.3, 1.3), 9e9
    la = 0.2
    while la <= 3.4:                       # coarse pass, step 0.05
        lb = 0.2
        while lb <= 3.4:
            e = err(la, lb)
            if e < best_err:
                best, best_err = (la, lb), e
            lb += 0.05
        la += 0.05
    ca, cb = best
    la = max(0.05, ca - 0.06)
    while la <= ca + 0.06:                 # fine pass, step 0.01
        lb = max(0.05, cb - 0.06)
        while lb <= cb + 0.06:
            e = err(la, lb)
            if e < best_err:
                best, best_err = (la, lb), e
            lb += 0.01
        la += 0.01
    return best

# ------------------------------------------------------------ knockout math
def advance_probs(lam_a, lam_b, rho=-0.11, pen_a=0.5, et_intensity=1.15):
    """Knockout 'to advance': 90' result, then 30' ET (per-minute rate slightly
    above regulation: tired legs, open games), then pens at pen_a for A.
    Returns the full breakdown so 'win in 90' vs 'advance' never gets confused."""
    m90 = market_pack(lam_a, lam_b, rho)
    et_a, et_b = lam_a * (30 / 90) * et_intensity, lam_b * (30 / 90) * et_intensity
    met = market_pack(et_a, et_b, 0.0)
    adv_a = m90["win_a"] + m90["draw"] * (met["win_a"] + met["draw"] * pen_a)
    adv_b = m90["win_b"] + m90["draw"] * (met["win_b"] + met["draw"] * (1 - pen_a))
    return {
        "win90_a": m90["win_a"], "draw90": m90["draw"], "win90_b": m90["win_b"],
        "et_win_a": m90["draw"] * met["win_a"],
        "et_win_b": m90["draw"] * met["win_b"],
        "to_pens": m90["draw"] * met["draw"],
        "advance_a": adv_a, "advance_b": adv_b,
    }

def et_lambda(lam_full: float, intensity: float = 1.15) -> float:
    """Expected event count in the 30' of extra time, IF it is reached.
    Per-minute rate slightly above regulation (tired legs, open games)."""
    return lam_full * (30 / 90) * intensity

def et_block_geq(m: int, lam_full: float, p_draw: float, intensity: float = 1.15) -> float:
    """P(>= m events occur in extra time), unconditional on reaching it.
    ET is reached with prob p_draw (the de-vigged 90' draw price); m<=0 -> 1."""
    if m <= 0:
        return 1.0
    return p_draw * p_at_least(m, et_lambda(lam_full, intensity))

def incl_et_geq(k: int, lam_reg: float, lam_full_for_et: float, p_draw: float,
                intensity: float = 1.15) -> float:
    """P(>= k of an event across a regulation piece (lam_reg) PLUS the ET block).
    lam_full_for_et is the FULL-match lam that drives the ET rate (ET is its own
    30' block, not a sub-window). Convolves the reg Poisson with the ET block."""
    tot = 0.0
    for j in range(0, 60):
        pj = pois_pmf(j, lam_reg)
        if pj < 1e-12 and j > lam_reg + 10:
            break
        tot += pj * et_block_geq(k - j, lam_full_for_et, p_draw, intensity)
    return tot

# --------------------------------------------------------------- shares etc
HALF_SHARE = {  # (first_half, second_half)
    "goals": (0.44, 0.56), "shots": (0.47, 0.53), "sot": (0.47, 0.53),
    "corners": (0.45, 0.55), "cards": (0.35, 0.65), "penalties": (0.52, 0.48),
    "offsides": (0.50, 0.50), "fouls": (0.48, 0.52),
    # penalties 1H moved 0.45->0.52: BOTH StatsBomb 2018-22 (0.52, n=50) and ESPN
    # 2026 (0.545, n=11) agree pens skew earlier than the old prior (calibrate_curve.py).
}

PRIORS = {  # full-match lambda starting points, WC-calibrated (see lambda_reference.md)
    "goals_total": 2.65, "corners_total": 9.2, "yellow_cards": 3.5,
    "red_cards": 0.12, "offsides_total": 3.9, "offsides_team": 1.9,
    "shots_total": 23.0, "sot_total": 8.2, "penalties": 0.40, "fouls": 23.0,
}

# ------------------------------------------------------ time-window intensity
# Cumulative share of full-match events by each node minute (a CDF over [0,90]).
# Generalizes HALF_SHARE (the 2-bucket version) so we can scope ANY window, e.g.
# the mandatory hydration-break quarters (breaks ~23'/68'). Window share for
# [a,b] = F(b) - F(a), piecewise-linear between nodes. HARD CONSTRAINT: the 45'
# node MUST equal HALF_SHARE[event][0] so window(0,45) reproduces half 1H (the
# old `half`/`atleast` commands stay as the cross-check). Calibrate the 23'/68'
# nodes from StatsBomb WC data (calibrate_curve.py); these are priors until then.
WINDOW_NODES = (0, 23, 45, 68, 90)
# F at (0, 23, 45, 68, 90); F(0)=0, F(45) PINNED to HALF_SHARE 1H, F(90)=1.
# Nodes set from a 3-WAY comparison (calibrate_curve.py -> calibration_output.md):
# prior (HALF_SHARE) | StatsBomb WC 2018-22 (per-second, exact) | ESPN 2026 (times
# goals/cards/pens only). DECISIONS (2026-06-28):
#   * F(45) kept = HALF_SHARE everywhere so window(0,45) == half 1H. The prior held up:
#     2026 goals 1H = 0.452 ~ prior 0.44; 2018-22's 0.389 was the lone outlier.
#   * goals/shots/sot/corners/offsides/fouls: 23/68 nodes = StatsBomb 2018-22 (no 2026
#     timing data for the non-timed five; 2018-22 1H split already matches the prior).
#   * cards: 2026 (n=189) shows real early-card inflation (F23 0.19 vs 2018-22 0.11);
#     n-weighted blend -> 0.14/0.60. F(45) stays 0.35 (prior+2018-22 agree).
#   * penalties: pooled 2018-22(n=50)+2026(n=11) -> 0.25/0.52/0.74; both agree pens
#     skew earlier than the old 0.45 prior, so HALF_SHARE["penalties"] moved to 0.52 too.
EVENT_CURVE = {
    "goals":     (0.0, 0.16, 0.44, 0.68, 1.0),  # 2018-22; 2026 confirms F45=0.44
    "shots":     (0.0, 0.21, 0.47, 0.69, 1.0),  # 2018-22 (no 2026 timing)
    "sot":       (0.0, 0.20, 0.47, 0.67, 1.0),  # 2018-22 (no 2026 timing)
    "corners":   (0.0, 0.22, 0.45, 0.71, 1.0),  # 2018-22 (no 2026 timing)
    "cards":     (0.0, 0.14, 0.35, 0.60, 1.0),  # blended toward 2026 early-card signal
    "penalties": (0.0, 0.25, 0.52, 0.74, 1.0),  # pooled data; earlier than old prior
    "offsides":  (0.0, 0.23, 0.50, 0.74, 1.0),  # 2018-22 ~flat (no 2026 timing)
    "fouls":     (0.0, 0.23, 0.48, 0.71, 1.0),  # 2018-22 ~flat (no 2026 timing)
}
SUB_GOAL_SHARE = 0.18  # fraction of goals scored by substitutes (knockouts a touch higher)

GOAL_SHARE = {  # fraction of a match's goals that are of this sub-type; price via
                # p_share_of_goals(share, lam_goals). Derived offline from cached data
                # (StatsBomb 2018-22 + ESPN 2026); regen with `calibrate_curve.py rare`.
    "outside_box": 0.12,  # goal struck outside the box.  SB 9.9% (33/334) | 2026 12.7% (29/229)
    "own_goal":    0.05,  # own goal.                      SB 4.5% (15/334) | 2026  5.2% (12/229)
}

def _curve_cdf(event: str, t: float) -> float:
    """Piecewise-linear interpolation of the cumulative event-share CDF at minute t."""
    nodes, F = WINDOW_NODES, EVENT_CURVE[event]
    if t <= nodes[0]:
        return F[0]
    if t >= nodes[-1]:
        return F[-1]
    for i in range(1, len(nodes)):
        if t <= nodes[i]:
            frac = (t - nodes[i - 1]) / (nodes[i] - nodes[i - 1])
            return F[i - 1] + frac * (F[i] - F[i - 1])
    return F[-1]

def window_share(event: str, a: float, b: float) -> float:
    """Share of full-match `event` expected in the minute window [a, b]."""
    return _curve_cdf(event, b) - _curve_cdf(event, a)

def player_score_prob(team_lam: float, share: float, minutes_factor=1.0):
    return 1 - exp(-team_lam * share * minutes_factor)

def blend(prior_lam: float, observed_lam: float, n_obs: int, k: float = 10.0):
    """Bayesian shrinkage: blend tournament-observed rate with prior.
    k = prior strength in 'equivalent matches'. After n_obs matches,
    weight on observed data = n_obs / (n_obs + k)."""
    w = n_obs / (n_obs + k)
    return w * observed_lam + (1 - w) * prior_lam

# ------------------------------------------------------------------ scoring
def brier(p: float, outcome: int) -> float:
    return (p - outcome) ** 2

def expected_rbp(p: float, crowd: float, truth: float) -> float:
    """Expected RBP if true prob is `truth`, you submit p, crowd submits crowd."""
    return ((crowd - truth) ** 2 - (p - truth) ** 2) * 100

# -------------------------------------------------------------- CLI helpers
def submit(p: float) -> int:
    """Contest submission integer, clamped to 1-99."""
    return max(1, min(99, round(100 * p)))

def row(label: str, p: float, width: int = 24) -> str:
    return f"  {label:<{width}} {100*p:6.1f}%   fair {american(p):>6}   submit {submit(p):>2}"

def print_match_card(la, lb, rho, name_a="A", name_b="B"):
    m = market_pack(la, lb, rho)
    print(f"lams: {name_a}={la:.2f}  {name_b}={lb:.2f}  (rho={rho})  "
          f"total={la+lb:.2f}")
    print("3-way:")
    print(row(f"{name_a} win", m["win_a"]))
    print(row("draw", m["draw"]))
    print(row(f"{name_b} win", m["win_b"]))
    print("double chance:")
    print(row(f"{name_a} or draw", m["win_a"] + m["draw"]))
    print(row(f"{name_a} or {name_b}", m["win_a"] + m["win_b"]))
    print(row(f"{name_b} or draw", m["win_b"] + m["draw"]))
    print("goals:")
    print(row("over 1.5", m["over15"]))
    print(row("over 2.5", m["over25"]))
    print(row("over 3.5", m["over35"]))
    print(row("BTTS", m["btts"]))
    print(row("BTTS & over 2.5", m["btts_and_over25"]))
    print(row(f"{name_a} over 0.5", m["team_a_o05"]))
    print(row(f"{name_a} over 1.5", m["team_a_o15"]))
    print(row(f"{name_b} over 0.5", m["team_b_o05"]))
    print(row(f"{name_b} over 1.5", m["team_b_o15"]))
    print(row(f"{name_a} clean sheet", m["cs_a"]))
    print(row(f"{name_b} clean sheet", m["cs_b"]))
    print("top scorelines:")
    for (a, b), p in top_scorelines(m["_grid"]):
        print(f"  {a}-{b}: {100*p:5.1f}%")

# --------------------------------------------------------------------- demo
def run_demo():
    print("== Demo: rebuild the Korea-Czechia card ==")
    pk, pd, pc = devig(160, 210, 200)
    print(f"3-way devig: K={pk:.3f} D={pd:.3f} C={pc:.3f}")
    la, lb = fit_lams_to_market(pk, pd)
    print(f"fitted lams: K={la:.2f} C={lb:.2f}")
    m = market_pack(la, lb)
    print(f"model: BTTS={m['btts']:.3f}  O2.5={m['over25']:.3f}  "
          f"BTTS&O2.5={m['btts_and_over25']:.3f}  1-1={m['p_11']:.3f}")
    lam_sot = lam_from_threshold(9, 0.50)
    print(f"SOT total lam from '9+ at 50%': {lam_sot:.2f}")
    r = race(lam_sot * 0.53 * 0.52, lam_sot * 0.53 * 0.48)
    print(f"2H SOT race: A_more={r['a_more']:.3f} tie={r['tie']:.3f}")
    lam_cards_2h = PRIORS["yellow_cards"] * HALF_SHARE["cards"][1]
    print(f"2H cards lam={lam_cards_2h:.2f} -> P(>=2)={p_at_least(2, lam_cards_2h):.3f}")
    print(f"Son anytime fair from +200: {fair_anytime(200):.3f}")

# ---------------------------------------------------------------------- CLI
def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="proppricer", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("odds", help="convert American odds <-> probability")
    p.add_argument("value", type=float, help="odds like -150/+200, or prob 0-1")

    p = sub.add_parser("devig", help="de-vig a mutually exclusive market")
    p.add_argument("odds", type=int, nargs="+")

    p = sub.add_parser("anytime", help="fair prob from one-sided market (de-vig by market type)")
    p.add_argument("odds", type=int)
    p.add_argument("--market", choices=MARKET_CHOICES, default="default",
                   help="source-market type -> two-way hold from ONE_SIDED_VIG "
                        "(e.g. anytime_scorer, player_sot, team_count)")
    p.add_argument("--shade", type=float, default=None,
                   help="override the table with an explicit (1+vig) factor, e.g. 1.15")

    p = sub.add_parser("pois", help="distribution table for a lambda")
    p.add_argument("lam", type=float)
    p.add_argument("--nb", type=float, default=None, metavar="R",
                   help="use negative binomial with dispersion R (cards: ~6-10)")

    p = sub.add_parser("atleast", help="P(X >= k)")
    p.add_argument("k", type=int)
    p.add_argument("lam", type=float)
    p.add_argument("--nb", type=float, default=None, metavar="R")

    p = sub.add_parser("lam", help="invert a market price to lambda")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--atleast", nargs=2, type=float, metavar=("K", "P"),
                   help="invert P(>=K)=P (P already a fair prob)")
    g.add_argument("--under", nargs=2, type=float, metavar=("LINE", "P"))
    g.add_argument("--atleast-odds", nargs=2, type=int, metavar=("K", "ODDS"),
                   dest="atleast_odds",
                   help="invert a one-sided 'K+ at ODDS' line, de-vigged by --market")
    g.add_argument("--under-odds", nargs=2, type=int, metavar=("LINE", "ODDS"),
                   dest="under_odds", help="invert an 'under LINE at ODDS' line")
    p.add_argument("--market", choices=MARKET_CHOICES, default="team_count",
                   help="market type for the *-odds de-vig (default team_count)")

    p = sub.add_parser("race", help="P(A more / tie / B more)")
    p.add_argument("lam_a", type=float)
    p.add_argument("lam_b", type=float)

    p = sub.add_parser("handicap", help="P(A - B beats a half-integer line)")
    p.add_argument("lam_a", type=float)
    p.add_argument("lam_b", type=float)
    p.add_argument("--line", type=float, required=True,
                   help="-1.5 = A by 2+; +1.5 = A loses by at most 1")

    p = sub.add_parser("match", help="full match card from team lams")
    p.add_argument("lam_a", type=float)
    p.add_argument("lam_b", type=float)
    p.add_argument("--rho", type=float, default=-0.11)
    p.add_argument("--names", nargs=2, default=("A", "B"))

    p = sub.add_parser("fit", help="lams from de-vigged 3-way probs")
    p.add_argument("p_win_a", type=float)
    p.add_argument("p_draw", type=float)
    p.add_argument("--rho", type=float, default=-0.11)

    p = sub.add_parser("price", help="one-shot: 3-way American odds -> match card")
    p.add_argument("odds", type=int, nargs=3, metavar=("A", "DRAW", "B"))
    p.add_argument("--power", action="store_true", help="power de-vig")
    p.add_argument("--rho", type=float, default=-0.11)
    p.add_argument("--names", nargs=2, default=("A", "B"))

    p = sub.add_parser("advance", help="knockout advance probs from lams")
    p.add_argument("lam_a", type=float)
    p.add_argument("lam_b", type=float)
    p.add_argument("--rho", type=float, default=-0.11)
    p.add_argument("--pen", type=float, default=0.5, help="P(A wins shootout)")
    p.add_argument("--names", nargs=2, default=("A", "B"))

    p = sub.add_parser("half", help="half-scoped prob/race from a full-game lam or X+ market")
    p.add_argument("event", choices=sorted(HALF_SHARE))
    p.add_argument("half", choices=["1H", "2H"])
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--lam", type=float, help="full-game lam for the team/total")
    src.add_argument("--mkt", nargs=2, type=int, metavar=("K", "ODDS"),
                     help="derive full-game lam from a one-sided X+ line: P(>=K) at ODDS")
    p.add_argument("--vs-lam", type=float, help="opponent full-game lam -> race in this half")
    p.add_argument("--vs-mkt", nargs=2, type=int, metavar=("K", "ODDS"),
                   help="opponent X+ line for the race")
    p.add_argument("--atleast", type=int,
                   help="P(half count >= this) instead of the 1/2/3 summary")
    p.add_argument("--market", choices=MARKET_CHOICES, default="team_count",
                   help="market type to de-vig --mkt/--vs-mkt lines (default team_count)")

    p = sub.add_parser("window", help="time-window prob (e.g. before/after a hydration break) "
                       "from a full-game lam or X+ market")
    p.add_argument("event", choices=sorted(EVENT_CURVE))
    p.add_argument("a", type=float, help="window start minute (e.g. 0)")
    p.add_argument("b", type=float, help="window end minute (e.g. 23 = before 1st hydration break)")
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--lam", type=float, help="full-game lam for the team/total")
    src.add_argument("--mkt", nargs=2, type=int, metavar=("K", "ODDS"),
                     help="derive full-game lam from a one-sided K+ at ODDS line")
    p.add_argument("--vs-lam", type=float, help="opponent full-game lam -> windowed race")
    p.add_argument("--vs-mkt", nargs=2, type=int, metavar=("K", "ODDS"))
    p.add_argument("--atleast", type=int, help="P(window count >= this) instead of 1/2/3")
    p.add_argument("--market", choices=MARKET_CHOICES, default="team_count")
    p.add_argument("--incl-et", action="store_true", dest="incl_et",
                   help="add an extra-time tail (needs --draw/--draw-odds)")
    et = p.add_mutually_exclusive_group()
    et.add_argument("--draw", type=float, help="de-vigged 90' draw prob = P(reach ET)")
    et.add_argument("--draw-odds", nargs=3, type=int, metavar=("A", "DRAW", "B"), dest="draw_odds")

    p = sub.add_parser("reg-et", help="P(>=k) in regulation vs including extra time")
    p.add_argument("event", choices=sorted(EVENT_CURVE))
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--lam", type=float, help="full-game (90') lam")
    src.add_argument("--mkt", nargs=2, type=int, metavar=("K", "ODDS"))
    p.add_argument("--atleast", type=int, default=1, dest="k", help="threshold k (default 1)")
    p.add_argument("--market", choices=MARKET_CHOICES, default="team_count")
    et = p.add_mutually_exclusive_group(required=True)
    et.add_argument("--draw", type=float, help="de-vigged 90' draw prob = P(reach ET)")
    et.add_argument("--draw-odds", nargs=3, type=int, metavar=("A", "DRAW", "B"), dest="draw_odds")

    p = sub.add_parser("subgoal", help="P(a substitute scores) from total-goals lam")
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--lam", type=float, help="total-goals lam")
    src.add_argument("--mkt", nargs=2, type=int, metavar=("K", "ODDS"))
    p.add_argument("--share", type=float, default=SUB_GOAL_SHARE, help="sub share of goals")
    p.add_argument("--market", choices=MARKET_CHOICES, default="team_count")
    p.add_argument("--incl-et", action="store_true", dest="incl_et")
    et = p.add_mutually_exclusive_group()
    et.add_argument("--draw", type=float)
    et.add_argument("--draw-odds", nargs=3, type=int, metavar=("A", "DRAW", "B"), dest="draw_odds")

    p = sub.add_parser("brace", help="P(any player scores 2+) from anytime-scorer odds")
    p.add_argument("odds", type=int, nargs="+",
                   help="anytime-goalscorer American odds, one per listed player")
    p.add_argument("--others-lam", type=float, default=None, dest="others_lam",
                   help="aggregate goal lam for one extra 'field' player (optional)")

    p = sub.add_parser("player", help="P(player scores) from team lam x share")
    p.add_argument("team_lam", type=float)
    p.add_argument("share", type=float)
    p.add_argument("--minutes", type=float, default=1.0)

    p = sub.add_parser("blend", help="shrink prior toward observed rate")
    p.add_argument("prior", type=float)
    p.add_argument("observed", type=float)
    p.add_argument("n_obs", type=int)
    p.add_argument("--k", type=float, default=10.0)

    p = sub.add_parser("rbp", help="expected RBP for (you, crowd, truth)")
    p.add_argument("you", type=float)
    p.add_argument("crowd", type=float)
    p.add_argument("truth", type=float)

    p = sub.add_parser("share", help="P(>=1 sub-type goal) from its share of goals x game lam")
    p.add_argument("share", help="GOAL_SHARE key (outside_box/own_goal) or a raw fraction")
    p.add_argument("lam_goals", type=float, help="total-goals lam for this match")

    sub.add_parser("priors", help="show WC-calibrated lambda priors")
    sub.add_parser("demo", help="original walkthrough demo")

    a = ap.parse_args(argv)

    if a.cmd == "odds":
        if 0 < a.value < 1:
            print(f"prob {a.value:.3f} -> fair odds {american(a.value)}  "
                  f"submit {submit(a.value)}")
        else:
            pr = implied(int(a.value))
            print(f"odds {int(a.value):+d} -> implied {100*pr:.1f}% (raw, incl. vig)")

    elif a.cmd == "devig":
        prop = devig(*a.odds)
        powr = devig_power(*a.odds)
        overround = sum(implied(o) for o in a.odds)
        print(f"overround: {100*(overround-1):.1f}%")
        print(f"{'odds':>8} {'raw':>7} {'prop':>7} {'power':>7}  fair(prop)  submit")
        for o, pp, pw in zip(a.odds, prop, powr):
            print(f"{o:>+8d} {100*implied(o):6.1f}% {100*pp:6.1f}% {100*pw:6.1f}%  "
                  f"{american(pp):>10}  {submit(pp):>6}")

    elif a.cmd == "anytime":
        p_raw = implied(a.odds)
        f = fair_one_sided(a.odds, a.market, a.shade)
        if a.shade is None:
            tag = f"{a.market} vig {100*one_sided_vig(a.market):.0f}%"
        else:
            tag = f"shade {a.shade:.3f}"
        print(f"raw {100*p_raw:.1f}% -> fair {100*f:.1f}% "
              f"({tag})  submit {submit(f)}")

    elif a.cmd == "pois":
        pmf = (lambda k: nb_pmf(k, a.lam, a.nb)) if a.nb else \
              (lambda k: pois_pmf(k, a.lam))
        label = f"NegBin(mu={a.lam}, r={a.nb})" if a.nb else f"Poisson({a.lam})"
        print(f"{label}:")
        print(f"  {'k':>2} {'P(=k)':>8} {'P(<=k)':>8} {'P(>=k)':>8}")
        cum = 0.0
        for k in range(0, 15):
            pk = pmf(k)
            print(f"  {k:>2} {100*pk:7.1f}% {100*(cum+pk):7.1f}% {100*(1-cum):7.1f}%")
            cum += pk
            if cum > 0.999:
                break

    elif a.cmd == "atleast":
        pr = nb_at_least(a.k, a.lam, a.nb) if a.nb else p_at_least(a.k, a.lam)
        tag = f" (NegBin r={a.nb})" if a.nb else ""
        print(f"P(X >= {a.k} | lam={a.lam}){tag} = {100*pr:.1f}%  "
              f"fair {american(pr)}  submit {submit(pr)}")

    elif a.cmd == "lam":
        if a.atleast:
            k, pr = a.atleast
            lam = lam_from_threshold(int(k), pr)
            print(f"P(X >= {int(k)}) = {pr} -> lam = {lam:.2f}")
        elif a.atleast_odds:
            k, odds = a.atleast_odds
            pr = fair_one_sided(odds, a.market)
            lam = lam_from_threshold(k, pr)
            print(f"P(X >= {k}) = {100*pr:.1f}% (de-vig {a.market} "
                  f"{100*one_sided_vig(a.market):.0f}%, raw {100*implied(odds):.1f}%) "
                  f"-> lam = {lam:.2f}")
        elif a.under_odds:
            line, odds = a.under_odds
            pr = fair_one_sided(odds, a.market)
            lam = lam_from_under(line, pr)
            print(f"P(under {line}) = {100*pr:.1f}% (de-vig {a.market} "
                  f"{100*one_sided_vig(a.market):.0f}%) -> lam = {lam:.2f}")
        else:
            line, pr = a.under
            lam = lam_from_under(line, pr)
            print(f"P(under {line}) = {pr} -> lam = {lam:.2f}")

    elif a.cmd == "race":
        r = race(a.lam_a, a.lam_b)
        print(f"lams A={a.lam_a} B={a.lam_b}")
        print(row("A more", r["a_more"]))
        print(row("tie", r["tie"]))
        print(row("B more", r["b_more"]))
        print(row("A more or tie", r["a_more"] + r["tie"]))

    elif a.cmd == "handicap":
        if a.line == int(a.line):
            sys.exit("use a half-integer line (e.g. -1.5, +0.5) — no pushes")
        # betting convention: A -1.5 covers iff A - 1.5 > B, i.e. A - B >= ceil(-line)
        t = ceil(-a.line)
        pr = diff_at_least(a.lam_a, a.lam_b, t)
        print(f"A {a.line:+g} covers iff A - B >= {t}, "
              f"with lams A={a.lam_a} B={a.lam_b}:")
        print(row(f"A {a.line:+g} covers", pr))

    elif a.cmd == "match":
        print_match_card(a.lam_a, a.lam_b, a.rho, *a.names)

    elif a.cmd == "fit":
        la, lb = fit_lams_to_market(a.p_win_a, a.p_draw, a.rho)
        print_match_card(la, lb, a.rho)

    elif a.cmd == "price":
        oa, od, ob = a.odds
        probs = devig_power(oa, od, ob) if a.power else devig(oa, od, ob)
        method = "power" if a.power else "proportional"
        overround = sum(implied(o) for o in a.odds)
        print(f"de-vig ({method}), overround {100*(overround-1):.1f}%: "
              f"{a.names[0]} {100*probs[0]:.1f}%  draw {100*probs[1]:.1f}%  "
              f"{a.names[1]} {100*probs[2]:.1f}%")
        la, lb = fit_lams_to_market(probs[0], probs[1], a.rho)
        print_match_card(la, lb, a.rho, *a.names)

    elif a.cmd == "advance":
        r = advance_probs(a.lam_a, a.lam_b, a.rho, a.pen)
        na, nb_ = a.names
        print(f"lams {na}={a.lam_a} {nb_}={a.lam_b}, P({na} wins pens)={a.pen}")
        print(row(f"{na} wins in 90", r["win90_a"]))
        print(row("draw in 90", r["draw90"]))
        print(row(f"{nb_} wins in 90", r["win90_b"]))
        print(row(f"{na} wins in ET", r["et_win_a"]))
        print(row(f"{nb_} wins in ET", r["et_win_b"]))
        print(row("goes to pens", r["to_pens"]))
        print(row(f"{na} ADVANCES", r["advance_a"]))
        print(row(f"{nb_} ADVANCES", r["advance_b"]))

    elif a.cmd == "half":
        share = HALF_SHARE[a.event][0 if a.half == "1H" else 1]

        def _full_lam(lam, mkt):
            if lam is not None:
                return lam
            k, odds = mkt
            return lam_from_threshold(k, one_sided_fair(odds, a.market))

        la = _full_lam(a.lam, a.mkt) * share
        print(f"{a.half} {a.event}: half lam = {la:.2f}  (share {share:.2f})")
        if a.vs_lam is not None or a.vs_mkt is not None:
            lb = _full_lam(a.vs_lam, a.vs_mkt) * share
            r = race(la, lb)
            print(f"  opp half lam = {lb:.2f}")
            print(row("team more", r["a_more"]))
            print(row("tie", r["tie"]))
            print(row("opp more", r["b_more"]))
            print(row("team more or tie", r["a_more"] + r["tie"]))
        elif a.atleast is not None:
            print(row(f"P(>= {a.atleast})", p_at_least(a.atleast, la)))
        else:
            for k in (1, 2, 3):
                print(row(f"P(>= {k})", p_at_least(k, la)))

    elif a.cmd == "window":
        def _fl(lam, mkt):
            if lam is not None:
                return lam
            k, odds = mkt
            return lam_from_threshold(k, one_sided_fair(odds, a.market))
        share = window_share(a.event, a.a, a.b)
        lam_full = _fl(a.lam, a.mkt)
        lw = lam_full * share
        print(f"{a.event} window [{a.a:g},{a.b:g}]': share {share:.3f}  "
              f"lam_window = {lw:.3f}  (full lam {lam_full:.2f})")
        if a.vs_lam is not None or a.vs_mkt is not None:
            lb = _fl(a.vs_lam, a.vs_mkt) * share
            r = race(lw, lb)
            print(f"  opp lam_window = {lb:.3f}")
            print(row("team more", r["a_more"]))
            print(row("tie", r["tie"]))
            print(row("opp more", r["b_more"]))
            print(row("team more or tie", r["a_more"] + r["tie"]))
        elif a.incl_et:
            if a.draw is None and a.draw_odds is None:
                ap.error("--incl-et needs --draw or --draw-odds")
            p_draw = a.draw if a.draw is not None else devig(*a.draw_odds)[1]
            k = a.atleast or 1
            print(row(f"P(>= {k}) regulation only", p_at_least(k, lw)))
            print(f"  ET tail: p_draw {p_draw:.2f}, ET lam {et_lambda(lam_full):.2f}")
            print(row(f"P(>= {k}) incl ET", incl_et_geq(k, lw, lam_full, p_draw)))
        elif a.atleast is not None:
            print(row(f"P(>= {a.atleast})", p_at_least(a.atleast, lw)))
        else:
            for k in (1, 2, 3):
                print(row(f"P(>= {k})", p_at_least(k, lw)))

    elif a.cmd == "reg-et":
        def _fl(lam, mkt):
            if lam is not None:
                return lam
            k, odds = mkt
            return lam_from_threshold(k, one_sided_fair(odds, a.market))
        lam_full = _fl(a.lam, a.mkt)
        p_draw = a.draw if a.draw is not None else devig(*a.draw_odds)[1]
        p_reg = p_at_least(a.k, lam_full)
        p_incl = incl_et_geq(a.k, lam_full, lam_full, p_draw)
        print(f"{a.event}: full lam {lam_full:.2f}, p_draw {p_draw:.2f}, "
              f"ET lam {et_lambda(lam_full):.2f}")
        print(row(f"P(>= {a.k}) regulation", p_reg))
        print(row(f"P(>= {a.k}) incl ET", p_incl))
        print(f"  delta = {100*(p_incl - p_reg):+.1f}")

    elif a.cmd == "subgoal":
        def _fl(lam, mkt):
            if lam is not None:
                return lam
            k, odds = mkt
            return lam_from_threshold(k, one_sided_fair(odds, a.market))
        lam_tot = _fl(a.lam, a.mkt)
        lam_sub = lam_tot * a.share
        print(f"sub-goal lam = {lam_tot:.2f} x {a.share:.2f} = {lam_sub:.3f}")
        print(row("sub scores (1+) reg", 1 - exp(-lam_sub)))
        if a.incl_et:
            if a.draw is None and a.draw_odds is None:
                ap.error("--incl-et needs --draw or --draw-odds")
            p_draw = a.draw if a.draw is not None else devig(*a.draw_odds)[1]
            print(row("sub scores (1+) incl ET", incl_et_geq(1, lam_sub, lam_sub, p_draw)))

    elif a.cmd == "brace":
        ps = []
        for o in a.odds:
            p = one_sided_fair(o, "anytime_scorer")
            lp = -log(1 - p)
            p2 = p_at_least(2, lp)
            ps.append(p2)
            print(f"  odds {o:+d} -> anytime {100*p:4.1f}%  lam {lp:.2f}  P(2+) {100*p2:4.1f}%")
        none = 1.0
        for p2 in ps:
            none *= (1 - p2)
        if a.others_lam is not None:
            none *= (1 - p_at_least(2, a.others_lam))
        print(row("any listed player 2+", 1 - none))

    elif a.cmd == "player":
        m = a.team_lam * a.share * a.minutes
        print(f"player lam = {a.team_lam} x {a.share} x {a.minutes} = {m:.3f}")
        print(row("scores (1+)", 1 - exp(-m)))
        print(row("scores 2+", 1 - exp(-m) * (1 + m)))

    elif a.cmd == "blend":
        out = blend(a.prior, a.observed, a.n_obs, a.k)
        w = a.n_obs / (a.n_obs + a.k)
        print(f"blend: {100*w:.0f}% observed ({a.observed}) + "
              f"{100*(1-w):.0f}% prior ({a.prior}) = {out:.2f}")

    elif a.cmd == "rbp":
        print(f"E[RBP] = {expected_rbp(a.you, a.crowd, a.truth):+.2f} "
              f"(you {a.you}, crowd {a.crowd}, truth {a.truth})")

    elif a.cmd == "share":
        if a.share in GOAL_SHARE:
            s, tag = GOAL_SHARE[a.share], f"{a.share} share {GOAL_SHARE[a.share]:.3f}"
        else:
            s, tag = float(a.share), f"share {float(a.share):.3f}"
        pr = p_share_of_goals(s, a.lam_goals)
        print(f"P(>=1 | {tag}, lam_goals={a.lam_goals}) = {100*pr:.1f}%  "
              f"fair {american(pr)}  submit {submit(pr)}")

    elif a.cmd == "priors":
        for k, v in PRIORS.items():
            print(f"  {k:<16} {v}")
        print("halves (1H/2H):")
        for k, (s1, s2) in HALF_SHARE.items():
            print(f"  {k:<16} {s1:.2f}/{s2:.2f}")

    elif a.cmd == "demo":
        run_demo()

if __name__ == "__main__":
    main()
