# MarketScope Ratings — design (frozen before data)

_Design frozen 2026-10-17 (ADR-028), before any football data was loaded or any parameter fitted. Results sections are added as milestones land; the design sections change only through a new ADR, and the change is recorded in the changelog at the bottom._

MarketScope Ratings is **"KenPom for the NFL"**: opponent-adjusted offensive, defensive and special-teams efficiency, with tempo, luck and strength of schedule, presented the way KenPom presents college basketball. Under the hood it is a dynamic, point-in-time model built on nflverse play-by-play (EPA), with QB, availability, coaching and context layers, evaluated honestly against simple benchmarks and against the betting market.

Ratings are a **model estimate**. They are shown with their measured error and are never a pick or a betting recommendation (CLAUDE.md rules).

## Prior art: how the established models work, and what we take from each

| Model                                                                     | Core design                                                                                                                                                                                                                                | Published parameters / findings                                                                                                                                                                                                                                                                                                                                                               | What MarketScope adopts                                                                                                                                                                           |
| ------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **FiveThirtyEight NFL Elo** (2014–23)                                     | Points-based Elo with a margin-of-victory multiplier. QB adjustment: rolling QB value vs the team's baseline. Season reversion and a Vegas win-total blend                                                                                 | HFA 65 Elo points, later lowered and made venue-specific (~48). Bye +25 Elo. Travel-distance term                                                                                                                                                                                                                                                                                             | Elo as a **benchmark**. The QB-swap idea (compare the starter's rolling value with the team's QB baseline). Travel distance as a candidate factor                                                 |
| **ELWAY** (Nate Silver, 2025–26)                                          | Separate offense and defense ratings, not zero-sum. 2026 version uses points per drive from 7 components. QBERT QB model. WAR-based injuries. Coaching effect. Roster-based preseason prior. Full-tiebreaker simulation                    | 1 pt ≈ 21.5 Elo. HFA 1–3.5 pts, +0.75 in playoffs. Bye ≈ +1 pt, +0.3 pt per extra rest day. QB ≈ 30% of player value. **Questionable QB plays ~70%, doubtful ~7%.** Non-QB injuries 0.5–1 pt typical, max ~2. New coach negative for ~10 games. Rookie QBs improve over ~20 starts. Wind lowers totals. Clinched teams rest QBs in Week 18 ~⅔ of the time. Prior = 50/50 last season / roster | Separate offense and defense ratings. **Probabilistic availability by injury status.** Rookie-QB curve. Coaching-change factor. Week-18 rest flag. Its parameters become **our comparison table** |
| **nfelo** (open source, `greerreNFL/nfelo`, config v4.3.1)                | Elo updated from a blend of margin, WEPA (weighted EPA), DVOA and PFF signals. 538-style QB model. **Regression toward the market**, weighted by trailing model-vs-market error                                                            | k ≈ 9.1, between-season reversion ≈ 0.53, margin weight 0.74, WEPA 0.15. Market-regression floor 0.40; ~65% market weight optimal. The model alone loses slightly to the market; model + market beats it on Brier                                                                                                                                                                             | Using **several efficiency signals** (not just score). The **model + market blend as a research study** (the displayed rating stays pure performance)                                             |
| **ESPN FPI**                                                              | Points above average built from opponent-adjusted offense, defense and special-teams EPA per play. Trash time removed. QB adjustment (QBR-like, aging curve, rookies at replacement level). Extreme plays capped. Season simulated 10,000× | Data from 2006. Offense more stable than defense. NFL strength of schedule ≈ 1 win per season                                                                                                                                                                                                                                                                                                 | The rating scale (**points vs average on a neutral field**). Capping extreme plays. Replacement-level rookies. Offense/defense stability asymmetry                                                |
| **DVOA / DAVE** (FTN)                                                     | Each play vs the league baseline for its situation. Opponent-adjusted. DAVE blends the preseason projection early in the season                                                                                                            | —                                                                                                                                                                                                                                                                                                                                                                                             | Opponent adjustment per play. **Prior weight decays as the season accumulates plays** (the DAVE idea). DVOA itself is proprietary, so EPA replaces it                                             |
| **KenPom** (college basketball)                                           | Tempo-free adjusted offensive and defensive efficiency vs average opposition at a neutral site. Adjusted tempo. Pythagorean win% (exponent 10.25). Log5 matchup odds. **Luck** = actual win% − expected win%                               | —                                                                                                                                                                                                                                                                                                                                                                                             | The presentation: adjusted offense, defense and pace with ranks. A **luck** column. Time travel to any past week                                                                                  |
| **Inpredictable GPF**                                                     | **Market-implied ratings**: weighted least squares on point spreads gives Generic Points Favored, split into offense and defense using totals                                                                                              | The market updates team views ~15% after each result. HFA ≈ 2 pts                                                                                                                                                                                                                                                                                                                             | **Market-implied ratings** from the nflverse close (history) and our consensus (2026), compared with MarketScope ratings                                                                          |
| **Glickman & Stern (1998)**, Lopez et al. (2018), Stan re-implementations | **Bayesian state-space**: team strength follows an AR(1) process week to week, with extra season-to-season variance and reversion. Fit on margins, or on betting lines                                                                     | Comparable to betting lines in their era. NFL strength autocorrelation has fallen over time. **Rest study (arXiv 2408.10867): the bye edge was ~2.2 pts before the 2011 CBA and ≈ 0 since**                                                                                                                                                                                                   | **Core architecture**: a state-space / Kalman filter over unit strengths (below). Rest effects are **estimated, not assumed**                                                                     |
| **nflseedR** (nflverse, R)                                                | Season simulation with NFL tiebreakers to depth 3 (through strength of schedule)                                                                                                                                                           | —                                                                                                                                                                                                                                                                                                                                                                                             | The **reference for tiebreaker logic** if we build the simulation (MS-034)                                                                                                                        |

