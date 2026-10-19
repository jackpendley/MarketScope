# MS-035 research studies: pre-registration (2026-10-18)

Committed before any study code was written or any outcome computed. Before writing this, only data
counts were looked at: 79 final 2026 games with odds history from at least 6 days out; 534 final
games (2024–26) with a 1-day forecast and an nflverse closing total; nflverse closes for 267–285
games per season 2016–25; one live injury snapshot (2026-10-18). Known going in: the full ratings-v1
model's probability of covering the closing line scored worse than a coin flip on 2023–24 and 2025
(MS-032a/b), so R4 is expected to be null.

**Common rules.**

- Every study reads the database only (`data.py` opens a read-only session).
- **Seasons:** 2016–24 for anything using MarketScope Ratings. 2025 is the untouched test season of
  ratings-v1 and is not used in any rating-based analysis. Studies that use no model output (R1, R3)
  may use 2025–26.
- **Point in time:** ratings come from the snapshot after the previous week (week 1 uses the
  preseason snapshot, week 0). Forecasts must have been issued before kickoff. Odds snapshots are
  pregame.
- **Inference:** 95% bootstrap intervals with 5,000 resamples of **games** (seed 2026), plus HC1
  standard errors for regressions. A claim needs its interval to exclude zero in the stated
  direction. Everything else is reported as "not distinguishable from zero", and nulls are
  published.
- **Gates:** a study whose sample fails its gate is reported as inconclusive, with its counts.
- **Multiple comparisons:** each study has one primary hypothesis (marked **primary**). Secondary
  results are labelled exploratory. No correction is applied; the number of tests is visible.
- **Orientation:** margins are home minus away. close margin = −(nflverse home closing spread).
  consensus margin = −(board consensus home spread). ATS residual = actual margin − close margin.

## R1: market accuracy over time (2026 odds)

- **Question:** how much more accurate is the consensus close to kickoff than a week out? Is any
  book's closing line more accurate than the consensus?
- **Games:** final 2026 regular-season games linked to an odds event, with pregame home spreads from
  one source (live collection or the OddsPapi backfill).
- **Consensus:** board consensus (median of current board books, at least 3) per snapshot
  (`consensus.py`). Leads: **6 days** and **3 days** (snapshot nearest kickoff − lead within
  ±12 h), **1 day** (±6 h), and the **close** (last pregame snapshot within 6 h of kickoff). A game
  needs all four.
- **Metric:** MAE of the consensus margin vs the actual margin.
- **Primary:** MAE(6 days) − MAE(close), paired by game. Claim "the consensus became more
  accurate" if its interval lies above 0. Also reported: 3 days − close, 1 day − close, and the
  nflverse close on the same games (a labelled benchmark).
- **Books (exploratory):** each board book's home spread in the close snapshot, MAE vs result,
  paired against the consensus on the games it quoted (at least 40 games). Expected: no book
  distinguishable from the consensus.
- **Gate:** at least 60 games with all four leads.

## R2: injury-news event study (2026 live, deferred)

- **Event:** a player newly listed **Out** in a live injury snapshot (the previous live snapshot did
  not list him Out) at least 24 h before kickoff, who is the team's expected starting QB or averaged
  at least 50% of offensive or defensive snaps over the team's previous 3 games.
- **Outcome:** board consensus margin change from the last snapshot before the injury snapshot's
  `first_seen_at` to (a) the first snapshot at least 6 h later and (b) the close. Oriented so
  positive = toward the injured team's opponent.
- **Baseline:** the same-window consensus change in games without such an event.
- **Primary:** mean oriented move for QB events vs the baseline; non-QB events reported separately.
- **Gate:** at least 30 events (at least 10 QB events for the QB claim). Run once the live injury
  history allows; until then, inconclusive.

## R3: weather and totals (2024–26)

- **Games:** final games with an Open-Meteo forecast at **1-day lead** for the kickoff hour
  (outdoor and open-roof venues only; domes and retractable roofs excluded by design) and an
  nflverse closing total.
