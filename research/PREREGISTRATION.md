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

## Addendum B (2026-10-19): historical injury studies R2h and R2w

Committed before any R2h or R2w code was written or any outcome computed. The live R2 above is
unchanged; it still waits for its gate. These two studies answer the same question with historical
data, which has no record of when a status was first published. Looked at before writing this:

- **Counts for R2w, weeks 2–6 of 2026:** 97 players on a final report as Out who had averaged at
  least 50% of snaps and played the team's previous game. They cover 67 team-games; 6 are QBs.
- **Already known:**
  - R4: rating gaps carry no information beyond the close.
  - MS-031: the QB and availability layers improve the model's margin error.
  - Line moves after the report have never been computed.
- **Coaching data:** these studies come after the MS-035c coaching corrections (ADR-045).

### R2h: are final-report absences priced in the close? (2016–24)

- **Predictions:**
  - Frozen ratings-v1, walk-forward through the football eval harness, scored on 2016–24 regular
    seasons. The runner never sees 2025.
  - This is the same stated exception as R6: the predictions exist only in the harness.
- **Availability adjustment A** (points, home-oriented): the game layer's QB term plus its non-QB
  availability terms (weight × feature) for each game.
  - It is computed from the final weekly injury report and reserve lists. Both are published before
    kickoff, so the close had the same information.
- **Primary:** OLS of the ATS residual (actual margin − close margin) on A. Game bootstrap with
  5,000 resamples (seed 2026).
  - "Absences are under-priced" if the slope's interval lies above 0.
  - "Over-priced" if it lies below 0.
- **Exploratory:**
  - The QB part and the non-QB part as separate regressors.
  - Games with |A| ≥ 2: mean ATS residual in the direction of A.
- **Gate:** at least 1,000 games with A ≠ 0.

### R2w: does the market move on absences during the week? (2026, weeks 1–6)

- **Games:** final 2026 regular-season games with a board consensus 6 days out and at the close.
  These use R1's rules and sources (live collection or the OddsPapi backfill).
- **Event:** a player listed Out on his team's final injury report for the game who:
  - averaged at least 50% of offensive or defensive snaps over his snap rows in the team's previous
    three game weeks, and
  - played (snaps > 0) in the team's previous game, so the absence is news since that game.
  - QB events are those with position QB.
- **Primary:**
  - Game-level OLS of the consensus margin move on N.
  - The move is close − 6 days, home-oriented, in points.
  - N is the away team's event count minus the home team's.
  - Game bootstrap with 5,000 resamples (seed 2026). "The market moves on newly confirmed absences
    during the week" if the slope (points per event) lies above 0.
- **What it can't see:** information already priced 6 days out, such as injuries obvious on the
  previous Sunday.
- **Exploratory:** QB events described separately; a QB claim needs at least 10 QB events.
- **Gate:** at least 30 events in qualifying games.

## Addendum C (2026-10-19): MS-043 sharp-market study S1–S5 (ADR-051, ADR-052)

Committed before any S1–S5 code was written or any outcome computed. Phase 12 asks which market
moves look like sharp action, measured by **closing-line value (CLV)** rather than win/loss.
Looked at before writing this:

- **Counts only:** `line_moves` holds 92 finished 2026 games, kickoffs 2026-09-10 to 2026-10-19 (weeks 1–6), 132,952 rows. Per book: DraftKings 57.8k (24.8k suspensions), Caesars 38.4k, Pinnacle 15.1k, Bookmaker.eu 9.6k, FanDuel 5.0k, Hard Rock 4.0k, Circa 3.0k.
- **Seen while building MS-042:** row counts per game and book, the snapshot cross-check (99.99%
  agreement), and the synthetic demo panel. No real game's lead-lag, steam or CLV has been computed
  or viewed, and no real game's line-move panel has been opened.

**Common rules for S1–S5.**

- **Data:** `line_moves` only (minute-level main lines, ADR-052), read-only. Regular-season 2026
  games with at least one Pinnacle spread row in the 14 days before kickoff.
- **Books:** reference = Pinnacle, Circa, Bookmaker.eu. Retail = DraftKings, FanDuel, Caesars
  (`williamhill_us`), Hard Rock (`hardrockbet`).
