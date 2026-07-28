# Prop Categories for the Crowd-Edge Model

Each category corresponds to a distinct, empirically observed crowd bias. A prop is
assigned to exactly one category. Props matching none are `uncategorized` and
carry no crowd-edge claim.

A separate boolean field, `is_half_scoped`, is recorded on every prediction
(see bottom) — half-scoping is a modifier, not a category.

> **Tagging discipline:** categories drive `crowdmodel.py`'s per-bucket
> crowd_hat, so the SAME prop wording must always get the SAME tag. A one-off audit
> found the same template scattered across 3–4 buckets (e.g. "Tied at halftime" in
> four categories, "X win" split fav_team_total/match_result), which quietly degraded
> crowd_hat — worst on `sub_scorer`, where the pooled line flipped the bet-direction
> signal. Tag by the prop's **structural family** (below), never by convenience. When
> in doubt, run the collision check before committing.

## Core categories

1. **match_result** — Props that are a **direct function of the pre-match 3-way
   moneyline**: "[team] win" / "win the match" / "win by 2+", "[team] advances",
   "regulation ends in a tie". Bias: crowd over/under-backs the favorite's *result*.
   (Knockout-era addition — pulls all win/advance/draw props out of
   fav_team_total, where they had been inconsistently split.)
2. **fav_team_total** — A named team's **scoring output** (NOT its result): "team to
   score," "[team] 2+ goals," "[team] 3+ total goals," "score in both halves,"
   "[team] score first goal (of the match / of the 2nd half)." Bias: crowd over-backs
   a strong favorite to score/run it up. Corners & SOT do NOT live here (they're
   volume counts → `totals`); wins/advances do NOT live here (→ `match_result`).
3. **fav_player** — Named-player props: player to score, **score-or-assist**, or
   record 1+/2+ shots on target. Bias: crowd overrates the famous name.
4. **and_conjunction** — "X AND Y." Bias: a conjunction is rarer than its parts;
   crowd misprices it (typically too high). *Protected:* any prop containing "and"
   stays here even if a clause looks like a team-scoring prop.
5. **or_disjunction** — True logical "X OR Y" unions. Bias: crowd underestimates the
   union. **Currently empty** — see the documented exceptions below; the props that
   *look* like disjunctions ("score or assist," "2 or fewer," "penalty or red") are
   deliberately routed elsewhere.
6. **discipline** — Cards, penalties, reds: total cards, **card races** ("more cards
   than"), "1+ card in a half," "penalty awarded," "penalty OR red card." One
   real-world driver (physicality + referee), kept in one home so it isn't scattered
   across totals/race/halves/disjunction.
7. **totals** — Neutral **volume counts**, team OR match, not tied to a named player
   or to discipline: match goals (3+ total goals), corners (team or match), shots on
   target (team or match), "any player 2+," timing props ("goal before 1st hydration
   break"). Bias: crowd under-rates absolute volume. Single-team corner/SOT counts
   belong HERE, not in fav_team_total — the bias is volume, not favorite-backing.
8. **race** — Team A vs Team B (or period vs period) comparisons: "more corners / SOT
   / goals than the opponent," "2nd half more goals than 1st." Bias: crowd over-rates
   the underdog side. *Card races go to `discipline`.*
9. **offsides** — Offside props (team caught offside N+, "either team offside before
   the hydration break," total offsides). Bias: crowd has no tactical read and
   clusters near 50%; the edge lives at the extremes. (Offside *races* stay here, not
   in `race` — offsides ranks above race.)

## Knockout-era categories

10. **ht_lead** — Halftime **state**: "Tied at halftime" (symmetric) and "[team]
    ahead at halftime" (path). n=26; kept SEPARATE from match_result (a symmetric
    40-47 prop would muddy an ML-outcome slope; folding it in was a CV wash).
11. **sub_scorer** — "A substitute scores." Bias: crowd chronically UNDER-prices it
    — the raw line sits ~32 flat regardless of the model's number (the crowd sits
    *below* the model, so pricing above it is +EV). ⚠️ At small n the model shrinks
    crowd_hat toward global (~40); **trust the ~30-33 anchor, do NOT trim to
    crowd_hat**. The `card` tool prints this flag.

**Do NOT mint thin categories for rare new prop types.** With few games left, a
one-off type (penalty shootout, "hold a lead at any point / ever_leads", etc.) can
never reach n≥~8, so a standalone bucket is 91% shrunk to global + 9% noise — i.e.
strictly no better (slightly worse) than just leaving it `uncategorized`. Instead
**fold a rare type into the nearest well-populated bucket** when one fits, else tag
`uncategorized`. Examples: "any player 2+" (a brace) → `fav_player` (it's a
player-scoring prop; the crowd over-prices scoring longshots the same way, named or
not); "decided by penalty shootout" → `uncategorized`; a future `ever_leads` →
`uncategorized` (or `match_result` if it prices like a result). **uncategorized** —
genuine leftovers only, rides ~global.

## Documented routing exceptions (do NOT "fix" these)
These contradict a naive keyword match on purpose — the crowd *mechanism* wins over
the surface syntax:
- **"[player] score or assist" → fav_player**, not or_disjunction. It's the
  famous-name bias, not a generic union bias.
- **"2 or fewer total goals" → totals**, not or_disjunction. "or fewer" is a
  threshold (≤2), not a logical OR.
- **"penalty OR red card" → discipline**, not or_disjunction. Discipline mechanism
  is more specific.
- **"more cards than [team]" → discipline**, not race. Card races live in discipline.
- **single-team corners/SOT counts → totals**, not fav_team_total. Volume bias.

## Priority order (first match wins)

When a prop matches more than one category, assign it to the highest-priority match
(the more specific crowd mechanism ranks higher):

    discipline -> and_conjunction -> or_disjunction -> fav_player -> sub_scorer
      -> offsides -> race -> ht_lead -> match_result -> fav_team_total -> totals
      -> shootout -> uncategorized

Deliberate judgment calls baked in: discipline above and/or (so "penalty OR red" and
"cards AND ..." land in discipline); offsides above race (offside races → offsides);
match_result above fav_team_total (a team WIN is a result, not a scoring total);
fav_team_total above totals but corners/SOT are defined into totals so no conflict.

## The `is_half_scoped` flag

The real half-related bias is not "is this a half prop" but "did the crowd fail to
halve the full-match number" (crowd 50 vs a model 22 on a half-scoped SOT prop). That
rides on top of player/race/totals props rather than forming a category. So a boolean
`is_half_scoped` is recorded on every prediction, letting the halving bias be measured
*within* each category without fragmenting the buckets.

## Small-sample note
Thin buckets (sub_scorer, shootout, match_result early on) lean on empirical-Bayes
shrinkage toward the global line (k=10 props); treat their per-category means as
provisional until the tournament fills them in. `crowdmodel.py card` prints per-bucket
cMAE and flags weak/known-biased buckets inline.