- **Primary (pricing):** OLS of the total residual (actual total − closing total) on forecast wind
  (mph). "Wind is under-priced" if the slope's interval lies below 0; "over-priced" if above 0.
  Also mean residual by wind bucket (< 10, 10–15, ≥ 15 mph).
- **Exploratory (market response):** OLS of the closing total on forecast wind with season fixed
  effects (how far the market moves totals per mph). Precipitation is reported descriptively.
- **Exploratory (movement, 2026 odds):** games whose forecast crossed 15 mph between the 3-day and
  1-day leads vs all others; board totals consensus change from 3 days out to the close. Gate: at
  least 15 crossing games.
- **Gate (primary):** at least 200 games and at least 30 games with wind ≥ 15 mph.

## R4: is performance priced? (2016–24)

- **Games:** regular-season games with an nflverse close and a result.
- **Rating margin:** home AdjEM − away AdjEM (ratings-v1 snapshot after the previous week) + 1.6
  points at non-neutral sites (the ratings-v1 home advantage, RATINGS.md). gap = rating margin −
  close margin.
- **Primary:** OLS of the ATS residual on the gap. Slope > 0 means the ratings carry information
  beyond the close. Claim "performance is not fully priced" if the slope's interval lies above 0
  **and** the slope is positive in at least 6 of 9 seasons. Also reported: 2023–24 alone
  (out-of-sample for the fitted rating parameters).
- **Exploratory (closing move, 2026 odds):** OLS of the consensus move (close − 6 days, margin
  orientation) on the gap at 6 days (rating margin − 6-day consensus margin). Slope > 0 means the
  market moves toward the ratings. Gate: at least 60 games. 2026 uses ratings-v1 live snapshots
  (point in time), not the 2025 test season.

## R5: luck regression (2016–24)

- **Games:** regular-season games from week 5 on, with an nflverse close and a result.
- **Luck difference:** home luck − away luck (wins minus expected wins, snapshot after the previous
  week).
- **Primary (market):** OLS of the ATS residual on the luck difference. Claim "the market overrates
  lucky teams" if the slope (points per win of luck) has an interval below 0.
- **Exploratory (ratings):** OLS of the rating residual (actual − rating margin) on the luck
  difference. Expected ≈ 0, because the ratings ignore wins and losses.
- **Exploratory (persistence, team-seasons):** luck after week 9 vs luck gained from week 10 to the
  end of the regular season. "Luck persists" if the slope's interval lies above 0 (bootstrap over
  team-seasons).

## R6: model + market blend (2023–24, deferred)

- **Blend:** p = w · p_model + (1 − w) · p_close (no-vig), with w set each week from the trailing
  four weeks' relative Brier (nfelo style; the market weight never below 0.40).
- **Primary:** Brier(blend) − Brier(close) on 2023–24 walk-forward predictions. Claim "the blend
  beats the close" if the interval lies below 0. Research only: never in the displayed rating.

## R7: play-caller impact (2016–24, deferred)

- **Carryover:** team-season pairs; OLS of next season's end-of-season offensive points-per-drive
  unit on this season's, with interactions for same offensive play-caller and same starting QB.
  **Primary:** the same-play-caller interaction, holding the QB fixed. Claim a continuity effect
  if its interval excludes 0 (bootstrap over team-season pairs).
- **Scheme (exploratory):** whether a play-caller's pass rate over expected and neutral pace follow
  him to a new team (his previous team's values vs the new team's prior values). Coach and roster
  effects are confounded; reported as descriptive.

## Addendum A (2026-10-18): R6 and R7 operational rules

Committed before any R6 or R7 code was written or any outcome computed. These rules fix details the
entries above leave open, and change one thing (the R7 measure, explained below). Looked at before
writing this:

- **Coverage counts:** 2,367 regular-season games 2016–24, all with both starting QBs and 2,366 with
  closing moneylines. 4,734 team-games with drive counts. Play-callers for all 288 team-seasons.
- **Gate re-check:** R2 has one day of live injury snapshots, and R3 has 29 windy games of the 30
  required. Both stay inconclusive.
- **Already known about R6:** on 2023–24 the model alone is less accurate than the close.
  benchmarks.md and factor-selection.md report its Brier and log loss against the close. The blend
  has never been computed.
