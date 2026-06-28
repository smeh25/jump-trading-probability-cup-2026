#!/usr/bin/env python3
"""Smoke + unit tests for proppricer — focus on the knockout/time-window models
(window, reg-et, subgoal, brace, ET helpers) and the EVENT_CURVE invariants.

    python3 test_proppricer.py        # runs all; nonzero exit on first failure

No external deps; pure asserts so it works without pytest. Run after any edit to
EVENT_CURVE / HALF_SHARE or the windowed-pricing code.
"""
import subprocess, sys
import proppricer as P

TOL = 1e-9
results = []


def check(name, cond):
    results.append((name, bool(cond)))
    print(f"  {'PASS' if cond else 'FAIL'}  {name}")


def approx(a, b, tol=1e-6):
    return abs(a - b) <= tol


# ---------------------------------------------------------- EVENT_CURVE invariants
def test_curve_invariants():
    print("EVENT_CURVE / HALF_SHARE invariants")
    for e, c in P.EVENT_CURVE.items():
        check(f"{e}: F(0)=0, F(90)=1", c[0] == 0.0 and c[-1] == 1.0)
        check(f"{e}: nodes monotonic non-decreasing",
              all(c[i] <= c[i + 1] for i in range(len(c) - 1)))
        # the hard pin: F(45) node == HALF_SHARE first-half share
        check(f"{e}: F(45) pinned to HALF_SHARE", approx(c[2], P.HALF_SHARE[e][0], TOL))
        # window(0,45) reproduces half 1H; window(0,90) == 1
        check(f"{e}: window(0,45) == half 1H",
              approx(P.window_share(e, 0, 45), P.HALF_SHARE[e][0]))
        check(f"{e}: window(0,90) == 1.0", approx(P.window_share(e, 0, 90), 1.0))
    # HALF_SHARE itself must sum to 1
    for e, (h1, h2) in P.HALF_SHARE.items():
        check(f"{e}: HALF_SHARE sums to 1", approx(h1 + h2, 1.0))


def test_window_share():
    print("window_share additivity / endpoints")
    for e in P.EVENT_CURVE:
        # additive: w(0,23)+w(23,45)+w(45,68)+w(68,90) == w(0,90) == 1
        parts = (P.window_share(e, 0, 23) + P.window_share(e, 23, 45)
                 + P.window_share(e, 45, 68) + P.window_share(e, 68, 90))
        check(f"{e}: quarter windows sum to 1", approx(parts, 1.0))
        check(f"{e}: empty window = 0", approx(P.window_share(e, 30, 30), 0.0))
        check(f"{e}: window non-negative", P.window_share(e, 23, 68) >= 0)


def test_applied_decisions():
    print("Stage-C applied node values")
    check("cards = 0.14/0.35/0.60", P.EVENT_CURVE["cards"] == (0.0, 0.14, 0.35, 0.60, 1.0))
    check("penalties = 0.25/0.52/0.74",
          P.EVENT_CURVE["penalties"] == (0.0, 0.25, 0.52, 0.74, 1.0))
    check("penalties HALF_SHARE pin 0.52", approx(P.HALF_SHARE["penalties"][0], 0.52))
    check("goals unchanged 0.16/0.44/0.68",
          P.EVENT_CURVE["goals"] == (0.0, 0.16, 0.44, 0.68, 1.0))


# ------------------------------------------------------------------- ET helpers
def test_et_helpers():
    print("extra-time helpers")
    lam = 2.6
    # ET lambda is the 30' block scaled by intensity
    check("et_lambda scales 30/90 * 1.15", approx(P.et_lambda(lam), lam * (30 / 90) * 1.15))
    # p_draw=0 -> no ET -> block prob of >=1 is 0
    check("et_block_geq(1, draw=0) == 0", approx(P.et_block_geq(1, lam, 0.0), 0.0))
    # m=0 always satisfied
    check("et_block_geq(0) == 1", approx(P.et_block_geq(0, lam, 0.3), 1.0))
    # ET block prob rises with draw prob
    check("et_block_geq monotonic in draw",
          P.et_block_geq(1, lam, 0.1) < P.et_block_geq(1, lam, 0.4))
    # incl_et with draw=0 collapses to pure regulation P(>=k)
    check("incl_et_geq(draw=0) == regulation atleast",
          approx(P.incl_et_geq(1, lam, lam, 0.0), P.p_at_least(1, lam)))
    # including ET can only add probability mass
    check("incl_et_geq >= regulation",
          P.incl_et_geq(2, lam, lam, 0.3) >= P.p_at_least(2, lam) - TOL)
    # all probabilities in [0,1]
    check("incl_et_geq in [0,1]", 0.0 <= P.incl_et_geq(1, lam, lam, 0.3) <= 1.0)


# ---------------------------------------------------------------- CLI smoke pass
def run(args):
    r = subprocess.run([sys.executable, "proppricer.py"] + args,
                       capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


def test_cli_smoke():
    print("CLI smoke (exit 0 + non-empty output)")
    cmds = [
        ["window", "goals", "0", "23", "--lam", "1.4"],
        ["window", "cards", "0", "23", "--mkt", "3", "150"],
        ["window", "sot", "0", "45", "--lam", "4.0", "--vs-lam", "3.0"],
        ["window", "goals", "0", "90", "--lam", "1.4", "--atleast", "1"],
        ["window", "goals", "0", "23", "--lam", "1.4", "--incl-et", "--draw", "0.25"],
        ["reg-et", "goals", "--lam", "2.6", "--atleast", "1", "--draw", "0.25"],
        ["reg-et", "goals", "--lam", "2.6", "--atleast", "1", "--draw-odds", "150", "230", "190"],
        ["subgoal", "--lam", "2.6"],
        ["subgoal", "--lam", "2.6", "--incl-et", "--draw", "0.25"],
        ["brace", "150", "200", "350"],
        ["brace", "150", "200", "--others-lam", "1.2"],
        # a few legacy commands to ensure no regression
        ["half", "sot", "2H", "--lam", "6.8"],
        ["advance", "1.4", "1.1"],
        ["match", "1.4", "1.1"],
    ]
    for c in cmds:
        code, out = run(c)
        check(f"{' '.join(c)}", code == 0 and len(out.strip()) > 0)


def test_cli_window_matches_half():
    print("CLI cross-check: window 0 45 == half 1H (goals)")
    # window goals 0 45 share should equal HALF_SHARE goals 1H; compare via library
    check("library window(0,45) goals == HS",
          approx(P.window_share("goals", 0, 45), P.HALF_SHARE["goals"][0]))


def main():
    test_curve_invariants()
    test_window_share()
    test_applied_decisions()
    test_et_helpers()
    test_cli_smoke()
    test_cli_window_matches_half()

    n = len(results)
    fails = [name for name, ok in results if not ok]
    print(f"\n{n - len(fails)}/{n} passed")
    if fails:
        print("FAILURES:")
        for f in fails:
            print(f"  - {f}")
        sys.exit(1)
    print("all green")


if __name__ == "__main__":
    main()