**Takeaways that shape our design:**

- Every strong system uses efficiency rather than results, adjusts for opponent, separates the QB, regresses toward a prior, and carries uncertainty.
- The best accuracy comes from blending with the market. We publish that as research, not in the displayed rating.
- Small effects (rest, travel, coaching) are inconsistent across systems. We estimate them ourselves and keep only those that improve validation.

---

## North star: "KenPom for the NFL" (the output contract)

The target is a KenPom-style system. The engine below can be modern (a Kalman filter), but **what users see, and how it reads, mirrors KenPom**, mapped from college basketball to the NFL.

### How KenPom's pieces map to the NFL

**Core ratings**

| KenPom                                                                       | MarketScope (NFL)                                                    | Definition                                                                                                                |
| ---------------------------------------------------------------------------- | -------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------- |
| **AdjO**: points per 100 possessions vs an average D-I defense, neutral site | **AdjO**: points per drive vs an average NFL defense, neutral site   | Built from luck-adjusted, opponent-adjusted EPA, so it is "expected points per drive". The drive is the NFL's possession. |
| **AdjD**                                                                     | **AdjD**: points per drive allowed vs an average offense             | Lower is better, as in KenPom.                                                                                            |
| **AdjT**: possessions per 40 minutes vs an average-tempo opponent            | **AdjPace**: drives per game, and neutral seconds per play           | Opponent-adjusted. Feeds the totals.                                                                                      |
| **AdjEM** = AdjO − AdjD; teams are ranked by it                              | **AdjEM**: net points per game vs an average team on a neutral field | (AdjO − AdjD) × league drives per game + **AdjST**. The table is ranked by AdjEM.                                         |
| _(KenPom has no special teams)_                                              | **AdjST**: special-teams points per game vs average                  | NFL-specific column; heavily shrunk because it is noisy.                                                                  |

**Luck and strength of schedule**