- **Already known about R7:** the fitted ratings-v1 reversion between seasons is higher when the
  offensive play-caller stays than when he changes: points per drive 0.64 vs 0.46, pass offense
  0.72 vs 0.58 (params.json, fitted 2016–22).

### R6: model + market blend

- **Predictions:**
  - Frozen ratings-v1 (the params hash is checked).
  - Run walk-forward through the eval harness for 2022–24. The runner stops after 2024, so it never
    sees 2025.
  - 2022 is used only to fill the trailing window for early 2023. Scored: every 2023–24 game
    (regular season and playoffs, as in the benchmark table) with a no-vig closing moneyline.
  - **Deviation from the common rules:** R6 reads through the football eval harness, not the
    database. The walk-forward predictions exist only there. The closing moneylines are the same
    nflverse values that `nfl_games` holds.
- **Market probability:** p_close is the no-vig home probability from the nflverse closing
  moneylines. y = 1 for a home win, 0 for a loss, 0.5 for a tie.
- **Weight rule:**
  - Set w for each week slot (season, week) from the games of the previous four slots, taken in
    kickoff order across season boundaries.
  - w is the weight that would have minimised the blend's Brier on those games:
    w = Σ(p_close − y)(p_close − p_model) / Σ(p_model − p_close)²,
    clipped to [0, 0.60] (market weight at least 0.40). w = 0 if the denominator is 0.
  - The slot being predicted never enters its own weight.
- **Primary:** mean over the scored games of (p_blend − y)² − (p_close − y)². Game bootstrap with
  5,000 resamples (seed 2026). Claim "the blend beats the close" if the interval lies below 0.
- **Exploratory:**
  - a fixed w = 0.35 (nfelo's ≈ 65% market weight)
  - the model alone vs the close
  - log loss for all three
  - the path of w by week

### R7: play-caller impact

- **Pairs:** team-seasons (s, s + 1) for s = 2016–23, so s + 1 ≤ 2024. Regular season only.
- **Measure (changed from "end-of-season offensive points-per-drive unit"):** the team's observed
  offensive points per drive for the season (Σ drive points / Σ drives), centred on that season's
  league mean.
  - **Why the change:** the filtered ratings cannot be used. The Kalman filter already reverts a
    rating less between seasons when the play-caller stays (the ρ values above). So next season's
    filtered rating partly carries this season's rating through a continuity-dependent prior, and a
    continuity effect would appear by construction. The observed season figure has no prior in it.
  - **Still not adjusted:** opponents and luck. Both add noise, not bias, with respect to
    continuity.
- **Same play-caller:** the offensive play-caller at the team's last regular-season week of s is
  also the play-caller at week 1 of s + 1 (from `nfl_coaching_staff`; the same definition the
  engine uses).
- **Same QB:**
  - The QB with the most regular-season starts in s also has the most in s + 1.
  - Starts come from `nfl_games` starting QB ids.
  - Ties go to the QB who started later in the season.
- **Model:** y(s+1) = a + b·x(s) + c·C + d·Q + e·x(s)·C + f·x(s)·Q, where C means same play-caller
  and Q means same QB.
- **Primary:** e, the extra carryover when the play-caller stays, holding the QB interaction fixed.
  Claim a continuity effect if its interval (bootstrap over team-season pairs, 5,000, seed 2026)
  excludes 0. Positive means more carryover when the play-caller stays.
- **Gate:** at least 40 pairs with a changed play-caller and at least 40 with a changed QB.
- **Exploratory:**
  - Carryover slopes in the four caller × QB groups (descriptive).
  - The same model for defence: points per drive allowed, and same defensive play-caller, with no
    QB term.
- **Scheme (exploratory):**
  - Movers are play-callers who were the primary offensive caller at team A in s and at a different
    team B in s + 1.
  - For pass rate over expected (PROE) and neutral seconds per play, regress team B's value in
    s + 1 on the caller's team-A value in s and on team B's own value in s. Both are team-season
    means, weighted by plays.
  - A coefficient on the caller's old value that is above 0 means the trait follows the coach.
  - Coach and roster effects are confounded, so this is descriptive.