- **Point in time:** a decision at time d uses only rows with `changed_at ≤ d`. A book's line at d is
  its latest row at or before d; a row without prices means it is off the board (never "still
  offering the old number").
- **The close:** Pinnacle's line in effect at kickoff (its latest available row before kickoff). A
  game whose Pinnacle spread was off the board for the final 30 minutes is excluded from CLV
  analyses.
- **CLV in points** (spreads and totals), from the bettor's side: home spread bet at line L against
  Pinnacle's closing home line C scores L − C; away = C − L; over = C − L; under = L − C. Positive
  means the bettor got a better number than the close. Price is not converted; S2 and S3 bound it
  instead (below). Half-points differ in value around 3 and 7, so results crossing a key number are
  also reported separately (exploratory).
- **Discovery and confirmation.** Discovery = games kicking off before 2026-10-21 (weeks 1–6, what
  is stored now). **Confirmation = games kicking off from 2026-10-21 to 2026-12-16 (weeks 7–14)**,
  re-run with the same committed code after those games are final and imported. A result counts as established only if its discovery claim holds and the
  confirmation estimate has the same sign with its interval excluding zero. Discovery-only results
  are labelled "discovery".
- **Inference:** 95% bootstrap intervals, 5,000 resamples of **games** (seed 2026), as in MS-035.
  Each study has one **primary** hypothesis; everything else is exploratory. No correction; the count
  of tests is visible. Nulls are published.
- **Language (ADR-051):** results describe timing and CLV. "A reference book moved first" is
  allowed; "sharp money" as a claim about who bet is not. Hypothetical results are labelled.

### S1: who moves first? (lead-lag)

- **Episode:** a spread line change by any book from a to b. Its **pair partners** are the other
  books that make the same change (a → b, same direction) within 60 minutes after it.
- **Pairwise lead:** for each (reference book R, retail book K) pair, count episodes where R moved
  first and K followed within 60 minutes, and episodes where K moved first and R followed.
- **Matching:** each change is matched to at most one change by the other book: the same a → b, the
  nearest in time within 60 minutes (ties go to the earlier one). Changes in the same second count
  for neither book and are reported as a count.
- **Primary:** the share of matched Pinnacle–retail pairs in which Pinnacle moved first, pooled over
  the four retail books (the bootstrap resamples games and recomputes the pooled share). "Pinnacle
  leads retail" if its interval lies above 0.5.
- **Exploratory:** the same share for Circa and Bookmaker.eu; each retail book's median follow time
  after a Pinnacle move (moves not followed by kickoff are censored); by time to kickoff (> 48 h,
  6–48 h, < 6 h) and by size (0.5 vs ≥ 1 point).
- **Gate:** at least 200 Pinnacle–retail pairs.

### S2: stale retail lines (the profitability question)

- **Event:** Pinnacle changes its home spread from a to b. At **d = the Pinnacle change + 60
  seconds**, a retail book is still posting a for the side Pinnacle moved toward (home if b < a, away
  if b > a) at a price of −125 or better. One event per (Pinnacle change, retail book).
- **Precisely:** "still posting a" means the retail book's home line at d equals a and it is on the
  board; "−125 or better" applies to the price of the side bet (−125, −110, +100 and so on qualify;
  −130 does not). Pinnacle changes less than 60 seconds before kickoff are excluded.
- **Hypothetical bet:** that side at that retail book, line a, at time d.
- **Primary:** mean CLV in points of the events. "Stale retail lines carry positive CLV" if its
  interval lies above 0.
- **Exploratory:** how long the stale number stayed available (until the book moved or went off);
  the same with d = change + 5 minutes; by book; moves crossing 3 or 7; totals with the same rule
  (over if Pinnacle raised the total); a hypothetical cover rate against the actual result,
  labelled hypothetical, with the break-even rate at the posted price.
- **Gate:** at least 100 events in at least 30 games.

### S3: steam

- **Definition (fixed here):** at least 3 of the 7 books move their home spread in the same
  direction within 10 minutes, each book counted once. The episode's time is when the third book
  moved; its direction is the side the books moved toward (home if the home line fell, away if it
  rose). Episodes in the same game and direction less than 60 minutes apart are merged (the first
  one stands).
- **Primary (continuation, no execution assumed):** how far Pinnacle's line moves further in the
  steam direction between d = episode time + 60 s and the close, in points (toward home: Pinnacle's
  home line at d minus its closing home line; toward away: the reverse). Episodes where Pinnacle is
  off the board at d are excluded. "Steam continues to the close" if the mean lies above 0.
- **Exploratory:** CLV of betting the steam side at d at the best line among retail books that had
  not yet moved, price −125 or better; whether a reference book was among the first three; totals.
- **Gate:** at least 50 episodes.

### S4: limits (exploratory only)

- Pinnacle spread changes split by whether the reported limit at the new line was above Pinnacle's
  median limit for that game. Outcome: reversal by the close (the closing line back at or beyond a).
  Descriptive; no claim.

### S5: key numbers (exploratory only)

- Pinnacle spread changes that cross or land on 3 or 7 versus others. Outcomes: reversal by the
  close, and how quickly retail books follow (S1's measure). Descriptive; no claim.

**What this can't see.** Who bet or why; Circa limits (not reported); exchange order books (not
stored); moves more than 14 days before kickoff. Points-based CLV ignores price differences beyond
the −125 bound. One season of history (OddsPapi starts in January 2026), so confirmation is forward
only.

## Addendum D (2026-10-19): S2 price split, registered after discovery for confirmation only

Committed after the S1–S5 discovery run (`research/reports/sharp-market-discovery.md`) and before any
week 7–14 game was imported, so it can only be tested on the confirmation sample. The discovery
numbers that motivated it are post hoc and are reported as such.

- **Why:** S2's points CLV is mostly the half-point head start of the old number (+0.54) less
  Pinnacle's partial reversal (−0.10), and points CLV ignores the price paid. In discovery, events at
  standard prices looked better than juiced ones (hypothetical cover 57.9% vs a 52.0% break-even, 628
  bets; 50.5% vs 53.6% for −111 to −125, 822 bets).
- **S2b (confirmation, weeks 7–14):** S2 events whose retail price on the side taken is −110 or
  better. **Primary:** mean CLV in points, game bootstrap (5,000, seed 2026); claim if the interval
  lies above 0. **Secondary:** the mean of (hypothetical cover − break-even at the posted price) per
  decided bet, pushes excluded; claim only if its interval lies above 0. One season of results is
  noisy, so a null here is the expected outcome even if the price split is real.
- **Unchanged:** every Addendum C rule, including the definition of S2 events and the close.

## Addendum E (2026-10-20): MS-044 system backtester, Wong teasers (ADR-051)

Committed before any backtest code was written or any teaser outcome computed. Looked at before
writing this: counts only. Games at the nflverse close inside the Wong ranges, per season 2016–25:
66, 68, 64, 42, 61, 64, 68, 80, 75, 99 (687 in all; 561 with a closing total of 49 or less); 34 so
far in 2026. Known going in, from public sources (not our data):

- **Prices:** two-team, six-point teaser prices in legal US books are reported between −120 and −135
  (bet365 and DraftKings −120, Caesars and Hard Rock −125, BetMGM −130, FanDuel −134; DraftKings
  reportedly −135 in 2025), and books reportedly shade lines away from the Wong ranges.
- **Jack's price:** −125 at Caesars, the best of the books he uses, so −125 is the primary price.

**Definitions.**

- **Leg:** a team whose nflverse closing spread is −7.5 to −8.5 (teased to −1.5 to −2.5) or +1.5 to
  +2.5 (teased to +7.5 to +8.5). At most one leg per game. Teased line = closing line + 6, from the
  team's side. A leg wins if team margin + teased line > 0, pushes if it equals 0.
- **Games:** all final games with an nflverse close (regular season and playoffs).
- **Variants (fixed here; no others are tested):** V0 every leg; V1 closing total ≤ 49; V2 closing
  total ≤ 49 and road teams only (neutral-site designated road teams count as road).
- **Prices:** −110, −120, −125, −130, −135, −140 for a two-team teaser. Break-even leg win rate
  = √(1 / decimal price): 72.4%, 73.9%, 74.5%, 75.2%, 75.8%, 76.4%.
- **Pushes:** the leg win rate counts a push as a loss (the common teaser rule). Teaser results are
  reported under two conventions: push loses the teaser; push voids it (stake returned).
- **Pairing (teaser ROI):** chronological: within each season-week, legs sorted by kickoff (then
  team) are paired 1–2, 3–4, …, an odd last leg is dropped; all-pairs: every pair of legs in the same
  season-week, averaged. One unit staked per teaser.

**Hypotheses.**

- **Primary (V0, 2016–25):** leg win rate with a 95% game bootstrap interval (5,000 resamples, seed
  2026). "Wong legs beat the −125 break-even" if the interval lies above 74.5%. The other prices are
  compared with the same interval, descriptively.
- **Secondary:** V1 and V2 the same way; 2016–23 versus 2024–25 as a stability check (no parameter
  is fitted, so neither is a training set); favourites versus underdogs.
- **Teaser ROI (descriptive, hypothetical):** per variant and price, chronological and all-pairs,
  with season tables, maximum drawdown and an equity curve. Interval for chronological ROI from
  resampling season-weeks.
- **2026 to date (Jack's question, hypothetical):** the same rules on 2026 games, both at the nflverse
  close and at **Caesars' own closing line** (the `williamhill_us` line in `line_moves` at kickoff,
  where that book is the one Jack uses). About 30 legs: reported as a record and ROI at −125 with no
  claim.

**What this can't see.** Prices available before the close (lines move into and out of the ranges
during the week); books' actual teaser rules beyond the two push conventions; limits or account
restrictions on teaser players.

