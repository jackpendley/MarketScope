# Fair-value engine v3: line conversion (fit, MS-059)

_Generated 2026-10-22 19:05 UTC · commit `40d3690` · reproduce with `research/src/marketscope_research/run_ladder_fit.py --phase fit`._

Design pre-registered in `research/PREREGISTRATION.md` (Addendum T, committed before this code). Each sharp book's (Pinnacle, Circa, Bookmaker.eu) Shin-devigged prices at its own half-point alternates, and its own moneyline, predicted from the same book's main line by four conversions of the frozen engine v2 distributions; loss is the binary KL divergence, game bootstrap (5,000, seed 2026); selection weeks 1–3, validation weeks 4–6. **Uses no game outcomes; this is model building, not a claim about value.**

**Adopted conversion:** spreads scale (β = 0.98), totals scale (β = 1.06), moneyline v2.

## Spread alternates

Selection: 1743 observations over 48 games. Validation: 2712 over 45 games.

Mean KL on the selection games (×1000, lower is better):

| Candidate                | Mean KL ×1000 |
| ------------------------ | ------------- |
| V2 additive shift        | 0.742         |
| L logit shift            | 0.511         |
| M location shift         | 1.035         |
| S logit scale (β = 0.98) | 0.502         |

S's β grid, best three: 0.98 (0.502), 1.00 (0.511), 0.96 (0.524).

Validation, S logit scale minus V2, mean KL ×1000: -0.114 (-0.167 to -0.061). V2 0.592, S logit scale 0.478; mean absolute error 1.02 against 0.93 points.

**S logit scale adopted as engine v3** (validation KL lower, interval below 0).

| Observations                   | Count | V2 KL ×1000 | Chosen KL ×1000 | V2 abs. error (pts) | Chosen abs. error (pts) |
| ------------------------------ | ----- | ----------- | --------------- | ------------------- | ----------------------- |
| All                            | 2712  | 0.59        | 0.48            | 1.02                | 0.93                    |
| 0.5–1 point from the main line | 848   | 0.11        | 0.10            | 0.56                | 0.55                    |
| 1.5–3 points                   | 939   | 0.17        | 0.15            | 0.66                | 0.63                    |
| More than 3 points             | 925   | 1.47        | 1.15            | 1.80                | 1.59                    |
| Spanning 3 or 7                | 1657  | 0.67        | 0.50            | 1.10                | 0.96                    |
| Not spanning 3 or 7            | 1055  | 0.47        | 0.45            | 0.90                | 0.88                    |
| pinnacle                       | 1478  | 0.67        | 0.58            | 1.03                | 0.98                    |
| circasports                    | 73    | 0.94        | 0.54            | 1.58                | 1.19                    |
| bookmaker.eu                   | 1161  | 0.47        | 0.35            | 0.97                | 0.85                    |
| 48 h before kickoff            | 463   | 0.46        | 0.34            | 0.88                | 0.79                    |
| 24 h before kickoff            | 481   | 0.47        | 0.39            | 0.89                | 0.82                    |
| 6 h before kickoff             | 527   | 0.65        | 0.55            | 1.05                | 0.97                    |
| 1 h before kickoff             | 616   | 0.69        | 0.54            | 1.13                | 1.01                    |
| Close                          | 625   | 0.63        | 0.53            | 1.10                | 1.01                    |

## Total alternates

Selection: 1812 observations over 48 games. Validation: 2847 over 45 games.

Mean KL on the selection games (×1000, lower is better):

| Candidate                | Mean KL ×1000 |
| ------------------------ | ------------- |
| V2 additive shift        | 0.584         |
| L logit shift            | 0.432         |
| M location shift         | 0.370         |
| S logit scale (β = 1.06) | 0.347         |

S's β grid, best three: 1.06 (0.347), 1.04 (0.354), 1.08 (0.362).

Validation, S logit scale minus V2, mean KL ×1000: -0.376 (-0.529 to -0.237). V2 0.813, S logit scale 0.437; mean absolute error 1.33 against 1.06 points.

