# Model card

MarketScope has two model families:

- **Market-movement models** (Phase 7): predict how the betting market will move.
- **MarketScope Ratings** (Phase 9, see `docs/RATINGS.md`): predict the football.

Both follow spec §16: point-in-time features, chronological and game-grouped splits, baselines first, probabilistic scores with game-clustered uncertainty, and honest reporting of null results.

---

## 1. Market-movement model v1 (MS-024/025, 2026-10-18)

|                       |                                                                                                                                                                                   |
| --------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Purpose**           | Research. Describes when and how the NFL spread market moves. It is not shown in the product and is not a betting tool.                                                           |
| **Targets**           | (a) Will the board-consensus home spread move ≥ 0.5 pts by t + 24 h? (b) Given a move, is it toward the home side?                                                                |
| **Prediction time t** | Any snapshot from 168 h to 24 h before kickoff with a consensus of at least 3 board books                                                                                         |
| **Label**             | The pregame consensus at the snapshot nearest t + 24 h, within ±3 h. If there is none, the label is missing (2.2% of eligible rows); it is never imputed                          |
| **Data**              | 2026 season. Weeks 1–5: OddsPapi history imported as derived 6-hourly snapshots (ADR-026). Weeks ≥ 6: live collection 4×/day (The Odds API)                                       |
| **Split**             | Chronological, grouped by game. Train weeks 1–3 (48 games), validation week 4 (16), **test week 5 (15)**. Live weeks ≥ 6 are a forward check, reported once 15 games are labelled |
| **Pre-registration**  | `research/src/marketscope_research/ml/design.py`, committed before labels (gate) and before models (protocol) were computed                                                       |
| **Code / reports**    | `research/src/marketscope_research/ml/`; `research/reports/market-ml-gate-v1.md`, `research/reports/market-baseline-v1.md`                                                        |

### Features (22, point-in-time)

Every feature is computed only from observations with `observed_at ≤ t`. This is checked mechanically: the leakage audit (`ml/audit.py`) perturbs every later observation and asserts that no feature changes. A planted feature that peeks at t + 24 h fails the audit (unit-tested), and the audit passed on 60 real snapshots.

- **Consensus and dispersion:**
  - consensus and |consensus|
  - number of books
  - mean and max absolute deviation from the consensus
  - range
  - the signed deviation of the most outlying book
- **Movement:**
  - 6 h and 24 h consensus moves, plus their magnitudes
  - consensus changes in the last 48 h
  - the totals consensus move over 24 h
- **Staleness:** the median time since the books last changed their quote.
- **Key numbers:** distance to 3 and to 7, an on-key flag, a half-point flag.
- **Context:** hours to kickoff, weekday (US Eastern), Pinnacle − consensus (imported weeks only), source.

The headline "will it move" model uses only features available in both sources, so it can run on live data. Pinnacle is tested as an ablation.

### Models

- constant (train + validation base rate)
- recent-week base rate
- smoothed rate by time to kickoff
- volatility heuristic
- standardized L2 logistic regression: median imputation with missing-value indicators; C chosen on validation log loss; refit on train + validation

**Direction-target baselines:** constant, the outlier-direction rule, and the momentum rule.

### Results (test week 5, scored once; 95% CIs resample games)

| Target                                      | Model                  | Brier     | Log loss  | AUC                  | vs constant                                                             |
| ------------------------------------------- | ---------------------- | --------- | --------- | -------------------- | ----------------------------------------------------------------------- |
| Move ≥ 0.5 in 24 h (22.7% positive)         | constant               | 0.182     | 0.560     | 0.50                 | —                                                                       |
|                                             | recent-week rate       | 0.179     | 0.547     | 0.50                 | Δ log loss −0.013 (−0.027 to +0.001)                                    |
|                                             | **logistic**           | **0.162** | **0.498** | **0.72 (0.57–0.86)** | Δ log loss −0.062 (−0.148 to +0.009); Δ Brier −0.021 (−0.051 to +0.004) |
|                                             | logistic + Pinnacle    | 0.159     | 0.490     | 0.74 (0.59–0.87)     | Δ log loss −0.071 (−0.165 to +0.010)                                    |
| Direction, given a move (60.8% toward home) | constant               | 0.265     | 0.722     | 0.50                 | —                                                                       |
|                                             | outlier-direction rule | 0.263     | 0.721     | 0.56                 | indistinguishable                                                       |
|                                             | logistic               | 0.250     | 0.693     | 0.54                 | indistinguishable                                                       |
|                                             | logistic + Pinnacle    | 0.227     | 0.753     | 0.75 (0.58–0.89)     | lower Brier, higher log loss (overconfident); CIs include 0             |