## Addendum F (2026-10-20): MS-045a system catalogue F1–F10 (ADR-051)

Committed before any F-system code was written or any outcome computed. Looked at before writing
this: counts only, 2016–25 final games with an nflverse close. Home underdogs 1,014; division games
977; underdogs of 7 or more 793; primetime (7 pm ET or later) 578; closing totals of 50 or more 405;
teams off a bye facing a team that was not 296; road teams on a short week 168; road teams with a
body-clock kickoff of 10:30 or earlier 261. Known going in: these are well-known public systems, and
public markets tend to price well-known edges away, so nulls are the expected result.

**Common rules.**

- **Games:** 2016–25 final games (regular season and playoffs) with an nflverse closing spread and
  total. Situational fields come from `nfl_games` and `nfl_game_context`, which are known before
  kickoff (rest, bye, short week, body-clock kickoff hour, division). Observed weather is never used.
- **Grading:** against the nflverse close at −110 (break-even 52.38%). A side wins if team margin +
  closing line > 0; a total wins on the stated side of the closing total. Pushes are excluded from
  win rates and return 0 units.
- **Primary, each system:** win rate on 2016–25 with a one-sided exact binomial test against 52.38%.
  **Holm–Bonferroni across F1–F10 at a family-wise 0.05** (valid however the systems overlap). A
  system is **supported** only if it passes Holm **and** its 2024–25 win rate is above 52.38%.
  Everything else is reported as no claim. 95% intervals and return at −110 are descriptive.
- **Forward:** every F-system and both Wong variants are tracked in the paper portfolio (MS-045b)
  regardless of the backtest verdict, so the forward record is not selected on past results.

**Systems.** One position per game per system.

- **F1 home underdogs:** home team closing at +0.5 or more, neutral sites excluded. Take the home team.
- **F2 divisional underdogs:** the underdog in a division game (closing spread not 0).
- **F3 big underdogs:** the underdog when the closing spread is 7 or more.
- **F4 rest edge:** a team coming off a bye playing a team that is not. Take the rested team.
- **F5 short-week road teams:** the road team is on a short week. Take the home team.
- **F6 early body clock:** the road team's body-clock kickoff hour is 10:30 or earlier (for example a
  Pacific team at 1 pm ET). Take the home team.
