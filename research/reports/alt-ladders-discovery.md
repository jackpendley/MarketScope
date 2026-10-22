# Alternate ladders: discovery (MS-055b)

_Generated 2026-10-22 21:46 UTC · commit `08edb64` · reproduce with `research/src/marketscope_research/run_alt_ladders.py --phase discovery`._

Design pre-registered in `research/PREREGISTRATION.md` (Addendum Q, committed before this code; corrections in Addendum R). Every retail alternate spread and total (−300 to +300) priced against the sharp-consensus fair probability at its exact line (engine v2, Shin devig); candidates are the ones worth more than 0 at decision time, scored at the sharp-consensus close. Game bootstrap (5,000, seed 2026). **Analysis, not betting advice.**

**Sample:** 93 games; 6278 candidate alternates as registered, 6257 after the coherence rule.

## As registered (Addendum Q)

Mean value at the close: +4.29% (+3.47 to +5.10). **Primary result:** **retail alternates above the sharp consensus carry positive value** (discovery result; confirmation on weeks 7–14 decides).

| Alternates                        | Positions | Value expected at decision time | Value at the close      |
| --------------------------------- | --------- | ------------------------------- | ----------------------- |
| Spread alternates spanning 3 or 7 | 1976      | +2.25%                          | +2.18% (+1.42 to +2.93) |
| Other spread alternates           | 765       | +2.36%                          | +1.70% (+0.70 to +2.71) |
| Total alternates                  | 3537      | +4.95%                          | +6.03% (+4.79 to +7.22) |
| 0.5–1 point from the main line    | 177       | +1.93%                          | +2.30% (+1.25 to +3.33) |
| 1.5–3 points                      | 727       | +1.92%                          | +2.42% (+1.70 to +3.15) |
| More than 3 points                | 5374      | +4.10%                          | +4.61% (+3.67 to +5.53) |
| Caesars                           | 1003      | +5.46%                          | +5.89% (+4.33 to +7.14) |
| DraftKings                        | 1106      | +3.33%                          | +3.81% (+2.80 to +4.83) |
| FanDuel                           | 1962      | +4.38%                          | +4.56% (+3.56 to +5.58) |
| Hard Rock                         | 2207      | +2.72%                          | +3.57% (+2.75 to +4.43) |

## Corrected (Addendum R): ghost markets removed, direct scoring

The engine moves a sharp price to another line by adding the main-line calibration shift unchanged at every line, which overstates the tails far from the main line. Direct value scores half-point alternates against the sharp books' own prices at that exact line instead (Pinnacle, Circa, Bookmaker.eu, Shin devig). The coherence rule removes ghost markets.

Engine-scored +4.28% (+3.45 to +5.09); direct-scored -3.64% (-4.85 to -2.30) on 1724 alternates with a direct price.

Under Addendum R a claim needs both intervals above 0; these discovery numbers were computed after the problems were found, so they are descriptive only.

| Alternates                        | Count | Engine-scored value     | With a direct price | Direct-scored value     |
| --------------------------------- | ----- | ----------------------- | ------------------- | ----------------------- |
| All                               | 6257  | +4.28% (+3.45 to +5.09) | 1724                | -3.64% (-4.85 to -2.30) |
| Spread alternates spanning 3 or 7 | 1965  | +2.12% (+1.37 to +2.87) | 485                 | -2.68% (-4.59 to -0.77) |
| Other spread alternates           | 764   | +1.72% (+0.71 to +2.72) | 257                 | -3.57% (-6.07 to -0.86) |
| Total alternates                  | 3528  | +6.03% (+4.79 to +7.22) | 982                 | -4.14% (-5.41 to -2.72) |
| 0.5–1 point from the main line    | 169   | +2.06% (+1.08 to +2.96) | 115                 | +1.62% (+0.41 to +2.84) |
| 1.5–3 points                      | 719   | +2.37% (+1.65 to +3.12) | 293                 | +0.75% (-0.25 to +1.91) |
| More than 3 points                | 5369  | +4.60% (+3.66 to +5.52) | 1316                | -5.08% (-6.31 to -3.67) |
| Caesars                           | 993   | +5.88% (+4.30 to +7.12) | 343                 | -0.09% (-3.63 to +2.91) |
| DraftKings                        | 1101  | +3.79% (+2.75 to +4.81) | 317                 | -5.65% (-7.28 to -4.00) |
| FanDuel                           | 1958  | +4.54% (+3.54 to +5.56) | 596                 | -4.85% (-5.92 to -3.81) |
| Hard Rock                         | 2205  | +3.56% (+2.75 to +4.43) | 468                 | -3.35% (-4.65 to -1.95) |

## Engine v3 (Addendum T secondary)

Candidates selected and scored with the MS-059 line conversion (logit scale for spreads and totals, fitted to the sharp books' own alternate prices), coherence rule applied. Secondary: the registered primary stays on engine v2 (post hoc on discovery games: descriptive only).

3049 candidates. Engine-scored +2.29% (+1.56 to +2.98); direct-scored -1.13% (-2.68 to +0.59) on 864 with a direct price. Within 1 point of the main line (direct): +1.63% (+0.41 to +2.90).

| Alternates                        | Count | Engine-scored value     | With a direct price | Direct-scored value     |
| --------------------------------- | ----- | ----------------------- | ------------------- | ----------------------- |
| Spread alternates spanning 3 or 7 | 1410  | +2.46% (+1.56 to +3.42) | 347                 | -2.27% (-4.61 to +0.19) |
| Other spread alternates           | 1988  | +2.27% (+1.42 to +3.09) | 544                 | -1.97% (-3.86 to +0.04) |
| Total alternates                  | 1061  | +2.33% (+1.49 to +3.12) | 320                 | +0.29% (-1.14 to +1.87) |
| 0.5–1 point from the main line    | 170   | +2.06% (+1.09 to +2.95) | 113                 | +1.63% (+0.41 to +2.90) |
| 1.5–3 points                      | 633   | +2.38% (+1.62 to +3.20) | 224                 | +1.09% (-0.02 to +2.42) |
| More than 3 points                | 2246  | +2.28% (+1.51 to +3.04) | 527                 | -2.67% (-4.64 to -0.49) |
| Caesars                           | 663   | +3.89% (+2.18 to +5.33) | 212                 | +2.61% (-1.04 to +5.68) |
| DraftKings                        | 385   | +1.09% (+0.10 to +1.95) | 125                 | -2.63% (-4.94 to -0.62) |
| FanDuel                           | 758   | +2.05% (+0.96 to +3.03) | 256                 | -4.24% (-5.88 to -2.78) |
| Hard Rock                         | 1243  | +1.95% (+1.23 to +2.59) | 271                 | -0.42% (-1.69 to +0.85) |

## What this can't see

Retail limits on alternates (usually lower than on main lines); whether a price would have been accepted; sharp alternate prices carry more margin than main lines, so the direct fair price is itself approximate.