| KenPom                                                             | MarketScope (NFL)                         | Definition                                                                                                                                                                                                                                   |
| ------------------------------------------------------------------ | ----------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Luck**: actual win% − win% expected from game-by-game efficiency | **Luck**: actual wins − **expected wins** | Expected wins = Σ over games of P(win \| that game's opponent-adjusted efficiency margin). The logistic fit is done on 2016–22. Also shown: **Pythagorean wins** (points-based, NFL exponent ≈ 2.37, refit).                                 |
|                                                                    | **Luck decomposition** (team page)        | Separates the luck into: one-score game record vs expected, fumble-recovery luck, opponent and own FG/XP luck, interception luck (INTs vs expected from passes defensed/thrown), and return-TD luck. KenPom shows one number; we show _why_. |
| **SOS AdjEM**: average AdjEM of opponents                          | **SOS** (games played)                    | Average _current_ AdjEM of opponents faced, adjusted for venue.                                                                                                                                                                              |
| **Opp O / Opp D**                                                  | **Opp AdjO / Opp AdjD**                   | Average current AdjO and AdjD of opponents faced.                                                                                                                                                                                            |
| **NCSOS** (non-conference SOS)                                     | **Non-division SOS**                      | The NFL analog.                                                                                                                                                                                                                              |
|                                                                    | **Remaining SOS**                         | Average AdjEM of opponents still to play (KenPom shows this implicitly through projected records).                                                                                                                                           |
|                                                                    | **Strength of opponent, per game**        | Opponent's AdjEM and rank _at the time of the game_ and _now_, shown in each game log row.                                                                                                                                                   |

**Four Factors, Pythag and preseason**

| KenPom                                                                      | MarketScope (NFL)                                                          | Definition                                                                                                                                                                                                                                                                     |
| --------------------------------------------------------------------------- | -------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Four Factors** (eFG%, TO%, OR%, FT rate), offense and defense, with ranks | **"Five Factors" of football** (Connelly), offense and defense, with ranks | Efficiency (success rate), explosiveness (EPA per successful play), field position (average starting yard line), finishing drives (points per trip inside the 40), and turnovers (margin and luck-adjusted). Also pass/rush EPA splits, early-down EPA, PROE, sack rate, CPOE. |
| **Pythag / log5**: win probability vs an average team                       | **Win% vs average**, and model win probability for any pairing             | Computed from the key-number-aware margin distribution.                                                                                                                                                                                                                        |
| Preseason ratings that fade as games accumulate                             | Preseason prior that fades as data arrives                                 | The Kalman season-boundary reversion. The prior's weight decays automatically. The team page shows "% of rating from prior".                                                                                                                                                   |
| Diminishing returns for blowouts                                            | Win-probability-leverage weighting, plus a cap on extreme plays            |                                                                                                                                                                                                                                                                                |
| Slight recency weighting                                                    | Week-to-week process noise                                                 | Learned, not hand-set.                                                                                                                                                                                                                                                         |
| Per-team home-court advantage                                               | Venue-specific HFA, shrunk toward the league HFA                           | Kept only if it earns its place.                                                                                                                                                                                                                                               |

**Predictions and the time machine**

| KenPom                                                                                | MarketScope (NFL)        | Definition                                                                                                                                                                                                                                                                                                             |
| ------------------------------------------------------------------------------------- | ------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **FanMatch**: predicted score, win probability and "thrill score" for each game       | **Weekly Matchups page** | Predicted score for **each team**, from AdjO/AdjD/AdjPace/HFA, so the margin and total come out of one structure, exactly as KenPom does. Also win probability, a **game-quality score** (average AdjEM of the two teams), an **excitement score** (expected closeness × quality), and the market consensus beside it. |
| Team schedule page with win probabilities for future games and a **projected record** | **Team page**            | Results with game grades. Future games with win probability. Projected record as a distribution.                                                                                                                                                                                                                       |
| Archive: ratings as of any date                                                       | Week selector            | Filtered (point-in-time) snapshots for every week since 2016.                                                                                                                                                                                                                                                          |

### Classic KenPom math as an explicit benchmark

`kenpom_classic.py` implements the original iterative adjustment, AdjO_game = RawO × (league average / Opp AdjD), iterated to convergence with recency weights.

- It runs alongside the Kalman engine, so RATINGS.md can show the two produce near-identical rankings.
- It also shows where the Kalman engine improves on the classic method: uncertainty, point-in-time behavior and prior fading.
- This makes the method easy to explain to someone who knows KenPom.

---

## Factor catalog (every candidate, its point-in-time source, and its status)

**How a factor earns its place:**

- **v1:** in the base model.
- **Test:** added through an ablation on 2023–24 validation. It is kept only if it improves margin MAE or log loss beyond noise (game-clustered CI).
- **Display:** shown in the UI but not modeled.
- **Research:** a study, not a model input.

This rule is what stops ~2,800 training games from being overfit by 40 factors.

| Group                                                                   | Factor                                                                                                                                                                                                 | Source (point-in-time)               | Status                                                      |
| ----------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------ | ----------------------------------------------------------- |
| **Unit strength**                                                       | Pass and rush offense/defense, luck-adjusted, WP-weighted EPA/play                                                                                                                                     | play-by-play, games final before t   | v1                                                          |
|                                                                         | Success rate, early-down EPA (more stable than 3rd down / red zone)                                                                                                                                    | play-by-play                         | v1, as extra observation channels                           |
|                                                                         | Explosive-play rate, sack rate (pressure, partly QB-independent)                                                                                                                                       | play-by-play                         | test                                                        |
|                                                                         | Special teams: FG/XP vs expected, punt and kick net EPA, return EPA                                                                                                                                    | play-by-play                         | v1, heavily shrunk                                          |
|                                                                         | Turnovers: interceptions shrunk toward expected; fumble recoveries set to expected                                                                                                                     | play-by-play                         | v1 (luck adjustment)                                        |
|                                                                         | Penalties and discipline, starting field position                                                                                                                                                      | play-by-play                         | test                                                        |
| **QB**                                                                  | Starter value: EPA/dropback + CPOE composite (the most predictive public QB metric), shrunk toward an experience prior                                                                                 | play-by-play                         | v1                                                          |
|                                                                         | Expected starter at t: last starter unless Out/Doubtful, then next on the depth chart                                                                                                                  | injury reports, depth charts         | v1                                                          |
|                                                                         | **P(plays \| status)**, estimated from history (injury status joined to snaps > 0) by position. ELWAY reference: Q ≈ 70%, D ≈ 7%                                                                       | injuries + snaps                     | v1                                                          |
|                                                                         | Rookie / early-career improvement curve (~20 starts)                                                                                                                                                   | play-by-play                         | test                                                        |
| **Availability**                                                        | Snap-share-weighted absences by group (OL, WR/TE, RB, front 7, secondary) × learned positional value; expected value over P(plays)                                                                     | injuries + snaps                     | v1                                                          |
|                                                                         | Non-linear OL / secondary cluster injuries (≥ 2 starters out in one group)                                                                                                                             | same                                 | test                                                        |
|                                                                         | Players returning from IR / reserve                                                                                                                                                                    | weekly rosters                       | test                                                        |
| **Context**                                                             | Home-field advantage by season (declined after 2020)                                                                                                                                                   | schedule                             | v1                                                          |
|                                                                         | Venue-specific HFA (Denver altitude, dome, crowd), shrunk toward league HFA                                                                                                                            | schedule + stadiums                  | test                                                        |
|                                                                         | Rest difference, bye, mini-bye, Thursday short week (bye edge ≈ 0 after 2011)                                                                                                                          | schedule                             | test                                                        |
|                                                                         | Travel distance, time-zone shift, body clock (West team at 1pm ET; night games)                                                                                                                        | stadium coordinates                  | test                                                        |
|                                                                         | Neutral / international site                                                                                                                                                                           | schedule                             | v1                                                          |
|                                                                         | Division game (familiarity → smaller margins?)                                                                                                                                                         | schedule                             | test                                                        |
|                                                                         | Back-to-back road games; "lookahead/letdown" spots                                                                                                                                                     | schedule                             | research (expected null)                                    |
| **Environment**                                                         | Forecast wind > 15 mph, precipitation, temperature; dome team in cold                                                                                                                                  | Open-Meteo forecasts issued before t | v1 for totals, test for margin                              |
|                                                                         | Roof (retractable = unknown pre-game), surface (turf/grass)                                                                                                                                            | stadium                              | test                                                        |
| **Coaching / scheme**                                                   | New head coach (first ~10 games), in-season coach change                                                                                                                                               | nflverse coach fields in schedules   | test                                                        |
|                                                                         | **Who calls the plays.** Offensive and defensive play-callers, HC/OC/DC by season, plus mid-season changes                                                                                             | Curated `nfl_coaching_staff` (below) | v1 for the prior and process noise; test as a direct factor |
|                                                                         | **Play-caller continuity → carryover.** Offensive carryover between seasons depends on the same offensive play-caller _and_ the same QB. Defensive carryover depends on the same defensive play-caller | coaching staff + QB state            | v1 (conditions ρ_s; effect sizes estimated)                 |
|                                                                         | **Mid-season play-calling change → faster adaptation.** Extra Kalman process noise for that unit in the week of the change                                                                             | coaching staff, effective week       | v1                                                          |
|                                                                         | **Play-caller scheme fingerprint.** PROE, neutral pace, shotgun and no-huddle rates, 4th-down aggressiveness, early-down pass rate. These follow the coach to new teams                                | play-by-play × coaching staff        | v1 for totals and pace priors; research for margin          |
|                                                                         | Pass rate over expected, neutral pace (feed totals and variance)                                                                                                                                       | play-by-play                         | v1 for totals                                               |
|                                                                         | 4th-down aggressiveness (go rate vs recommendation)                                                                                                                                                    | play-by-play                         | test (totals / variance)                                    |
| **Season state**                                                        | Week 18: clinched or eliminated teams resting starters                                                                                                                                                 | standings at t                       | test, with an explicit flag                                 |
|                                                                         | Playoffs (HFA + 0.75 per ELWAY)                                                                                                                                                                        | schedule                             | test                                                        |
| **Officiating**                                                         | Referee crew penalty and total tendencies                                                                                                                                                              | officials (2015+)                    | research                                                    |
| **Market** (research and market ML only, never in the displayed rating) | Market-implied ratings, line movement, Pinnacle − board, divergence                                                                                                                                    | odds observations, nflverse close    | research / Phase 10                                         |
| **Variance**                                                            | Team-specific margin variance (high-variance teams help underdogs)                                                                                                                                     | play-by-play                         | research                                                    |

---

## Model architecture — MarketScope Ratings v1

**1. Measurement layer (one row per game per team).**

- For each game and unit, compute observation channels: luck-adjusted, WP-weighted, extreme-play-capped EPA/play; success rate; early-down EPA.
- Pass and rush are measured separately. Each channel carries its play count, which sets its observation noise.

**2. State layer: a dynamic opponent-adjusted Kalman filter (Glickman–Stern style).**

- The latent state per unit is a vector of 32 offense + 32 defense strengths.
- Each game observes y = off_A − def_B + hfa_season + ε, with noise variance proportional to 1/plays. **Opponent adjustment happens inside the filter**, because every observation links two teams.
- **Week-to-week evolution:** state = ρ_w·state + process noise q_unit.
- **Season boundary:** state = ρ_s·state + larger noise q_season. This reversion is the prior, and its weight decays automatically as data arrives (the DAVE behavior).
  - ρ_s depends on continuity: same offensive play-caller and same QB for offense; same defensive play-caller for defense.
  - A play-caller change mid-season adds a one-time process-noise bump to that unit, so the rating adapts faster.
- Per-unit parameters (ρ_s, q_unit, q_season, the channel weights) are fit by **maximum likelihood on 2016–2022**. This gives the stability asymmetry (offense > defense > special teams) as a _finding_ rather than an assumption.
- **Filtered vs smoothed:**
  - _filtered_ estimates use data up to t: point-in-time, used for every prediction
  - _smoothed_ estimates (RTS) use the whole season: hindsight, used only for retrospective "true strength" charts
  - This is a clean, explainable leakage lesson.
- **Uncertainty:** the filter's covariance gives ± ranges for every rating at every week.
- Implemented directly in numpy, which is small and explainable. A Stan version is optional research.
- **Benchmark ablation:** ridge regression with an exponential half-life, in place of the filter.

**3. QB and availability layer.**

- Separate QB state: rolling, shrunk EPA+CPOE composite per QB.
- The team's pass-offense strength is decomposed into a QB part and a rest-of-offense part.
- Game adjustment = E[QB value | P(plays)] − the team's baseline QB value, plus the expected-value availability sum over position groups. Positional values are learned on 2016–22.

**4. Game layer.**

- Home margin = β·(unit matchups: pass offense vs pass defense, rush vs rush, special teams vs special teams) + HFA + QB/availability + every _test_ factor that earned its place.
- Regularized linear, so contributions are additive and **every prediction can be explained as a waterfall**, e.g. "ratings +2.0, HFA +1.4, QB out −1.8 …".
- **Total** = offense/defense points + pace + PROE + weather + roof.
- **Probabilities:**
  - an empirical key-number-aware margin distribution conditional on the expected margin (fit on 1999–2015, outside every evaluation season) → win probability, P(margin > −line), and P(total > line)
  - ties around 0.5%

**5. Rating scale.** Ratings are published in the KenPom contract above: AdjO and AdjD in points per drive, AdjPace, AdjST, and AdjEM in points per game. Each comes with ± SE and a rank.

- Luck and SOS are computed from the same snapshots.
- Neither feeds the predictions. Luck is descriptive, because the ratings already ignore win/loss outcomes. SOS is already handled by the opponent adjustment.

**6. Market-implied ratings (Inpredictable style).**

- A weekly weighted least-squares fit of spreads (and totals, for the offense/defense split) on team indicators + HFA.
- Inputs: the nflverse close for history, our consensus snapshots for 2026, giving a time series of the market's view of each team.

**Validation protocol (frozen in `docs/RATINGS.md` before any tuning):**

- Walk-forward, week by week.
- Season roles:
  - 2016–2022: fitting and tuning
  - 2023–24: validation and factor selection
  - **2025: untouched test, evaluated once, logged in `model_runs`**
  - **2026: live forward test** with immutable pre-kickoff `model_predictions`
- Metrics, each with a game-clustered bootstrap CI:
  - margin and total MAE/RMSE
  - Brier and log loss for win probability vs no-vig market probabilities
  - reliability curves
- Benchmarks: naive HFA, SRS, Elo (538-style), market-implied ratings, the nflverse close, and our last-pregame consensus.
- Optional extra benchmark: 538's published `nfl-elo` CSVs (CC-BY) for 2016–22.
- **Parameter comparison table:** our fitted HFA, rest/bye, travel, reversion, QB share, P(plays | Q/D), coaching effect and wind effect, next to the published 538, ELWAY, nfelo and Inpredictable values. This is a headline result.
- **Expected outcome, stated up front:** the model beats SRS and Elo and loses to the close. The interesting findings are which components matter, where performance and price disagree, and whether those disagreements carry information.

### Factor selection (pre-registered 2026-10-18, before any candidate was fitted)

The rule and candidate list are in `apps/football/src/marketscope_football/ratings/selection_design.py`. Each candidate is added on its own to the MS-031 model's game layer. It is kept only if both:

1. its 2016–22 coefficient has the expected sign with |t| ≥ 2, and
2. on 2023–24, paired against the MS-031 model, Δ margin MAE ≤ 0 and Δ log loss ≤ 0.

**Candidates:**

- rest difference
- bye week
- travel distance
- time-zone shift
- body clock
- altitude
- division game (smaller home edge)
- playoffs (larger home edge)
- new head coach (first 10 games)
- new offensive play-caller (first 4 games)

The RB absence value stays only if it passes the same rule. Margin weather is not testable (forecasts start in 2024).

Kept factors are refitted jointly, and that model is frozen as `ratings-v1`. Its 2023–24 score is optimistic by construction, so the one-time 2025 test is the honest estimate.

## References

- nflverse / nflreadpy data and licences: https://nflreadpy.nflverse.com/ (CC-BY 4.0; FTN data CC-BY-SA 4.0)
- Open-Meteo Previous Runs / Historical Forecast APIs: https://open-meteo.com/en/docs/historical-forecast-api (CC-BY 4.0)
- ELWAY methodology: https://www.natesilver.net/p/how-our-elway-forecasts-work-methodology
- FiveThirtyEight NFL Elo: https://fivethirtyeight.com/methodology/how-our-nfl-predictions-work and https://github.com/fivethirtyeight/nfl-elo-game
- nfelo: https://github.com/greerreNFL/nfelo and https://nfeloapp.com/analysis/using-market-regression-to-improve-prediction-accuracy-in-the-nfl
- ESPN FPI: https://africa.espn.com/nfl/story/_/id/13539941/how-espn-nfl-football-power-index-was-developed-implemented
- KenPom: https://kenpom.com/blog/ratings-explanation/ and https://kenpom.com/blog/ratings-glossary/
- Inpredictable: https://inpredictable.com/p/methodology.html
- State-space team strength: Glickman & Stern (1998, JASA); Lopez, Matthews & Baumer (2018), https://arxiv.org/abs/1701.05976
- Rest differential: https://arxiv.org/abs/2408.10867
- nflseedR (tiebreakers): https://cloud.r-project.org/web/packages/nflseedR/index.html

---

## Results

_Each milestone appends its tables here: benchmarks (MS-029), Kalman parameters and ablations (MS-030), QB and availability (MS-031), factor selection, 2025 test, parameter comparison (MS-032)._

### Benchmarks (MS-029)

Walk-forward on the 2023–24 validation seasons (570 games, regular season and playoffs). 95% bootstrap CIs resample games. Full report: `apps/football/reports/benchmarks.md` (ADR-033).

| Model                                          | Margin MAE | Δ MAE vs close (paired 95% CI) | Brier  | Log loss |
| ---------------------------------------------- | ---------- | ------------------------------ | ------ | -------- |
| naive home field                               | 11.16      | +1.32 (+0.91 to +1.71)         | 0.2481 | 0.6893   |
| Elo (538, published constants)                 | 10.33      | +0.49 (+0.23 to +0.75)         | 0.2230 | 0.6371   |
| SRS (ridge; half-life 126 d, λ 4)              | 10.37      | +0.53 (+0.29 to +0.77)         | 0.2246 | 0.6404   |
| market-implied ratings (half-life 56 d, λ 0.5) | 10.37      | +0.52 (+0.29 to +0.77)         | 0.2231 | 0.6376   |
| nflverse close                                 | 9.84       | –                              | 0.2098 | 0.6081   |

- All five land in the ranges expected before the run (Elo/SRS 10–11, close 9.5–10).
- Ratings fitted to past closing lines are no better than results-based SRS at predicting margins. Most of the close's edge comes from information arriving in the week of the game, not from a better summary of the past.
- Ablations: classic current-season-only SRS is 0.32 worse (CI +0.15 to +0.50), mostly early in the season. Elo's margin-of-victory multiplier helps (+0.17 without it, CI just touching 0). 538's later home-field value (48) is indistinguishable from 65.
- Win probability for margin-based benchmarks: Φ(margin / 11.90), with σ fit on 1999–2015 closing lines.

### Kalman unit ratings (MS-030)

Walk-forward on 2023–24 (570 games), parameters fitted on 2016–22 only (ADR-034). Full report: `apps/football/reports/kalman-ratings.md`.

| Model                        | Margin MAE | Δ vs Elo (paired 95% CI) | Δ vs SRS               | Brier  | Log loss |
| ---------------------------- | ---------- | ------------------------ | ---------------------- | ------ | -------- |
| MarketScope Ratings (Kalman) | 10.33      | +0.00 (−0.20 to +0.21)   | −0.04 (−0.21 to +0.14) | 0.2244 | 0.6411   |
| Elo (538)                    | 10.33      | –                        |                        | 0.2230 | 0.6371   |
| SRS (ridge)                  | 10.37      |                          | –                      | 0.2246 | 0.6404   |
| nflverse close               | 9.84       | −0.49                    | −0.53                  | 0.2098 | 0.6081   |

- **Bar not met.** Unit ratings alone tie Elo and SRS. They win early in the season (weeks 1–4: −0.31 vs SRS, CI −0.61 to −0.00) and are level after.
- **The filter beats a half-life ridge** on the same EPA (+0.17 for the ridge, CI +0.01 to +0.32).
- **Not distinguishable from zero on validation:** the luck, cap and WP-weighting adjustments, each extra channel, and play-caller continuity (likelihood-ratio p = 0.66 in-sample).
- **Stability:** offense carries over more than defense (pass ρ 0.72 vs 0.40), consistent with FPI's offense/defense asymmetry. Within a season, weekly drift is about ⅙ of the spread between teams.

### KenPom contract (MS-030b)

Report: `apps/football/reports/ratings-contract.md` (ADR-035). Stored weekly in `rating_snapshots` from 2016.

- **Luck (2016–22 fits):**
  - Expected wins: logit = 0.60 × home + 0.29 × net adjusted EPA per game.
  - Pythagorean exponent 2.79.
  - League luck sums to 0 in every snapshot.
  - Home teams outscore their scrimmage efficiency by about 1.4 points; that is kept as a home term, not luck.
- **Classic KenPom vs Kalman (Spearman):** about 0.6 at week 4, 0.79–0.90 at week 9, 0.85–0.94 at the end of the regular season.
- **Totals (2023–24):** MAE 10.22: −0.36 vs naive (CI −0.64 to −0.10), +0.26 vs the close (CI +0.04 to +0.48).
- **Model home advantage:** 1.6 points.

### QB layer (MS-031a)

ADR-036. Validation 2023–24 (570 games), run once:

|                                      | Δ margin MAE vs model with QB layer | Δ Brier |
| ------------------------------------ | ----------------------------------- | ------- |
| without the QB layer                 | −0.00 (−0.09 to +0.09)              | +0.0008 |
| actual starter in hindsight (oracle) | −0.08 (−0.20 to +0.02)              | −0.0021 |

- **QB-change games** (87, where a team's expected starter changed or might not play): the QB layer is 0.19 better (CI −0.53 to +0.16). The effect is concentrated where it should be, but there are too few games to show it.
- **Expected starter accuracy:** 92.3% (2016–22), 91.0% (2023–24), 93.1% (2025–26), vs about 88% for "last game's starter".
- **Fitted values:**
  - P(starter plays | Questionable) = 0.64
  - replacement level −0.106 EPA/dropback vs league
  - QB rating half-life 730 days, prior 250 dropbacks
  - game-layer weight 0.51 for the expected starter, 0.89 for the actual starter: the uncertainty about who starts halves the usable signal

### Non-QB availability and the combined model (MS-031b)

ADR-037. Validation 2023–24 (570 games), run once:

| Model                                           | Margin MAE | Δ vs Elo (paired 95% CI) | Δ vs SRS               |
| ----------------------------------------------- | ---------- | ------------------------ | ---------------------- |
| MarketScope Ratings (units + QB + availability) | 10.25      | −0.08 (−0.31 to +0.15)   | −0.12 (−0.31 to +0.08) |
| unit ratings only (MS-030)                      | 10.33      | +0.00                    | −0.04                  |

- **The availability layer** is worth 0.08 (CI −0.00 to +0.17), and the QB layer 0.19 in QB-change games. Neither is yet beyond noise on two seasons.
- **Positional values (points per missing full-time starter):** OL 0.72, WR/TE 0.84, front seven 0.55, secondary 0.57 (ELWAY: 0.5–1 typical). RB 2.41 is noisy (rare absences).
- **The close is still 0.41 ahead** (9.84).

## Changelog

- 2026-10-17: design frozen (ADR-028).
- 2026-10-18: evaluation harness and benchmark results (MS-029, ADR-033). No design change.
- 2026-10-18: Kalman unit ratings (MS-030, ADR-034). Deviations, all decided on 2016–22 before validation:
  - one filter per channel (no cross-channel covariance)
  - points per drive added as a channel
  - game-layer weights by OLS rather than inside the likelihood
  - QB continuity deferred to MS-031
  - filter burn-in from 2012
- 2026-10-18: KenPom contract outputs (MS-030b, ADR-035). Additions to the design: a pace filter (32 units + mean) for AdjPace and totals; expected wins from per-game net adjusted EPA with a home term.
- 2026-10-18: QB layer (MS-031a, ADR-036). QB continuity at the season boundary is handled by the QB feature's baseline rather than by conditioning ρ_s.
- 2026-10-18: non-QB availability (MS-031b, ADR-037).
- 2026-10-18: factor-selection rule pre-registered (MS-032), committed before any candidate was fitted.