- **F7 divisional unders:** the under in division games.
- **F8 primetime unders:** the under when kickoff is 7 pm ET or later.
- **F9 high-total unders:** the under when the closing total is 50 or more.
- **F10 ML (walk-forward logistic regression):** predicts whether the home team covers the closing
  spread from: closing home spread, closing total, division game, neutral site, both teams' rest
  days, bye flags and short-week flags, road team's travel (km), time-zone shift and body-clock
  kickoff hour, altitude change. Standardised features, L2 penalty with C = 1.0 (fixed, not tuned).
  For each season s from 2018 to 2025 the model is fitted on all seasons from 2016 to s − 1 and
  predicts season s. Positions: the side whose predicted cover probability is 0.55 or more. Its
  primary uses 2018–25.

**What this can't see.** Prices other than −110; lines before the close; public betting percentages.

## Addendum G (2026-10-20): MS-046 machine learning on minute-level market state (ADR-051, ADR-052)

Committed before any MS-046 code was written or any target computed. Looked at before writing this:
the MS-043 discovery report (Pinnacle led retail in 0.741 of matched changes; stale retail numbers
+0.44 points of CLV, mostly the half-point head start; steam continuation +0.17 points) and one
descriptive count: of 1,473 stale-number cases, 79% were still posted 30 minutes later and 48% six
hours later, with mean CLV unchanged (+0.39 to +0.41). No model, feature or target below has been
computed.

**Units and timing.**

- Games: 2026 regular-season games with a Pinnacle spread history and a usable close (Addendum C
  rules). Market: spreads.
- Decision times d = kickoff − h for h ∈ {48, 24, 6, 1} hours. A unit needs Pinnacle on the board at
  d. Every feature uses only `line_moves` rows with changed_at ≤ d (Addendum C's point-in-time rule).
- **Discovery:** games kicking off before 2026-10-21 (weeks 1–6). **Confirmation:** weeks 7–14 (to
  2026-12-16), scored once with models frozen on discovery data.

**Features at d** (home orientation): Pinnacle's line; Pinnacle's price imbalance (home minus away,
on the continuous cents scale); log Pinnacle limit and its change over the previous 6 h; Pinnacle
line changes in the previous 6 h and 24 h, and their net direction; mean, highest and lowest retail
line minus Pinnacle's; Circa's and Bookmaker.eu's line minus Pinnacle's (0 if absent, plus presence
flags); signed steam episodes (Addendum C definition) in the previous 24 h; Pinnacle suspensions in
the previous 24 h; hours to kickoff; a key-number flag (|Pinnacle line| ∈ {2.5, 3, 3.5, 6.5, 7, 7.5}).
G2 adds, per retail book and side: the book's line minus Pinnacle's (from the side), the book's price
on that side, minutes since the book last changed its line, whether the book still shows Pinnacle's
previous number, and the book's identity.

**Models and selection (fixed here).** Ridge-penalised linear models (C = 1, standardised) and
gradient-boosted trees (scikit-learn HistGradientBoosting, max_depth 3, learning_rate 0.05,
max_iter 200, random_state 2026). In discovery, each is evaluated walk-forward by week (train on all
weeks before w, predict week w, for w = 3 to 6). The one with the better pooled walk-forward loss is
chosen, refitted on weeks 1–6 and frozen for confirmation.

**G1: Pinnacle's direction.** Target: the sign of Pinnacle's closing home line minus its line at d
(toward home, no change, toward away). Baseline: class frequencies by horizon from the training
weeks. **Primary:** pooled multinomial log loss of the chosen model minus the baseline's, game
bootstrap (5,000, seed 2026). Discovery claim if the interval lies below 0 on the walk-forward
weeks; established only if it also lies below 0 on confirmation.

**G2: price-aware value of retail numbers.** Units: (game, d, retail book, side) with the book on the
board at d. Target: the expected profit per unit of taking that side at the book's line and price at
d, using Pinnacle's no-vig closing probability converted to the book's line with an empirical
margin distribution:

- Home-margin frequencies from 2016–25 regular-season games, bucketed by nflverse closing spread
  (|spread| ≤ 2.5, 3–4, 4.5–7, > 7). For a closing home line C and line L: the cover probability at L
  is the bucket's cover probability at L, shifted so that at C it equals Pinnacle's no-vig
  probability (pushes kept at the bucket's frequency). Expected profit = P(win) × payout − P(loss).

The model predicts this value; positions are units with a predicted value above 0. **Primary:** the
mean realised value of the selected positions, game bootstrap; discovery claim if the interval lies
above 0 on the walk-forward weeks. **Comparison (secondary):** the same for the rule "the book's line
is better than Pinnacle's for the side at −125 or better" (no model), to show what the model adds.

**What this can't see.** Who bet; injuries before 2026-10-18 at decision time (point-in-time
reports start then, so they are left out); exchange order books; moves more than 14 days out. Value
is measured against Pinnacle's close (CLV), not results.

## Addendum H (2026-10-20): price-aware value of stale numbers, for confirmation only

Committed after the MS-046 discovery run and before any week 7–14 game was played. MS-046 re-scored
the MS-043 S2 cases with Addendum G's price-aware value (expected profit per unit at Pinnacle's
no-vig close): −2.0% (−2.7 to −1.3) for all 1,473 cases, −0.6% (−1.5 to +0.3) for the 641 at −110 or
better. Those numbers motivated this addendum and are not evidence for it.

- **S2c (confirmation, weeks 7–14):** S2 events (Addendum C definition) at −110 or better. **Primary:**
  mean price-aware value per unit, game bootstrap (5,000, seed 2026); claim if the interval lies above 0. **Secondary:** the same for all S2 events.