**Verdict under the pre-registered rule:** a model beats a baseline only if both the Brier and the log-loss difference CIs lie entirely below zero.

- **Will it move: not yet established.**
  - Logistic regression clearly _ranks_ snapshots: its AUC CI excludes 0.5.
  - It improves every point estimate, most of all 120 h or more before kickoff (Brier 0.20 vs 0.26).
  - It is under-calibrated on the test week, because the base rate rose by week (9% in Week 1 → 23% in Week 5).
- **Direction: no detectable skill on this test week.**
  - The outlier study's aggregate finding (63% of consensus moves go toward a diverging book) does **not** turn into per-snapshot directional skill here.
  - The Pinnacle variant's ranking signal (AUC 0.75) is suggestive, but it is overconfident and not significant.

**Most informative features** (standardized coefficients): recent 24 h movement, cross-book range and mean deviation, totals movement, and a missing 6 h lag (often a market's first snapshot with three books). Lower probability goes with half-point lines and longer-unchanged quotes.

### Missing data

- **Labels:** missing labels are dropped, never imputed.
- **Features:** the lag features are missing when no snapshot lies within ±3 h of the lag. `pinnacle_dev` is structurally missing on live data. The logistic model imputes the median and adds explicit missing-value indicators.

### Limitations, bias and failure modes

- **Small sample:** one season, and a single test week of 15 games. A different week could reverse the point estimates.
- **Non-stationary base rate:** the rate rises as the season progresses, so fixed-rate baselines and the logistic intercept are biased low on later weeks.
- **Source shift:** imported snapshots are derived from change logs and exclude BetMGM. Live snapshots exclude Caesars and Pinnacle, and their timing differs (:07 past the hour). The forward check will measure transfer between the two once 15 live games are labelled.
- **Snapshot resolution:** at about 6-hourly snapshots, a move is known only to have happened within an interval, never at an exact time.
- **Market behaviour ≠ profit:** predicting a line move says nothing about betting value after the vig.

### Next

- Re-run when the forward check reaches 15 live games, and after more weeks, as v2 with rolling-origin evaluation.
- Phase 10 (MS-036) added football features and measured their lift against this baseline; see section 1b.

## 1b. Market-movement model with football features (MS-036, 2026-10-19)

- **Design:** pre-registered in `research/src/marketscope_research/ml/design_football.py` (9c3ef34 on `main`; first pushed as 85fd030 in PR #46), committed before any feature was built. Same target, split, C grid, bootstrap and claim rule as v1.
- **Report:** `research/reports/market-football-v1.md`.
- **Features, point in time at each snapshot t** (a unit test perturbs every input usable after t and checks that nothing changes):
  - **Ratings:** gap between the rating margin and the consensus margin, from the latest ratings-v1 snapshot usable at t. Rating terms only: injury and QB terms come from reports published during the week.
  - **Injuries:** starters (≥ 50% share over recent games) who played < 25% of snaps in their team's latest game, from snap counts at least 36 h old. Live injury statuses only start in week 6, so they can't train a model on weeks 1–4.
  - **Weather:** wind at the shortest usable forecast lead, the change since the previous lead, and an outdoor flag.
  - **Schedule:** rest difference, away travel, short week.

**Results** (test week 5, football model minus the v1 market-only model, paired by game):

| Target                           | Δ Brier                      | Δ log loss                | Verdict |
| -------------------------------- | ---------------------------- | ------------------------- | ------- |
| Will it move (≥ 0.5 pts in 24 h) | +0.0011 (−0.0015 to +0.0039) | +0.002 (−0.007 to +0.011) | no lift |
| Direction, given a move          | +0.0373 (+0.0045 to +0.0776) | +0.081 (+0.010 to +0.172) | worse   |

- **Direction:** 152 training rows from 32 games; the signed injury and rest features overfit.
- **Exploratory:** the injury family alone in the will-it-move model came closest to helping, Δ Brier −0.0025 (−0.0052 to 0.0000).
- **Forward check:** pending, with 13 and 6 labelled live games (needs 15).

**What it means:** with one season of odds history (a 15-game test week), football features do not detectably improve line-move prediction. This matches R4 and R2h, which found the closing market already prices this information. Re-run as v2 with rolling-origin evaluation when more live weeks exist; the live injury snapshots can then be used directly.

---

## 2. MarketScope Ratings

Designed in `docs/RATINGS.md` (ADR-028); not built yet (Phase 9). This section will hold the ratings model card: margin and total models, win probabilities, the 2025 test, and the 2026 live forward test.
