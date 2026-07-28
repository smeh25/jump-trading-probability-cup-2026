# Probability Cup — Results Dashboard

Row-level data lives in [predictions.csv](predictions.csv) (source of truth). All aggregate
numbers below come from `python3 analyze.py` — they are not hand-edited.

---

## Scoring: the free cushion vs. the real edge

The platform scores the crowd as the **mean of individual entrants' Brier scores**, not the
Brier of their average. By Jensen's inequality that gap is positive, so a forecast collects it
just by sitting near consensus. **Platform RBP = cushion + doc-edge.** Only the **doc-edge**
(accuracy vs. the consensus line) separates a forecaster from the rest of the field. Optimize
doc-edge; the cushion takes care of itself.

---

## Cumulative (through the final — 102 matches, 1,174 settled props)

- **Doc-edge +631.4 (+0.538/prop), t ≈ 2.69 from zero** — a statistically significant edge over the consensus line.
- **Platform RBP +5,105.8 (+4.35/prop).**
- **Beat the consensus line on 876 / 1,174 props (74.6%).**
- Mean Brier: forecast 0.215 vs. crowd 0.220.

---

## By category — doc/prop

| category | doc/prop | read |
|----------|---------:|------|
| race | **+0.9** | Top bucket — SOT/corner races on mismatches, faded down. Foul-races are coin-flips (price honestly, don't reach above crowd). |
| fav_player | **+1.4** | Benched-star + marquee + half-scope SOT fades, all DOWN. Above-crowd player holds have lost 4× — cap the up-side to ~5. |
| offsides | +0.3 | Blowout-vs-grind rule: above-crowd offside WINS in blowouts (M35, M43 in a 5-0) but LOSES in grinds (M39, M42). Reach above crowd only when a blowout is likely. |
| fav_team_total | +0.2 | Scoring-only (wins moved to match_result). The edge is the underdog-side fades (underdog to score, esp. half-scoped) + the public-favorite upset tail (M36 0-0). |
| match_result | +0.7 | Win/advance/reg-draw, direct function of the 3-way ML. n=37, mostly at-crowd cushion; the upset tail pays (M89 Brazil-advance NO). |
| totals | +1.0 | Direct lines (esp. the pick'em SOT-ladder rung); above-crowd OK if small and +EV, but the downside is correlated on low-event games — keep the gap ≤~5. |
| ht_lead | +0.6 | Tied/ahead at HT. n=27, tight crowd_hat (cMAE ~2), a reliably small-positive cushion. |
| and_conjunction | −0.6 | Use the direct line / full grid. High-prob conjunctions the crowd under-prices (can sit above); low-prob conjunction fades bleed when they hit (M42) — so don't oversize. |
| discipline | **−0.04** | Climbed from −1.05 to ~break-even — the disciplined card-total fades are paying (M89 4+cards 32v42 NO +18.9). Still fat-tailed. Split: card TOTALS/halves/pen → fade DOWN but ANCHOR to the market; card RACES → push UP toward the chasing dog. |

**By direction:** below-crowd ≈ +1.3/prop (the robust +EV side); above-crowd ≈ −0.3/prop — but
that average is dragged by *oversized* reaches; a small, +EV above-crowd hold is fine.
**By half-scope:** ~no effect (half +0.4 vs. full +0.7, noisy).

**crowd_hat reliability is not uniform** (`crowdmodel.py card` prints a per-category `cMAE`
column). Weakest buckets: fav_player ~4.9, discipline ~3.9, race ~3.8; tightest:
totals/fav_team_total ~2.7. Dominance-race *direction* is unpredictable — never reach above
crowd_hat on a dominance prop.

---

## Per-game one-liners (plat / doc / beat·n / top prop)

| M | match | plat | doc | beat | top prop |
|---|-------|-----:|----:|:----:|----------|
| 1 | USA v Paraguay | −12.0 | −50.5 | 5/10 | Paraguay more corners +6.2 |
| 2 | Canada v Bosnia | +79.8 | +41.0 | 9/10 | Džeko 1+ SOT +29.9 |
| 3 | Korea v Czechia | −6.0 | −44.0 | 5/10 | Son scores +12.0 |
| 4 | Qatar v Switzerland | +69.2 | +29.7 | 9/10 | Qatar score 1+ +21.9 |
| 5 | Brazil v Morocco | +84.1 | +50.8 | 9/10 | Brazil win +15.5 |
| 6 | Haiti v Scotland | −19.6 | −50.2 | 4/10 | Tied at HT +4.3 |
| 7 | Australia v Türkiye | +24.5 | −2.1 | 6/9 | Kökçü 1+ SOT 2H +9.7 |
| 8 | Netherlands v Japan | +8.2 | −19.0 | 6/10 | Netherlands win +11.1 |
| 9 | Germany v Curaçao | +57.4 | +27.0 | 8/10 | Curaçao more fouls 44v66 NO +27.0 |
| 10 | Sweden v Tunisia | +25.8 | −0.1 | 7/10 | 2H>1H goals +8.6 |
| 11 | Spain v Cabo Verde | +53.4 | +24.0 | 9/10 | Olmo score/assist +23.0 |
| 12 | Belgium v Egypt | +43.3 | +18.2 | 9/10 | Belgium win +14.1 |
| 13 | Saudi Arabia v Uruguay | +19.5 | −4.5 | 7/10 | Saudi more fouls +8.2 |
| 14 | Iran v New Zealand | +65.6 | +39.2 | 9/10 | Taremi 1+ SOT 2H +22.6 |
| 15 | France v Senegal | +34.7 | +4.5 | 7/10 | France winning at HT +11.3 |
| 16 | Iraq v Norway | +25.9 | −0.6 | 7/10 | Mohanad Ali score/assist +7.0 |
| 17 | Argentina v Algeria | +19.3 | −7.3 | 6/10 | Mahrez 1+ SOT +19.9 |
| 18 | Austria v Jordan | +18.9 | −4.5 | 6/10 | Jordan more fouls NO +8.2 |
| 19 | Portugal v DR Congo | +39.1 | +11.1 | 7/10 | 2H<1H goals +11.2 |
| 20 | England v Croatia | +41.1 | +16.7 | 6/10 | England more fouls NO +12.7 |
| 21 | Ghana v Panama | +18.1 | −5.6 | 6/10 | Fajardo fade +16.7 |
| 22 | Uzbekistan v Colombia | +21.7 | +0.5 | 8/10 | Uzbekistan score +8.6 |
| 23 | Czechia v South Africa | +63.4 | +41.1 | 10/10 | South Africa more fouls 29v51 +20.8 |
| 24 | Switzerland v Bosnia | +26.1 | +2.4 | 8/10 | Bosnia penalty +13.0 |
| 25 | Canada v Qatar (6-0) | +36.8 | +13.8 | 7/10 | Canada dominance cluster |
| 26 | Mexico v Korea Rep | +36.2 | +13.3 | 8/9 | card-total shade +9.9 |
| 27 | USA v Australia | +16.1 | −7.5 | 6/9 | Australia corners +9.0 |
| 28 | Morocco v Scotland | +19.5 | −4.7 | 7/10 | Scotland SOT-2H fade +7.3 |
| 29 | Brazil v Haiti (3-0) | +49.5 | +23.7 | 8/10 | Nazon benched fade +10.2 |
| 30 | Türkiye v Paraguay | +29.8 | +10.1 | 5/10 | Kökçü benched fade 15v41 NO +17.6 |
| 31 | Netherlands v Sweden | +45.2 | +21.4 | 8/10 | Gyökeres half-SOT fade +9.8 |
| 32 | Germany v Côte d'Ivoire | +31.1 | +9.0 | 8/10 | both-SOT-HT 77v65 +9.6 |
| 33 | Ecuador v Curaçao (0-0) | +2.6 | −22.3 | 6/9 | shock 0-0; two oversized above-crowd holds sank doc |
| 34 | Tunisia v Japan (0-4) | +34.7 | +16.0 | 8/9 | Japan more fouls +13.6 |
| 35 | Spain v Saudi Arabia (4-0) | +57.7 | +30.9 | 9/10 | blowout: above-crowd offside +12.9 |
| 36 | Belgium v Iran (0-0) | +24.6 | +3.7 | 7/10 | shock 0-0; favorite-fades cashed |
| 37 | Uruguay v Cabo Verde (2-2) | +33.8 | +9.1 | 9/10 | Núñez benched fade 16v38 NO +15.5 |
| 38 | New Zealand v Egypt (1-3) | +10.1 | −14.3 | 6/10 | Trezeguet benched fade YES −20.6 (+EV tail) |
| 39 | Argentina v Austria (2-0) | +25.6 | +2.6 | 5/10 | 2-or-fewer goals +10.5 |
| 40 | France v Iraq (3-0) | +37.3 | +18.0 | 8/9 | Iraq 2H-SOT fade +8.5 |
| 41 | Norway v Senegal (3-2) | +34.4 | +11.8 | 9/10 | Norway-2H-goals fade +11.3 |
| 42 | Jordan v Algeria (1-2) | +13.4 | −8.0 | 6/10 | small fades won; two +EV holds hit tails (variance) |
| 43 | Portugal v Uzbekistan (5-0) | +58.0 | +32.3 | 9/10 | blowout: above-crowd offside +11.6 |
| 44 | England v Ghana (draw) | +25.6 | −1.0 | 8/10 | Ghana corners fade +8.5 |
| 45 | Panama v Croatia | +12.7 | −13.5 | 5/10 | Sučić fade +16.3 (Panama above-crowd cluster soured) |
| 46 | Colombia v DR Congo (1-0) | +24.1 | +2.6 | 7/10 | Díaz vig-fade 41v50 NO +11.4 |
| 47 | Switzerland v Canada (2-1) | +15.7 | −9.6 | 6/10 | Xhaka/David player fades cashed |
| 48 | Bosnia-H v Qatar (3-1) | −17.5 | −43.4 | 4/10 | biggest deviations all lost (2H-corner −17, fouls −14) |
| 49 | Scotland v Brazil (0-3) | +31.2 | +10.0 | 9/10 | Brazil 2H-SOT +9.3 |
| 50 | Morocco v Haiti (4-2) | −7.5 | −28.6 | 5/10 | Nazon benched-fade backfired −15.5 (open game) |
| 51 | South Africa v Korea-Rep (1-0) | +59.7 | +35.5 | 9/10 | Son benched fade 23v56 NO +30.2 |
| 52 | Czechia v Mexico (0-3) | +62.8 | +41.3 | 9/9 | Schick benched fade 27v47 NO +19.0 |
| 53 | Curaçao v Côte d'Ivoire (0-2) | +41.8 | +14.0 | 8/10 | Côte d'Ivoire 5+ corners +11.2 |
| 54 | Ecuador v Germany (2-1) | +49.5 | +24.1 | 8/10 | Germany-2H-goals fade +10.5 |
| 55 | Japan v Sweden (1-1) | +31.8 | +13.4 | 6/8 | Japan-win fade 43v52 NO +11.5 |
| 56 | Tunisia v Netherlands (1-3) | +50.2 | +25.6 | 9/10 | 8+ total SOT 75v60 YES +12.4 |
| 57 | Paraguay v Australia (0-0) | +35.8 | +17.5 | 6/9 | 4+ cards fade 31v47 NO +14.6 |
| 58 | Türkiye v United States (3-2) | +24.0 | +2.7 | 7/10 | Balogun benched fade 15v28 NO +9.1 |
| 59 | Norway v France (1-4) | +7.4 | −15.4 | 7/10 | over-faded Norway team-scoring on benched-individual logic |
| 60 | Senegal v Iraq (5-0) | +19.9 | −0.8 | 8/10 | Mohanad Ali 15v20 NO +3.8 (player-vs-team split) |
| 61 | Uruguay v Spain (0-1) | +14.0 | −10.1 | 5/10 | Olmo benched fade 27v35 NO +8.5 |
| 62 | Cabo Verde v Saudi Arabia (0-0) | +42.0 | +21.2 | 9/10 | Cabo Verde offside 54v47 YES +9.8 |
| 63 | New Zealand v Belgium (1-5) | +56.7 | +33.9 | 8/10 | discipline-split, both sides won (Belgium 2H-card fade +9.2) |
| 64 | Egypt v Iran (1-1) | +31.5 | +10.8 | 8/10 | player-SOT pulled to line (Trezeguet +9.6) |
| 65 | Panama v England (0-2) | +12.1 | −12.3 | 6/10 | Fajardo benched fade +9.6 |
| 66 | Croatia v Ghana (2-1) | +16.3 | −5.5 | 6/10 | Luka Sučić trap fade +8.2 |
| 67 | DR Congo v Uzbekistan (3-1) | +8.9 | −11.8 | 8/10 | one above-crowd reach (both-1+SOT-2H 75v65 NO −12.2) ate it |
| 68 | Colombia v Portugal (0-0) | +27.5 | +6.0 | 8/10 | Ramos benched fade 17v37 NO +15.4 |
| 69 | Jordan v Argentina (1-3) | +7.2 | −16.9 | 6/10 | pen/red held at market +13.65 (dead-rubber coast) |
| 70 | Algeria v Austria (3-3) | +54.8 | +35.2 | 9/10 | 9+ corners 31v45 NO +13.4 (even-game fades swept) |
| 71 | South Africa v Canada (0-1) | +55.0 | −11.6 | 12/15 | Rayners benched fade +19.9 (card-after-break reach −36.6 the lone drag) |
| 72 | Brazil v Japan (2-1) | +142.0 | +30.5 | 13/15 | Brazil both-halves NO +26.1 |
| 73 | Germany v Paraguay (1-1, PAR adv pens) | +140.0 | +36.0 | 14/15 | Musiala benched 2+SOT NO +30.4 (favorite upset) |
| 74 | Netherlands v Morocco (1-1, MOR adv pens) | +106.2 | +21.2 | 11/15 | Brobbey starter 2+SOT 25v36 NO +21.2 (2nd straight upset) |
| 75 | Côte d'Ivoire v Norway (1-2) | −20.3 | −44.9 | 6/15 | first losing KO; open game, faded below crowd 13/15 (Amad benched YES −45.7) |
| 76 | France v Sweden (3-0) | +113.8 | +22.2 | 15/15 | Isak 2+SOT 17v32 NO +21.6 (perfect 15/15) |
| 77 | Mexico v Ecuador (2-0) | +76.1 | +5.4 | 11/15 | 20+ shots 82v56 YES +38.3 |
| 78 | England v DR Congo (2-1) | +92.1 | +7.9 | 9/15 | 20+ shots 85v64 YES +27.5 |
| 79 | Belgium v Senegal (1-2 upset) | +157.5 | +45.4 | 12/15 | Mané 2+SOT 14v32 NO +23.8 |
| 80 | USA v Bosnia (2-0) | +55.9 | −5.0 | 11/15 | card-in-1H 54v61 NO +21.4 |
| 81 | Spain v Austria (≥3-0) | +68.9 | +0.6 | 11/15 | 4+ cards 25v39 NO +22.1 |
| 82 | Portugal v Croatia (2-1) | +150.4 | +35.1 | 14/15 | Bernardo benched 1+SOT 23v39 NO +29.7 |
| 83 | Switzerland v Algeria (2-0) | +96.9 | +20.0 | 11/15 | Vargas 2+SOT 19v33 NO +23.0 |
| 84 | Australia v Egypt (1-1) | +158.8 | +49.2 | 13/15 | 20+ shots 73v59 YES +25.5 |
| 85 | Argentina v Cabo-Verde (2-2) | +93.8 | +3.2 | 11/15 | Álvarez benched G/A 20v39 NO +30.0 (22+ shots NO −27.7 ate doc) |
| 86 | Colombia v Ghana (1-0) | +20.3 | −21.9 | 11/15 | Semenyo 12v26 NO +22 (offside reach −34, 4+cards −29 sank doc) |
| 87 | Canada v Morocco (0-3) | +109.8 | +18.1 | 13/15 | Davies benched 1+SOT 25v34 NO +21.4 |
| 88 | Paraguay v France (0-1) | +143.5 | +32.8 | 13/15 | 4+ cards 27v42 NO +26.0 |
| 89 | Brazil v Norway (1-2, NOR win) | +89.8 | +12.4 | 13/15 | Ødegaard G/A 21v35 NO +19.4 (favorite upset) |
| 90 | Mexico v England (2-3, ENG win) | −48.7 | −66.0 | 5/15 | worst card — correlation disaster (Bellingham 2+SOT −33.8) |
| 91 | Portugal v Spain (0-1, ESP win) | +146.1 | +33.3 | 13/15 | sub-scores recalibration 45v32 YES +36.6 |
| 92 | USA v Belgium (1-4, BEL win) | +36.0 | −15.3 | 11/14 | benched Lukaku YES −20 in a 4-1 rout (doc− card) |
| 93 | Argentina v Egypt (3-2, ARG win) | +61.8 | −3.4 | 9/15 | Marmoush benched 17v37 NO +30.5 |
| 94 | Switzerland v Colombia (0-0, SUI adv pens) | +124.8 | +29.0 | 13/15 | 4+ cards base-rate 34v45 NO +23.0 (0-0 rank-climb card) |
| 95 | France v Morocco (2-0, FRA win) | +46.7 | −17.2 | 9/15 | Dembélé 29v40 NO +23.1 (below-field chalk card) |
| 96 | Spain v Belgium (2-1, SPA win) | +57.6 | −8.7 | 11/15 | Lukaku benched-SOT 21v45 NO +39.8 |
| 97 | Norway v England (1-1, ET) | +84.6 | +2.8 | 11/15 | Bellingham 30v42 NO +24.8 (tight 1-1 cashed fades; lone shot-reach −59.4) |
| 98 | Argentina v Switzerland (3-1, ET; reg 1-1) | +88.2 | +21.7 | 13/15 | Switzerland 3+ SOT 58v52 YES +16.0 |
| 99 | France v Spain (0-2, SF) | +126.0 | +47.0 | 13/15 | VAR-review fade 32v42 NO +23.9 |
| 100 | England v Argentina (1-2, SF) | +114.2 | +20.3 | 11/15 | 10+ corners 36v45 NO +14.6 |
| 101 | France v England (4-6, 3rd-place, 2×) | +76.1 | −24.1 | 10/15 | goal-before-break 54v44 YES +20.4 (10-goal freak game) |
| 102 | Spain v Argentina (0-0 reg, SPA won ET, FINAL 3×) | +205.8 | −45.5 | 11/20 | 5+ Spain shooters 86v70 YES +34.4 |

---

## Notes

- **Coverage:** the 48-team tournament had 104 matches; this log covers 102 — all 32 knockout matches (M71–M102) and 70 of the 72 group-stage matches (M1–M70). **Two group-stage matches were not forecasted and are not included** (which two is not recorded).
- Match IDs/dates for M9–M17 are sequential placeholders; verify against the platform before reuse.
- M9 (Germany v Curaçao) was a real staked card, recovered after being wrongly dropped once — verify before removing any card.