- **Unchanged:** Addenda C, D and G, including the S2 event definition, the close, and the margin
  model.

## Addendum I (2026-10-21): MS-047 injury-report windows and the line

Committed before any MS-047 code was written or any outcome computed. Looked at before writing this:
R2w (+0.40 points of consensus move per newly-out starter, 6 days out to the close, weeks 2–6); MS-043
and MS-046 discovery reports (stale retail numbers −2.0% price-aware value overall); counts of injury
rows by week (point-in-time snapshots exist only from 2026-10-18, so they are not used here).

**The report window.** Clubs file game-status designations (Out, Doubtful, Questionable) by 4 pm ET
on the day before a Thursday game and two days before any other game (Friday for Sunday, Saturday for
Monday, Thursday for Saturday). For each game, R = 4 pm ET on that day, and the window is
[R − 4 h, R + 2 h]: teams usually file after practice, and books react afterwards.

**Events (R2w's definition, unchanged).** A player listed Out on his team's final report who
averaged at least 50% of offensive or defensive snaps over the previous three game weeks and played
the team's previous game. Per game, N = away events − home events (positive: news against the road
team). Week 1 has no previous game and is excluded.

**Games.** 2026 regular-season games with Pinnacle on the board at both window edges (`line_moves`).
**Discovery:** weeks 2–6 (kickoff before 2026-10-21). **Confirmation:** weeks 7–14 (to 2026-12-16),
with the same code.

**I1 (primary): does Pinnacle price the news inside the window?** Game-level OLS of Pinnacle's move
across the window (margin orientation, points: line at R − 4 h minus line at R + 2 h) on N. Game
bootstrap (5,000, seed 2026). Claim if the slope's interval lies above 0. Exploratory: the share of
each game's full move (6 days out to the close) that happens inside the window, for games with
N ≠ 0.

