# Soccer Poisson Parameter Reference (λ priors)

Base rates per 90 minutes unless noted. Hierarchy: market-implied λ > tournament-
observed λ > these priors. These are STARTING points — always override with a
market read when one exists.

2026-specific context (verified June 2026): 48 teams / 104 matches; market total
prices ~2.69 goals/match (same as Qatar 2022's 172/64). Heat + 3-min drinks
breaks per half may suppress late tempo; many mismatch fixtures cut both ways
(blowouts up, but parked buses too). New rule: covering an opponent's mouth in
a confrontation = straight red.

## Calibration corrections (n=1019 audit)

Fair value IS the base rate — these fix where fair drifted off it; do not shade past. Calibrated
buckets (goals **totals** −0.9, **match_result** +0.7) are left alone — extremity there is pure −EV.

| Bucket | n | Priced | Realized | Fix |
|---|---|---|---|---|
| **discipline (cards)** | 125 | 40.6 | **28.8** | Press card TOTALS to ~22–29 (anchor to market), keep RACES pushed UP. Biggest leak. |
| **fav_team_total** | 121 | 54.5 | **61.2** | Favorite's OWN scoring/volume totals UNDER-priced — recalibrate UP. NOT the both-teams JOINT (that still fades). |

Minor hot buckets, small downward trims: offsides 51→45, ht_lead 43→38, fav_player 35→30, race 47→43.
Guardrail: on props priced opposite the crowd across 50, the correct side is picked only **50% (49/98)** — edge is
calibration + magnitude on the correct side, not bold cross-crowd bets. Fix miscalibration, never force extremity.

## Match-level event rates

| Event | λ (full match) | Notes / source basis |
|---|---|---|
| Goals (total) | 2.5–2.7 | WC 2022: 2.69. Calibrate to O/U 2.5 price when available |
| Goals (per team) | 1.25–1.35 each | Split via moneyline; favorite share via scoreline odds |
| Corners (total) | 8.5–9.5 (WC); 9.5–10.5 (club) | WC 2022: 8.6/90 (Opta) – 8.9 incl. all corners. Club leagues run a corner higher |
| Corners (per team) | ~λ_total × possession-ish share | Dominant team gets 55–65% |
| Yellow cards | 3.3–4.2 | WC 2022: 3.34 (= 214 PLAYER yellows/64; totals incl. bench/staff run higher — settlement!); club leagues 4.0–4.8; 2026 WC: re-derive after ~10 matches |
| Red cards | 0.10–0.20 | WC 2018 & 2022: 4/64 = 0.06 each, but 2014 was 0.16. 2026 opener had 3 reds + new auto-red rule (mouth-covering in confrontations) → don't anchor below ~0.10. P(any red) ≈ 10–18% at this λ |
| Offsides (total) | 3.5–4.0 | WC 2022: 255/64 = 4.0. Semi-automated era catches marginal calls |
| Offsides (per team) | 1.5–2.0 | Runners-in-behind teams +20%; deep-block opponents −25% |
| Shots (total) | 22–24 (WC); 24–26 (club) | WC 2022: ~22/game, lowest on record — WCs are cagier than club play |
| Shots on target (total) | 7.5–8.5 (WC); 8–9 (club) | WC 2022: just under 8. Calibrate to SOT line when quoted |
| Penalties awarded | 0.35–0.45 | VAR-era WC (2018: 0.45, 2022: ~0.36). Club ~0.28 |
| Fouls (total) | 21–25 | Driver of cards; physical matchups +15% |
| Throw-ins (total) | 35–45 | Rarely quoted; long-throw teams matter for set-piece props |

## Goal sub-type shares (fraction of a match's goals; multiply by λ_goals for that game)

For "will ≥1 goal of type X happen" props, model type-X goals as a **thinning** of total goals:
`E = share × λ_goals`, `P(≥1) = 1 − e^(−E)` (proppricer `GOAL_SHARE` + `p_share_of_goals`,
CLI `share`). Shares derived offline from cached data — regen with `python3 calibrate_curve.py rare`.

| Sub-type | Share of goals | Source basis |
|---|---|---|
| Goal from outside the penalty box | 0.12 | StatsBomb 2018-22 9.9% (33/334, shot location outside 18-yd box, ex-penalties) \| ESPN 2026 12.7% (29/229, text-parse). Locked to 0.12 (lean 2026, current tournament). |
| Own goal | 0.05 | StatsBomb 2018-22 4.5% (15/334, "Own Goal For" events) \| ESPN 2026 5.2% (12/229, "Own Goal" keyEvents). 2026 OGs run hot (0.15/match ≈ 2018). |
| Headed goal | 0.152 | StatsBomb 2018-22 17.4% (58/334, shot.body_part = "Head") \| ESPN 2026 15.2% (37/243, `type.text` = "Goal - Header"). Locked to 2026; ESPN may slightly under-tag (some headers land in generic "Goal"/"Goal - Free-kick"), so treat as a floor. |

## Match-event flat rates (per-match P, opponent-independent — NOT scaled by goals)

Some props are ~fixed per-match base rates, not tied to the game's goal environment. Submit the flat P
directly (small ±2-3 tilt only for a clearly physical/tame matchup). Regen with `calibrate_curve.py subs`.

| Event | P(≥1 per match) | Source basis |
|---|---|---|
| Substitution in the first half (in-play, before HT whistle) | 0.15 | **Injury-driven** (no tactical subs pre-HT), so flat/opponent-independent. StatsBomb 2018-22 17.2% (22/128, period 1 & minute<45) \| ESPN 2026 12.3% (10/81). Pooled 15.3% → locked 0.15. Excludes halftime subs (those log at ≥45'/period 2). |
| **EITHER team makes a substitution AT HALFTIME** | **0.58** | **ESPN 2026, n=91: 55/91 = 60.4% (KO-only 12/21 = 57.1%) → price ~57-58, shade to KO.** Per-team rate 34.1%; the two teams are slightly POSITIVELY correlated so "either" (60.4%) > independence 1−(1−.341)²=56.5% (a scrappy/lopsided game prompts BOTH benches). Count dist: 0 subs 40% / 1 subs 33% / 2+ 27%. Detection: HT subs log at dv exactly `"45'"` (no stoppage `+`), bracketing the "Second Half begins" marker (both sides of it); 1H-stoppage/injury subs get `"45'+X'"`. 🔴 **Knockout correction: the all-games base rate (58) is too high for tight knockouts, where managers hold subs — a tight level game at HT often sees NO halftime sub. Same KO sub-activity over-pricing as sub-G/A below. TEMPER to ~48 in deep KO / tight-projected games; the full 58 is for group-stage / lopsided games only.** No book market so keep modest confidence; game-script tilt is DOWN-weighted (tight/cagey → ~46-48, only a clear blowout-projection → ~55). |

### Total substitutions in regulation (2026: 5/team, ≤3 windows + HT; combined cap 10; concussion subs extra)
For "N+ total subs in regulation (90+stoppage)" props. **ESPN 2026 KNOCKOUT data, n=22, regulation-only
(ET subs excluded via period tag, cross-checked vs roster `subbedIn`):** mean **8.59** combined; distribution
6:14% / 7:0% / 8:27% / 9:32% / 10:27%. → **P(≥8)=86%, P(≥9)=59%, P(≥10)=27%.**
- **Splits HARD by game-script (THIS is the edge):** games DECIDED in regulation → P(≥9)=**71%** (12/17);
  games that went to ET/pens → P(≥9)=**20%** (1/5). ET-bound teams HOLD a sub for the ET window (they get a
  6th in ET). The 3 lowest games (6 subs) were 2 shootout games + one comfortable 1-0.
- **Price:** `P(≥9) = (1−p_ET)·0.71 + p_ET·0.20`, p_ET = P(regulation draw → ET). Even/tight matchup → ~54-55%;
  mismatch / clear favorite → ~60-61%. Crowd sits high (~65-72%, "everyone empties the bench") → below-crowd
  fade, MORE so the more even the game. Anchor to a total-subs O/U line if the book posts one. (The weighted
  average is a sound law-of-total-probability split on the ET regime; caveat = the ET conditional is n=5, wide
  CI, and a COMFORTABLE favorite also suppresses subs (a 1-0 cruise → 6), so skew a hair down in cruise spots.)

### "Player plays the entire match" (full 90+stoppage, reg) — ESPN 2026 KO, n=22
P(a STARTER plays full) by position: GK 98%, center-backs 85-100%, fullbacks ~63%, central mids ~50%,
**advanced attackers (F/CF/AM/wide-fwd) ~32%, wide forwards (LF/RF) ~15-31%.** So "star winger/forward
plays 90" is a LOW base rate (~30%) — the 5-sub era hooks attackers ~2/3 of the time.
- **Crowd is SHARP here (~44-48, not 55-65)** — they price the 5-sub reality; the fade edge is ~true 32 vs
  crowd ~46 ≈ 14pts, not 25. Don't over-claim it. A managed injury roughly cancels the healthy-star bump.
- **Game-state (COUNTERINTUITIVE):** tied→ET **27%** (LOWEST), 1-goal 31%, blowout 33%. A level game does NOT
  keep the forward on — the manager throws fresh attackers to win before ET. An EVEN matchup argues the number
  DOWN. Price a starting star forward ~30-33.

### Two more KO base rates empirically validated (ESPN 2026, n=22)
- **P(a substitute scores, reg) = 50% (13/26 combined ESPN + tracked KO props).** Drove SUB_GOAL_SHARE 0.18→0.24.
  Crowd anchors LOW (~32) → above-crowd is +EV (price ~45 vs crowd ~33 ≈ +2/prop). Size with CI-humility
  (~45, not 50); the edge is the BASE RATE, not a track record.
- **P(a substitute scores OR ASSISTS, reg) = 53.8% (49/91 ESPN 2026; KO-only 57.1%, 12/21).** Sub assists =
  19.6% of all credited assists (37/189) on top of 48 sub goals; **48/49 hits came in the 2H** (subs barely
  exist pre-HT — already baked into the game-level rate, no half-restriction needed). Per-goal sub-involvement
  share **0.278**. ⚠️ **λ-SCALED (measured curve): by reg goals — 0 goals: 0/7, 1-2: ~26%
  (9/35), 3: 73% (16/22), 4+: 89% (24/27). Poisson-mix pricing: λ 2.2-2.4 → ~44-46; λ 2.7 → ~51-53; λ 3.0+ →
  ~55-58.** The prop is leveraged on the goal environment.
  🔴 **DEEP-KO REALITY CHECK (the model runs HOT here): the crowd anchored ~38 on this union in tight
  low-scoring knockouts and was right — a below-crowd sit lost when priced at ~47-53. The 0.278 share is
  GROUP-STAGE-inflated: blowout subs pad goal/assist stats, but tight QF+ knockout uses subs defensively/late
  and rides starters. In QF+ TEMPER toward crowd ~40, cap the above-crowd reach at ~+5 — a +15 above-crowd bet
  is exactly the cross-crowd deviation the 50%-hit guardrail punishes. Trust the model's LEVEL only in group/early
  KO; discount it hard in the deep rounds.**
- **P(both halves have the SAME goal count, reg) = 27% (6/22)**, vs `count_race(0.44λ,0.56λ)['tie']` model 25% — ✅
  model validated. Dominated by 1-1-per-half and 0-0 games; below-crowd (crowd overprices "balanced").
- **First card before first goal:** ESPN keyEvents/commentary UNDER-capture cards (~2.8/game logged vs ~4 real),
  so the raw 45.5% (10/22) is a biased-LOW floor; the `first_event_race` model (~52 at μ_c 3.2) is the better
  estimate — price in the ~50-52 band, shading down only for the card-total-over bias.

## Hydration-break windows (2026 — VERIFIED, web-confirmed)

FIFA 2026 streamlined the rule: a **3-min break ~22' into each half, called by the ref in EVERY match**
(no weather condition). So the breaks fall at **~22'** and **~67'** (±1–2' to an existing stoppage), NOT the
old-standard 30'/75'. This is the settlement window for all "before/after hydration break" props:
- **"Goal/event BEFORE 1st break" = before ~22'** → use F(22) ≈ **0.15** of goals (share, ×λ_full). Do NOT use
  the 30'/0.25 window — it over-prices (a 30'-window price of ~50 should be ~38-40 at the true 22' break).
- **"Goal in 1H AFTER 1st break" = window (22', 45']** → thin by ~0.29 of match goals (or ~0.65 of 1H goals
  off a 1H-exact-goals devig). ⚠️ **The window-share model OVER-PRICES this prop (a raw ~51 resolved below a
  crowd of ~44). Anchor toward the crowd ~44, not the raw ~51** — the rightward break-timing skew (refs wait
  for a dead ball, so the window is often shorter than 22-45) plus early-2H-of-half lull means the model's
  timing share runs high. Sit at/below crowd here.
- **"Goal/event AFTER 2nd break" = after ~67'** → use 1−F(68) ≈ **0.32** of full-match goals (or ~0.57 of 2H
  goals when a 2H-specific λ is available). Empirically resolves YES above crowd — lean UP.
- Matches the EVENT_CURVE quarter nodes (F(23)/F(68)); those ARE the break times, not just midpoints.

## Time-of-match shares (multiply full-match λ by these)

| Event | 1st half share | 2nd half share | Why |
|---|---|---|---|
| Goals | 0.44 | 0.56 | Fatigue, subs, chasing games |
| Shots / SOT | 0.47 | 0.53 | Mild late tilt |
| Corners | 0.45 | 0.55 | Tracks shot volume |
| Cards | 0.35 | 0.65 | Fatigue, tactical fouls, frustration |
| Cards in STOPPAGE time (45'+/90'+) | — | share **0.17** of all cards | ESPN 2026 n=91 games, keyEvents 0.175 & commentary 0.171 agree; 32/81 games (39.5%, a FLOOR — under-capture) had ≥1. Price P(≥1)=1−e^(−0.17·μ_cards) ≈ 42-50% at μ 3.2-4 |
| Goals in STOPPAGE time (45'+/90'+) | — | share **0.135** of all goals | ESPN 2026 n=101 games / 260 goals: 13.5% of goals land in stoppage. **STAGE-INVARIANT (verified): group 13.3% / KO 13.8% — no KO uptick (unlike pen-or-red), it's a pure timing property → use 0.135 in KO.** Game-level P(≥1 stoppage goal)=30.7% (KO 9/29=31.0%). λ-scalable: **P(≥1)=1−e^(−0.135·μ_goals)** (=29% at μ 2.5, 31% at μ 2.7). For "goal in first- OR second-half stoppage" props. |
| Penalties | 0.45 | 0.55 | Tracks box activity |
| Goals 0–15 min | ~0.11 | — | For "early goal" props |
| Goals 76–90+ | — | ~0.23 | Stoppage time inflates the last bucket |

## Player-level building blocks

| Quantity | Typical value | Notes |
|---|---|---|
| Star striker share of team goals | 0.28–0.35 | +0.03–0.05 if penalty taker |
| Second striker / winger share | 0.15–0.22 | |
| Attacking mid share | 0.10–0.15 | |
| Goals per shot on target (conversion) | 0.30–0.35 | Headers lower (~0.25), one-on-ones higher |
| SOT per shot | 0.33–0.38 | Long-range shooters lower |
| Striker shots per 90 | 2.5–3.5 | Target men on set-piece teams at high end |
| Sub-risk minutes discount | ×0.85–0.92 | If likely off at ~70', scale per-90 rates |

## Style multipliers (apply to base λ, keep within ±25%)

| Situation | Adjustment |
|---|---|
| Cross/set-piece heavy team | corners ×1.15–1.25 for them |
| Counter-attacking team | own corners ×0.85; own offsides ×1.15 |
| Opponent plays high line | offsides ×1.2–1.3 |
| Opponent in deep block | offsides ×0.75; own corners ×1.1 |
| Derby / elimination stakes | cards ×1.2–1.4 |
| Mismatch (David vs Goliath, 48-team field) | cards ×1.05–1.15 (chasing fouls); goals λ split very lopsided |
| Big ref (high card avg) | cards ×1.2–1.5 — ALWAYS check the referee |
| Altitude / heat | 2H shares shift further late (fatigue) |

## Settlement reminders (check before pricing ANY prop)
- **Total-cards COUNT definition (FanDuel-confirmed 2026, assume platform matches):** count = yellows +
  reds shown to ON-PITCH players in **regulation only** (ET/shootout cards DON'T count); **a 2nd-yellow→red
  = 2 cards** (the yellow + the red); manager/bench/subbed-off cards = 0. So for a cards COUNT use the
  PLAYER-card prior (~3.3–4.2 KO), NOT an inflated bench-included number; nudge up slightly for 2nd-yellows.
  ⚠️ Do NOT confuse with the **booking-POINTS** market (yellow=10, straight red=25) — irrelevant to a
  cards-vs-goals COUNT prop, where a straight red = 1 card. Anchor μ_cards to the book's total-cards O/U
  line (bakes in this definition); confirm whether the platform also counts a 2nd-yellow as 2.
- "90 minutes + stoppage" vs "including extra time" — knockout props differ.
- Player props: does the player need to start? Play at all?
- Corners: taken vs awarded (a corner awarded but match ends = varies by book).

## Two structural laws (never forget)
1. "Strictly more than opponent" props on low counts: tie probability ~15–22%
   makes >55% answers nearly impossible without total domination.
2. "X AND Y" goal props: lay out the scoreline grid; the conjunction usually
   excludes the modal scoreline (1-1, 1-0). Never multiply marginals.

## Low-sample fixture projection (e.g. the third-place match)
Method for a fixture type with almost no direct history: take the fixture-vs-knockout delta from the last two
World Cups (FT-only baselines), project each onto the **2026 KO baseline (n=22 FT-only, R32+R16+QF+SF)**. Two
estimates (not averaged) — their spread = how much to trust the lean.

| Stat | 2026 KO avg | Δ2018 | Δ2022 | exp(2018) | exp(2022) |
|---|---|---|---|---|---|
| Goals | 2.68 | −0.89 | −0.50 | **1.79** | **2.18** |
| Shots | 23.09 | −0.33 | −2.70 | **22.8** | **20.4** |
| Yellows | 2.91 | −0.89 | −0.20 | **2.02** | **2.71** |
| SOT | 8.27 | +0.44 | −3.70 | 8.72 | 4.57 |
| Fouls | 22.64 | −9.78 | +2.00 | 12.9 | 24.6 |
| Corners | 9.41 | −1.67 | +1.20 | 7.74 | 10.6 |

- **Both estimates agree → trust the lean:** e.g. Goals ~1.8–2.2 (below 2.68), Shots ~20–23, Yellows ~2.0–2.7.
- **Estimates straddle the baseline → noise, use the flat 2026 KO number:** SOT ~8.3, Fouls ~22.6, Corners ~9.4.
- Caveats: delta is only n=2 tournaments — keep any lean gentle (regression to mean). A "high-scoring
  third-place match" reputation is an artifact of comparing to the group-inflated whole-tournament average;
  vs the correct KO peer set it is normal-to-slightly-below.
- **Lineups override everything for player props** — rotation/rest is the only thing that moves scorer/SOT props
  off these baselines; price them only once XIs post.
