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
from math import ceil, exp, lgamma, factorial

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

def auto_shade(p: float) -> float:
    """Favorite-longshot-aware de-vig factor for a ONE-SIDED 'X+' market (which
    has no opposite side to normalize against). The single-line vig is small near
    pick'em (~2%) but deep longshots are inflated much more (~12%). Linear in the
    raw implied prob between those anchors, clamped to [1.02, 1.12]. Replaces the
    old fixed 1.10 guess, which over-shaded pick'em and under-shaded longshots."""
    return max(1.02, min(1.12, 1.149 - 0.286 * p))

def fair_anytime(odds: int, shade=None) -> float:
    """One-sided market fair prob = raw implied / shade. shade=None (default) uses
    the odds-aware auto_shade; pass a float to override."""
    p = implied(odds)
    return p / (auto_shade(p) if shade is None else shade)

def one_sided_fair(odds: int) -> float:
    """Auto-shaded fair prob for a one-sided X+ line (alias of fair_anytime)."""
    return fair_anytime(odds, None)

# ------------------------------------------------------------- poisson core
def pois_pmf(k: int, lam: float) -> float:
    return exp(-lam) * lam ** k / factorial(k)

def pois_cdf(k: int, lam: float) -> float:
    return sum(pois_pmf(i, lam) for i in range(k + 1)) if k >= 0 else 0.0

def p_at_least(k: int, lam: float) -> float:
    return 1 - pois_cdf(k - 1, lam)

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

# --------------------------------------------------------------- shares etc
HALF_SHARE = {  # (first_half, second_half)
    "goals": (0.44, 0.56), "shots": (0.47, 0.53), "sot": (0.47, 0.53),
    "corners": (0.45, 0.55), "cards": (0.35, 0.65), "penalties": (0.45, 0.55),
    "offsides": (0.50, 0.50), "fouls": (0.48, 0.52),
}

PRIORS = {  # full-match lambda starting points, WC-calibrated (see lambda_reference.md)
    "goals_total": 2.65, "corners_total": 9.2, "yellow_cards": 3.5,
    "red_cards": 0.12, "offsides_total": 3.9, "offsides_team": 1.9,
    "shots_total": 23.0, "sot_total": 8.2, "penalties": 0.40, "fouls": 23.0,
}

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

    p = sub.add_parser("anytime", help="fair prob from one-sided X+ market (auto shade)")
    p.add_argument("odds", type=int)
    p.add_argument("--shade", type=float, default=None,
                   help="override the odds-aware auto shade with a fixed factor")

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
    g.add_argument("--atleast", nargs=2, type=float, metavar=("K", "P"))
    g.add_argument("--under", nargs=2, type=float, metavar=("LINE", "P"))

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
        s = auto_shade(p_raw) if a.shade is None else a.shade
        f = p_raw / s
        tag = " auto" if a.shade is None else ""
        print(f"raw {100*p_raw:.1f}% -> fair {100*f:.1f}% "
              f"(shade {s:.3f}{tag})  submit {submit(f)}")

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
            return lam_from_threshold(k, one_sided_fair(odds))

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