**I2 (primary): are retail books slower on injury news?** S2 events (Addendum C: a retail book still
posting Pinnacle's old number 60 s after Pinnacle moved, side Pinnacle moved toward, −125 or better)
whose Pinnacle change falls inside the window of a game with N ≠ 0, in the direction of the news
(toward home if N > 0, toward away if N < 0). Outcome: Addendum G's price-aware value per unit.
**Primary:** mean value of these news-window cases, game bootstrap; claim if the interval lies above 0. **Secondary:** the difference from all other S2 cases (game bootstrap of the difference in
means); claim if it lies above 0. Exploratory: how long the old number stayed up, news-window versus
other cases.

**Gates.** I1: at least 30 events in qualifying games. I2: at least 50 news-window cases.

**What this can't see.** The minute a designation became public (only the deadline is known); news
from practice reports earlier in the week; Questionable and Doubtful designations (only Out counts).

## Addendum J (2026-10-21): MS-050 openers and totals, price-aware

Committed before any MS-050 code was written or any outcome computed. Looked at before writing this:
MS-043 (S2 totals cases +0.55 points of CLV, exploratory), MS-046 (spread value model; stale retail
spread numbers −2.0% price-aware) and MS-047. No opener or price-aware totals value has been computed.

**Common rules.** `line_moves`, point-in-time (Addendum C). Value = expected profit per unit at
Pinnacle's no-vig close (Addendum G). Discovery weeks 1–6, confirmation weeks 7–14 with the same code.
Game bootstrap (5,000, seed 2026). Retail books as in Addendum C. Price bound −125.

**Totals value model.** Total-points frequencies from 2016–25 regular-season games, bucketed by the
nflverse closing total (≤ 40.5, 41–44.5, 45–48.5, ≥ 49). For a Pinnacle closing total C and a line L:
the bucket's over probability at L, shifted so that at C it equals Pinnacle's no-vig over
probability (pushes kept at the bucket's frequency), exactly as Addendum G does for spreads.

**J1 (primary): openers.** For each game and retail book, the book's first available spread row in
`line_moves` (time t0). A position is taken on each side whose opening line is better than
Pinnacle's line at t0 for that side, at −125 or better, with Pinnacle on the board at t0. Outcome:
spread value. Claim if the mean value's interval lies above 0. Exploratory: by book; by hours
between t0 and kickoff.

**J2 (primary): stale totals.** S2's rule applied to totals (Addendum C: a retail book still
posting Pinnacle's old total 60 s after Pinnacle moved it, on the side Pinnacle moved toward, over if
the total rose, at −125 or better). Outcome: totals value. Claim if the interval lies above 0.
Exploratory: at −110 or better versus −111 to −125.

**J3 (secondary): totals at fixed horizons.** At 48, 24, 6 and 1 hours before kickoff, each retail
book's total that is better than Pinnacle's for the over or the under, at −125 or better. Mean
totals value, game bootstrap; claim if above 0.

**What this can't see.** Openers more than 14 days before kickoff appear as the line in effect 14
days out (the store's window); exchange totals; who bet.

## Addendum K (2026-10-21): MS-051 exchanges, price-aware with fees

Committed before any exchange import or MS-051 study code, and before any exchange outcome was
computed. Looked at before writing this: one game's raw exchange history (Bears @ Packers): entries
carry a top-of-book price and a `limit` (the size available at that price); reduced to main-line
changes it is about 4,200 rows per game for Kalshi, Novig and ProphetX together; the median spread
overround is about 1% (retail books about 4.5%). Everything in Addenda C, G and J stays as written.

**Data.** Novig (`novig`), ProphetX (`prophetx`) and Kalshi (`kalshi`) spreads and totals, imported
into `line_moves` with the same rules as the books (main line closest to even, 1 s settle, 60 s
suspensions, 14-day window). The size at the top of book is stored with each row but a change in
size alone does not create a row. Moneylines are left out to save storage.

**Fees (per unit staked), fixed here.** Novig: none on pregame trades. ProphetX: 2% of net winnings
(sensitivity: 1%). Kalshi: taker fee 0.07 × p × (1 − p) per $1 contract, where p = 1 / decimal price;
cost per contract p + fee, profit per contract 1 − p − fee. Values are expected profit per unit
staked at Pinnacle's no-vig close (Addendum G for spreads, Addendum J for totals), after fees.

**K1 (primary): stale exchange prices.** Addendum C's S2 rule with an exchange as the lagging book:
60 seconds after Pinnacle changes its line, the exchange still offers Pinnacle's old line on the side
Pinnacle moved toward, at −125 or better, with at least 100 (in the provider's units) available at
the top of book. Spreads and totals pooled. Claim if the mean value's interval lies above 0.
Exploratory: by exchange; spreads versus totals; with a 1,000 size floor.

**K2 (secondary): exchange prices at fixed horizons.** At 48, 24, 6 and 1 hours before kickoff,
each exchange side whose line is better than Pinnacle's for that side (spreads and totals), at −125
or better, size at least 100. Claim if the mean value's interval lies above 0.

**Samples.** Discovery weeks 1–6; confirmation weeks 7–14 with the same code; game bootstrap
(5,000, seed 2026).

**What this can't see.** Depth beyond the top of book; whether an order would have been filled
before the price changed; exchange account limits; fees on Kalshi rounded to cents (the exact
formula is used).

## Addendum L (2026-10-21): Novig stale prices, for confirmation only

Committed after the MS-051 discovery run (`research/reports/exchanges-discovery.md`) and before any
week 7–14 game was played. In discovery, stale exchange prices were −1.2% (−1.6 to −0.8) after fees
overall, but Novig, which charges no pregame fee, was +0.4% (−0.2 to +0.9) over 635 cases. That
breakdown was exploratory, so it motivates this addendum and is not evidence for it.

- **K1n (confirmation, weeks 7–14):** Addendum K's K1 cases at Novig only (size ≥ 100, −125 or better,
  spreads and totals pooled). **Primary:** mean value per unit at Pinnacle's no-vig close, game
  bootstrap (5,000, seed 2026); claim if the interval lies above 0. **Secondary:** the same with a size
  floor of 1,000.
- **Unchanged:** every Addendum K rule.

## Addendum M (2026-10-21): MS-053 fair-value engine v2, model selection

Committed before any MS-053 code was written. Nothing below has been fitted or scored. This is a
model-building step, not a claim about value; it fixes how the engine is chosen so later studies
can't tune it on their own outcomes.

**Margin model.** The quantity is P(favourite margin = k | |closing spread|, closing total), with the
home team as favourite at a pick'em. Data: nflverse closes and results, regular season and playoffs.

- **Baseline (A):** today's spread-bucket tables (Addendum G).
- **Candidate (B):** kernel-weighted empirical frequencies. Weights exp(−½((Δs/h_s)² + (ΔT/h_T)²))
  over games, with Δs the spread difference and ΔT the total difference. Mixed with 2% of model (A)'s
  distribution, so no value seen in training has zero probability.
  - Bandwidths are chosen from h_s ∈ {0.5, 1, 1.5, 2} and h_T ∈ {2, 4, 6, 1000 (total ignored)}.
  - The criterion is leave-one-season-out log loss on 2016–22.
- **Validation, once, on 2023–25** with models fitted on 2016–22: the mean log loss of the exact
  favourite margin, game bootstrap (5,000, seed 2026). **(B) is adopted if its log loss is lower than
  (A)'s with the interval of the difference below 0.** Otherwise (A) stays and the engine keeps the
  spread buckets.
- **Reported alongside:** calibration of cover probabilities at the half-points around 3 and 7, and
  how well the moneyline implied by the spread (P(margin > 0), ties excluded) matches the nflverse
  closing moneylines (mean absolute probability difference).

**Total-points model.** The same protocol for P(total points = k | closing total, |closing spread|),
with model (A) being today's total buckets (Addendum J).

**Devig method.** Multiplicative, power and Shin, chosen on nflverse closing moneylines: log loss of
P(home win) on 2016–22, ties excluded. Confirmed on 2023–25, where it must not be worse than
multiplicative by more than its interval.

**Sharp consensus (fixed here, not fitted).** The equal-weight mean of the devigged probabilities of
the sharp sources on the board at the time: Pinnacle, Circa, Bookmaker.eu and Novig (Novig devigged
too). Each source is converted to the common line with the adopted margin or total model. There are
too few 2026 games to fit weights, so none are fitted.

## Addendum N (2026-10-21): MS-055a model-priced teaser legs ("Wong 2.0")

Committed before any MS-055 code was written or any outcome computed. Known going in: Wong's fixed
ranges won 75.7% (72.5–78.9%) of legs over 2016–25 (ADR-054); the fair-value engine v2 was selected
on 2016–22 and validated on 2023–25 (ADR-062).

- **Legs.** Every team in every game, teased 6 points. Its fair win probability is the engine's
  margin distribution, fitted only on seasons before the game's season (frozen bandwidths), calibrated
  so the favourite's no-push cover probability at the nflverse closing spread is 0.5 (the close is
  the market's median), and evaluated at the teased line. A push counts as a loss.
- **Selection.** Legs whose fair win probability is at least the −125 break-even (74.54%); at most one
  leg per game (the higher probability).
- **Primary (2023–25, out of sample for both the model and its bandwidths):** the selected legs' win
  rate, game bootstrap (5,000, seed 2026). Claim if the interval's lower bound is above 74.54%.
- **Secondary:** the same for 2018–25 (the bandwidths were chosen on 2016–22, so 2018–22 is only
  partly out of sample); chronological teasers at −125 and −120 (push loses); a comparison with Wong
  V0 legs over the same seasons.
- **Power:** about 150–250 selected legs over 2023–25 gives an interval of roughly ±6 points of win
  rate, so only an advantage of about 6 points over break-even could be claimed.
- **Forward:** a paper strategy `wong-model` is added to the portfolio regardless of the result.

## Addendum O (2026-10-21): MS-057 does the market move toward the model from early in the week?

Committed before any MS-057 code was written or any outcome computed. Known going in: rating gaps add
nothing beyond the close (R4); 52% of Pinnacle lines do not change from the decision time to the close
at short horizons (MS-046).

- **Games.** 2026 regular season. Decision time d = kickoff − 6 days, with Pinnacle on the board at d
  and a usable close (Addendum C). **Discovery:** weeks 1–6; **confirmation:** weeks 7–14.
- **Model line.** The ratings-only home spread at d: −(AdjEM home − AdjEM away + 1.6 home advantage),
  from the latest rating snapshot usable at d (`ml/football_features.rating_margin`), preseason
  snapshot in week 1. No injury or QB information.
- **Primary.** OLS of Pinnacle's move to the close (closing home line − line at d) on the model's
  disagreement at d (model home spread − Pinnacle line at d). Game bootstrap; claim if the slope's
  interval lies above 0 (the market moves toward the model).
- **Secondary.** Taking the side the model prefers at Pinnacle's line at d when |disagreement| ≥ 1.5
  points: mean price-aware value at Pinnacle's no-vig close (engine v2). Claim if above 0.
- **Power:** about 90 discovery games; with disagreements of a few points and moves of about a point,
  only a slope of roughly 0.1 or more can be told from zero.
- **Paid-data gate.** A positive slope that is not significant on one season is the case for buying
  2020–25 history (Phase 13 gate).

## Addendum P (2026-10-22): MS-054 cross-market value on main markets

Committed before any MS-054 code was written or any outcome computed. Known going in: retail numbers
that merely beat Pinnacle's line are worth −2.0% (MS-046); the engine v2 and the Shin devig are frozen
(ADR-062); the market moves toward the ratings early in the week (MS-057, unrelated to this test).

**Data and timing.** The research lake (MS-052): every book's full ladders, pregame. Decision times
d = kickoff − h for h ∈ {48, 24, 6, 1}. A book's line at d is its main line by the `line_moves` rule
(`lake/mainline.pick_main`) from its entries at or before d. Retail books: DraftKings, FanDuel,
Caesars, Hard Rock. Sharp sources: Pinnacle, Circa, Bookmaker.eu, Novig. Discovery weeks 1–6,
confirmation weeks 7–14; game bootstrap (5,000, seed 2026). Prices −200 to +200 only (avoid extreme
moneylines).

**Sharp-consensus fair probability** (Addendum M): for a side and line, each sharp source on the board
devigs its own main line (Shin) and converts the probability to the requested line with the engine's
margin (spreads, moneylines) or total distribution, calibrated at the source's line; the consensus is
the equal-weight mean. Value of a position = P(win) × payout − P(loss) under that probability
(moneyline ties excluded).

**A (primary): moneyline versus the book's own spread.** At each d, for each retail book with a main
spread and a moneyline on the board: the moneyline probability implied by the book's own spread
(engine margin distribution calibrated to the book's devigged spread price at its line, P(margin > 0),
ties excluded). A side is a candidate when the book's moneyline price is worth more than 0 under that
probability. Outcome: value at the sharp-consensus close. Claim if the mean's interval lies above 0.

**B (primary): same-line value against the sharp consensus.** At each d, every retail main-line side
(spreads, totals, moneylines) whose price is worth more than 0 under the consensus fair probability
at d for that exact line. Outcome: value at the sharp-consensus close. Claim if the mean's interval
lies above 0. Exploratory: by market, by book, by horizon.

**Power.** Value at the close has a per-position spread of roughly 3–5%. With several hundred
candidates over about 90 games, a mean of about 1% per unit is the smallest detectable.

**What this can't see.** Alternate ladders (MS-055b); limits at retail books; whether the price would
have been accepted at that size.

## Addendum Q (2026-10-22): MS-055b alternate ladders

Committed before any MS-055b code was written or any outcome computed. Same data, timing, sharp
consensus, engine and samples as Addendum P (MS-054), which has not yet been run.

- **Positions.** At d = kickoff − h, h ∈ {48, 24, 6, 1}: every retail alternate spread and total (any
  line other than that book's main line) with both sides active at d and a price between −300 and
  +300. A side is a candidate when its price is worth more than 0 under the sharp-consensus fair
  probability at d for that exact line.
- **Primary.** Mean value of the candidates at the sharp-consensus close; game bootstrap (5,000, seed
  2026). Claim if the interval lies above 0.
- **Exploratory.** Alternates that cross or land on 3 or 7 relative to the book's main line (spreads)
  versus others; by distance from the main line; by book; totals versus spreads.
- **Power.** Alternates are numerous (dozens per book and game), but they are strongly correlated
  within a game; the game bootstrap accounts for that. The smallest detectable mean is about 1% per
  unit.
- **What this can't see.** Retail limits on alternates (usually lower than on main lines).

## Addendum R (2026-10-22): corrections to MS-054 and MS-055b before confirmation

Written after the registered discovery runs (commit `0c1cd71`; `reports/cross-market-discovery.md`,
`reports/alt-ladders-discovery.md`) and before any confirmation game (weeks 7–14, kickoff from
2026-10-21) has been played. Post-hoc checks found two measurement problems. The discovery numbers
already seen cannot support any claim; this addendum fixes the rules confirmation will use.

1. **Ghost markets.** The feed sometimes leaves a sportsbook market marked active long after the book
   stopped updating it. Example: a Caesars −10 spread last updated on 1 September and still "active"
   at kickoff on 18 October, when Caesars' real line was −7. The main-line rule picks such a market
   whenever it is priced closer to even than the real line. **Coherence rule** (no outcomes involved):
   at time t, rank a sportsbook's active markets of one type by their latest entry, freshest first.
   Keep a market only if its no-vig probability is monotone with every market already kept: for
   spreads, P(home covers) is non-decreasing in the home handicap; for totals, P(over) is
   non-increasing in the total; ties are allowed. Exchanges (Novig, ProphetX, Kalshi) are exempt,
   because their resting orders could be traded. The rule applies to main-line picking and to
   alternate candidates for every sportsbook. `line_moves` keeps the old rule until the collector
   adopts this one (MS-058).
2. **Engine tails.** The engine converts a source's probability to another line by adding the
   main-line calibration shift unchanged at every line, which misprices lines far from the main
   line. Against the sharp books' own prices at the same line, MS-055b's discovery candidates were
   worth −3.6%, not the engine's +4.5%. **Direct value:** value under the equal-weight mean of the
   Shin-devigged prices of Pinnacle, Circa and Bookmaker.eu at exactly that line at the
   sharp-consensus close. Half-point lines only, so pushes need no model.

**Confirmation (weeks 7–14).**

- **MS-054 B and MS-055b.** Positions are selected as in Addenda P and Q, with the coherence rule.
  A claim requires both of these intervals to lie above 0 (game bootstrap, 5,000 draws, seed 2026):
  - the engine-scored mean;
  - the direct-scored mean, over positions that have a direct price.
- **MS-054 A** is unchanged apart from the coherence rule.
- The reports also show the as-registered results (no coherence rule) for comparison.
- **Secondary, confirmation-only:** retail alternates within 1 point of the book's main line (direct
  value; discovery, post hoc: +2.0%).
- **Power:** in discovery, 54 of 131 B positions over 34 of 93 games had a direct price. Weeks 7–14
  hold about 120 games, so about 70 direct positions. A mean of about 2% per unit is the smallest
  detectable.
- **Phase 12 confirmations** run on `line_moves` as it stands at confirmation. If MS-058 has
  re-derived it with the coherence rule by then, the reports say so.

## Addendum S (2026-10-22): MS-054 B confirmation requires an independently seen price

Written after Addendum R and its corrected discovery run (commit `0f5b772`), and before the first
confirmation kickoff (2026-10-23 00:15 UTC). The corrected run showed that the coherence rule misses
ghosts priced almost level with the real line. Caesars' dead −10 (−115/−115, last updated on
1 September) sits at 50.0% beside the real −7 at 50.2%. That is monotone, so the rule kept it, and
it stayed among the B positions at all four horizons. A minimum-slope version was tried and rejected
without using any outcome: Hard Rock prices adjacent lines in equal pairs and real ladders flatten in
the tails, so it would drop genuine markets. A feed-independent check replaces it.

- **Corroborated price.** A B position at DraftKings, FanDuel or Hard Rock counts as corroborated
  when our own collector (The Odds API, `odds_observations.source = 'the-odds-api'`, four snapshots a
  day) observed the same event, book, market, selection, point and American price at a snapshot inside
  the interval the lake price was in effect. That interval runs from the later of the two sides'
  latest entries to the next entry on either side, or to kickoff. Caesars cannot be corroborated (it
  is paid-plan-only on The Odds API) and is excluded from the primary.
- **Primary for MS-054 B (replaces Addendum R's B primary).** Corroborated B positions, coherence rule
  applied. A claim requires the engine-scored mean and the direct-scored mean (over corroborated
  positions with a direct price) both to have intervals above 0 (game bootstrap, 5,000 draws, seed
  2026). All other B variants are reported as secondary.
- **MS-054 A and MS-055b** are unchanged from Addendum R. The collector stores main lines only, so
  alternates cannot be corroborated.
- **Power, stated honestly.** Discovery cannot measure the corroborated share, because the collector
  only started on 2026-10-16. If about 70% of the roughly 100 DraftKings, FanDuel and Hard Rock
  positions in weeks 7–14 are corroborated, about half of those have a direct price: roughly 35
  positions over 25 games. Only a mean of about 3% or more per unit is detectable. An inconclusive
  result is "no claim".
- **If B holds or is inconclusive but positive:** The Odds API's historical snapshots (retail books
  plus Pinnacle, 2020–25) would test it over about 1,400 games with independently observed prices.
  That joins MS-057 as the second reason for the paid-data decision.