**S logit scale adopted as engine v3** (validation KL lower, interval below 0).

| Observations                   | Count | V2 KL ×1000 | Chosen KL ×1000 | V2 abs. error (pts) | Chosen abs. error (pts) |
| ------------------------------ | ----- | ----------- | --------------- | ------------------- | ----------------------- |
| All                            | 2847  | 0.81        | 0.44            | 1.33                | 1.06                    |
| 0.5–1 point from the main line | 899   | 0.15        | 0.14            | 0.66                | 0.66                    |
| 1.5–3 points                   | 1100  | 0.46        | 0.40            | 1.21                | 1.15                    |
| More than 3 points             | 848   | 1.98        | 0.80            | 2.20                | 1.38                    |
| pinnacle                       | 1538  | 0.78        | 0.42            | 1.43                | 1.05                    |
| circasports                    | 74    | 1.84        | 0.59            | 2.26                | 1.31                    |
| bookmaker.eu                   | 1235  | 0.80        | 0.45            | 1.15                | 1.05                    |
| 48 h before kickoff            | 493   | 0.52        | 0.35            | 1.14                | 0.98                    |
| 24 h before kickoff            | 506   | 0.55        | 0.36            | 1.15                | 0.98                    |
| 6 h before kickoff             | 550   | 0.76        | 0.41            | 1.30                | 1.05                    |
| 1 h before kickoff             | 646   | 0.98        | 0.51            | 1.44                | 1.15                    |
| Close                          | 652   | 1.11        | 0.51            | 1.52                | 1.12                    |

## Moneylines from the spread

Selection: 481 observations over 48 games. Validation: 665 over 45 games.

Mean KL on the selection games (×1000, lower is better):

| Candidate                | Mean KL ×1000 |
| ------------------------ | ------------- |
| V2 additive shift        | 0.638         |
| L logit shift            | 0.374         |
| M location shift         | 0.919         |
| S logit scale (β = 0.98) | 0.431         |

Validation, L logit shift minus V2, mean KL ×1000: -0.084 (-0.234 to 0.026). V2 0.427, L logit shift 0.343; mean absolute error 1.01 against 0.92 points.

**V2 stays**: L logit shift did not beat it on validation with the interval below 0.

| Observations                   | Count | V2 KL ×1000 | Chosen KL ×1000 | V2 abs. error (pts) | Chosen abs. error (pts) |
| ------------------------------ | ----- | ----------- | --------------- | ------------------- | ----------------------- |
| All                            | 665   | 0.43        | 0.34            | 1.01                | 0.92                    |
| 0.5–1 point from the main line | 51    | 0.11        | 0.11            | 0.59                | 0.58                    |
| 1.5–3 points                   | 237   | 0.34        | 0.33            | 1.11                | 1.08                    |
| More than 3 points             | 377   | 0.52        | 0.38            | 1.01                | 0.87                    |
| pinnacle                       | 225   | 0.36        | 0.29            | 0.92                | 0.85                    |
| circasports                    | 217   | 0.38        | 0.38            | 0.97                | 0.91                    |
| bookmaker.eu                   | 223   | 0.53        | 0.36            | 1.15                | 1.00                    |
| 48 h before kickoff            | 135   | 0.39        | 0.24            | 0.97                | 0.79                    |
| 24 h before kickoff            | 133   | 0.41        | 0.36            | 0.99                | 0.91                    |
| 6 h before kickoff             | 132   | 0.40        | 0.37            | 0.96                | 0.95                    |
| 1 h before kickoff             | 132   | 0.47        | 0.40            | 1.06                | 1.00                    |
| Close                          | 133   | 0.46        | 0.34            | 1.10                | 0.95                    |

## What this can't see

Sharp alternates carry more margin than main lines, so the Shin fair price at an alternate is itself approximate. The books may share a pricing model, so agreement with them is agreement with the market's ladder, not with outcomes.
