# Cross-market value on main markets: discovery (MS-054)

_Generated 2026-10-22 21:40 UTC · commit `08edb64` · reproduce with `research/src/marketscope_research/run_cross_market.py --phase discovery`._

Design pre-registered in `research/PREREGISTRATION.md` (Addendum P, committed before this code; corrections in Addendum R). Data: the research lake (full ladders). Fair probabilities from the frozen engine v2 and Shin devig; the sharp consensus is the equal-weight mean of Pinnacle, Circa, Bookmaker.eu and Novig. Values are per unit at the sharp-consensus close. Game bootstrap (5,000, seed 2026). **Analysis, not betting advice.**

**Sample:** 93 games in the lake for this phase.

## As registered (Addendum P)

### A: moneylines priced better than the book's own spread

51 positions. Mean value at the close: -4.87% (-6.29 to -3.52). **Primary result:** **the opposite** (discovery result; confirmation on weeks 7–14 decides).

| Retail book | Positions | Value expected at decision time | Value at the close      |
| ----------- | --------- | ------------------------------- | ----------------------- |
| Caesars     | 26        | +2.12%                          | -5.37% (-6.77 to -3.19) |
| DraftKings  | 11        | +2.21%                          | -4.14% (-9.51 to -1.73) |
| FanDuel     | 11        | +1.66%                          | -5.55% (-7.49 to -4.21) |
| Hard Rock   | 3         | +0.79%                          | -0.71% (-0.98 to -0.17) |

### B: retail prices better than the sharp consensus at the same line

131 positions. Mean value at the close: +3.56% (+2.28 to +4.78). **Primary result:** **same-line prices above the sharp consensus carry positive value** (discovery result; confirmation on weeks 7–14 decides).

| Market    | Positions | Value expected at decision time | Value at the close      |
| --------- | --------- | ------------------------------- | ----------------------- |
| moneyline | 31        | +1.31%                          | +2.69% (+1.24 to +4.04) |
| spreads   | 82        | +3.24%                          | +3.65% (+2.00 to +5.21) |
| totals    | 18        | +4.21%                          | +4.69% (+1.89 to +7.49) |

| Retail book | Positions | Value at the close       |
| ----------- | --------- | ------------------------ |
| Caesars     | 26        | +7.67% (+4.38 to +10.38) |
| DraftKings  | 32        | +1.88% (-0.43 to +3.74)  |
| FanDuel     | 44        | +2.85% (+1.53 to +4.14)  |
| Hard Rock   | 29        | +2.82% (+1.44 to +4.01)  |

| Hours before kickoff | Positions | Value at the close      |
| -------------------- | --------- | ----------------------- |
| 48                   | 41        | +4.51% (+2.77 to +6.24) |
| 24                   | 23        | +3.83% (+1.15 to +6.12) |
| 6                    | 34        | +2.49% (+1.32 to +3.76) |
| 1                    | 33        | +3.31% (+2.21 to +4.79) |

## Corrected (Addendum R): ghost markets removed, direct scoring

The feed sometimes leaves a sportsbook market marked active after the book stopped updating it. The registered main-line rule can pick such a ghost when it is priced closer to even than the real line. The coherence rule keeps a market only if its price is consistent with the book's fresher markets. Direct value scores half-point spreads and totals against the sharp books' own prices at that exact line, with no engine conversion.

A: 48 positions, -4.62% (-5.74 to -3.30): **the opposite** (post hoc: cannot support a claim). B: 116 positions, engine-scored +2.97% (+1.79 to +4.02); direct-scored +2.20% (-0.14 to +4.26) on 55 positions with a direct price. Corroborated by our own collector: 6 of 99 checkable positions (DraftKings, FanDuel, Hard Rock).

Under Addenda R and S a claim needs corroborated positions with both intervals above 0. These discovery numbers were computed after the problems were found, so they are descriptive only, and our collector only started on 2026-10-16, so few discovery prices can be corroborated.

| Positions                         | Count | Engine-scored value     | With a direct price | Direct-scored value     |
| --------------------------------- | ----- | ----------------------- | ------------------- | ----------------------- |
| All                               | 116   | +2.97% (+1.79 to +4.02) | 55                  | +2.20% (-0.14 to +4.26) |
| moneyline                         | 31    | +2.69% (+1.24 to +4.04) | 0                   | –                       |
| spreads                           | 70    | +3.08% (+1.57 to +4.36) | 42                  | +2.20% (-0.91 to +4.77) |
| totals                            | 15    | +3.07% (+1.43 to +5.28) | 13                  | +2.22% (+1.08 to +3.36) |
| Caesars                           | 17    | +5.63% (+2.43 to +8.17) | 7                   | +0.39% (-2.10 to +3.54) |
| DraftKings                        | 27    | +1.81% (-0.62 to +3.69) | 15                  | +1.82% (-2.05 to +4.72) |
| FanDuel                           | 43    | +2.76% (+1.50 to +4.03) | 17                  | +2.46% (-0.15 to +4.49) |
| Hard Rock                         | 29    | +2.82% (+1.44 to +4.01) | 16                  | +3.08% (+0.56 to +5.14) |
| Corroborated (Addendum S primary) | 6     | +4.14% (+1.65 to +6.84) | 1                   | +1.87% (+1.87 to +1.87) |

## Engine v3 (Addendum T secondary)

Positions selected and scored with the MS-059 line conversion (logit scale for spreads and totals, fitted to the sharp books' own alternate prices), coherence rule applied. Moneyline conversion stayed v2, so A is the corrected A above. Secondary: the registered primaries stay on engine v2 (post hoc on discovery games: descriptive only).

B: 117 positions, engine-scored +2.97% (+1.79 to +4.06); direct-scored +2.05% (-0.25 to +4.24) on 54 positions with a direct price. Corroborated: 7 positions, engine-scored +4.34% (+1.63 to +6.47); direct-scored +1.87% (+1.87 to +1.87) on 1.

## What this can't see

Alternate ladders (MS-055b); retail limits; whether a price would have been accepted at size; feed errors that are not ghost markets.
