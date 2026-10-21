# Case study: MarketScope

_A full-stack NFL market-intelligence platform with its own football model, built from October 2026 as a portfolio project._

## The problem

Sportsbook odds change constantly. Public sites show only the current price, and nothing shows _how_ a line moved or _whether_ the moves follow the football. MarketScope set out to do three things, all without becoming a picks service:

1. **Record the market faithfully.** Store every observation from five books, and replay any game's line history exactly.
2. **Model the football independently.** Build KenPom-style team ratings from play-by-play data, so there is a view of each game that doesn't come from the market.
3. **Test, with discipline, whether the two disagree in ways that matter.** Pre-register the questions, publish the nulls, and never dress up a model estimate as a bet.
4. **Study the market itself** (Phase 12, the Sharp-Market Lab). Which books move first, whether lines left behind are worth taking at their price, and whether published "sharp" systems hold up, scored by closing-line value rather than wins and losses.

## Architecture in one paragraph

- **Writers:** a TypeScript collector (GitHub Actions, 4 times a day) writes append-only odds observations to PostgreSQL. A Python pipeline (daily) ingests nflverse play-by-play, injuries, snaps and Open-Meteo forecasts, then rebuilds the ratings, the forward-test estimates and 10,000-season playoff simulations.
- **Readers:** a Next.js 16 site on Vercel reads the same database through one query layer. A read-only Python research package runs the studies.
- **Market microstructure (Phase 12):** a nightly job turns a provider's change logs into minute-level `line_moves` for the market makers (Pinnacle, Circa, Bookmaker.eu), four retail books and three exchanges (Novig, ProphetX, Kalshi). A paper-portfolio job places hypothetical positions from every pre-registered system before kickoff and grades them afterwards.
- **Database:** one schema (Drizzle migrations, RLS on all 26 tables) serves both languages. Every job is idempotent per job key.

Details and diagram: [ARCHITECTURE.md](ARCHITECTURE.md).

## Engineering decisions worth calling out

- **Append-only observations, with three timestamps kept apart.**
  - **The timestamps:** the provider's `last_update`, our `observed_at`, and the historical snapshot time are never conflated.
  - **Reconstruction:** line history is rebuilt from observations rather than stored as a derived series.
  - **Honest wording:** a move is reported as happening somewhere in the interval between two observations, never at an invented moment.
  - **Imported history:** reconstructed from a provider's change log (ADR-026), and kept out of the run-health metrics (ADR-027).
- **Exact-line comparison.** Prices are compared only when event, market, selection _and point_ match. The database enforces it a second time: a point exists exactly when the market has lines.
- **Idempotent, budget-guarded jobs.** Each run claims a job key before doing anything, and checks the credit budget before spending. The network fetch happens outside the database transaction. A repeated cron run or a manual re-run is harmless.
- **Point in time as a tested property, not a convention:**
  - The walk-forward runner removes result columns before a model predicts.
  - A test plants a model that reads results and checks that it fails.
  - Filtered rating snapshots must not change when later games are added.
  - The ML feature builders are checked by perturbing everything after each prediction time.
- **One query layer.** Every SQL query the site runs lives in `packages/db`, has integration tests against a migrated database, and is reviewed with EXPLAIN ANALYZE against production. The hot queries take under 3 ms.
- **Security as a default.**
  - RLS everywhere, invite-only accounts (hashed passwords, rate-limited sign-in, CSRF and open-redirect guards), `/api/*` protected because of the provider's terms.
  - API keys stripped from logged errors.
  - A history scan shows no secret was ever committed ([SECURITY.md](SECURITY.md)).
- **Testing at every layer:**

  | Layer                                                        | Tests |
  | ------------------------------------------------------------ | ----- |
  | `packages/shared` unit                                       | 192   |
  | `packages/db` integration                                    | 47    |
  | collector                                                    | 51    |
  | web view models                                              | 108   |
  | Playwright e2e, including axe-core WCAG checks on every page | 49    |
  | football pytest                                              | 110   |
  | research pytest                                              | 40    |

  Synthetic fixtures are labelled in their file names and on screen.

## The football model

**Design first.** The design was frozen in [RATINGS.md](RATINGS.md) before any data was examined. It took from the published systems:

- 538 Elo, ELWAY, nfelo and ESPN FPI
- DVOA
- KenPom
- Glickman–Stern state-space models

**The engine** is a Kalman filter over team strengths:

- **Inputs:** separate channels for pass, rush, success rate and points per drive.
- **Opponent adjustment** happens inside the filter, because every game links two teams.
- **Between seasons**, ratings revert toward a prior. The amount depends on play-caller continuity, and the prior's weight fades as games accumulate.
- **Parameters** were fitted by maximum likelihood on 2016–22.
- **Outputs** follow the KenPom contract: AdjO and AdjD in points per drive, AdjEM in points per game, luck, strength of schedule and Five Factors.

**Factors had to earn their place.** Rest, travel, byes, new coaches and the playoffs each had to beat a pre-registered rule on 2023–24. None did, which is consistent with the published finding that the bye-week edge vanished after 2011. QB and availability adjustments were learned from data.

**The model was then frozen,** with its parameters hashed and checked by a test. The untouched 2025 season was scored exactly once:

| 2025, 285 games            | Margin MAE | Brier     |
| -------------------------- | ---------- | --------- |
| Closing line (benchmark)   | 9.67       | 0.210     |
| **MarketScope ratings-v1** | **10.06**  | **0.222** |
| 538-style Elo              | 10.19      | 0.224     |
| SRS                        | 10.19      | 0.223     |
| Home field only            | 11.02      | 0.250     |

**Reading that table:**

- The model beats home field clearly, and is level with Elo and SRS: those differences are within noise.
- It trails the closing line by 0.39 points per game. That was the expected outcome, stated before the test.
- The point of a performance-only model is not to beat the market. It is to be an independent view whose disagreements can be studied.

**Since then:**

- **Live forward test (2026):** estimates are stored before kickoff, never edited, and scored on the public scorecard.
- **Season simulation:** reproduces every 2016–24 playoff field, and beats home-field coin flips on playoff, division and #1-seed odds.

## Research: pre-registered, nulls published

Each study's question, data window, decision rule and minimum sample size were committed (and the commit pushed) before any study code existed. Studies using the ratings stop at 2024, so the 2025 test season stays clean.

| Study                                                                     | Result                                                     |
| ------------------------------------------------------------------------- | ---------------------------------------------------------- |
| R1: is the consensus more accurate at kickoff than 6 days out?            | No (77 games)                                              |
| R2h: does the injury part of the model predict results against the close? | No: the close has priced injuries by kickoff               |
| **R2w: does the consensus move during the week on newly-out starters?**   | **Yes: about 0.4 points per starter (+0.14 to +0.73)**     |
| R3: is wind under-priced in totals?                                       | Inconclusive: one windy game short of the gate             |
| R4: do rating-vs-close gaps predict results?                              | No                                                         |
| R5: does the market overrate lucky teams?                                 | No                                                         |
| R6: does a model + market blend beat the close?                           | No: worse. nfelo's result doesn't replicate for this model |
| R7: does play-caller continuity preserve offense, holding the QB fixed?   | No. QB continuity does                                     |
| ML: do football features improve line-move prediction?                    | No detectable lift (15-game test week)                     |

**What they say together:** the closing NFL market already prices what a strong public performance model measures, including injuries by kickoff. It is still moving on injury news during the week.

## The Sharp-Market Lab: what moves the market, and is any of it worth taking?

The goal shifted from "can a model beat the book?" (it can't, and R4/R6 show why) to studying the market itself. Three pieces of engineering made that possible:

- **Minute-level line history for free.**
  - **The data:** a provider's change log, reduced to main-line changes per book. Bursts under a second are merged, suspensions of a minute or more are recorded, and 14 days before kickoff are kept.
  - **Size:** about 1,450 rows per game for books and about 2,300 more for exchanges, instead of millions of raw entries.
  - **Checked:** the result reproduces 99.99% of the stored snapshots.
- **A price-aware yardstick.** The obvious measure ("you got half a point better than the close") ignores what the book charged for that half-point. A margin distribution from 2016–25, with 3 and 7 carrying the most value, is calibrated to Pinnacle's no-vig close. That puts an expected value on any number at any price, and it was the measure that changed the conclusions.
- **Discovery and confirmation.**
  - Every study's rules were committed before its code, and its code before its first run.
  - Results on weeks 1–6 are "discovery". The same code re-runs once on weeks 7–14.
  - Anything noticed after the fact is pre-registered for the held-out weeks rather than claimed.

| Study                                                              | Discovery result (weeks 1–6)                                                          |
| ------------------------------------------------------------------ | ------------------------------------------------------------------------------------- |
| **S1: who moves first?**                                           | **Pinnacle, in 74% of matched changes with retail books (68–80%)**                    |
| S2: retail numbers left behind after Pinnacle moves                | +0.44 points, but **−2.0% per unit once priced**: the books charge for the old number |
| S3: does steam continue to the close?                              | Barely: +0.17 points (+0.01 to +0.34)                                                 |
| M1/M2: machine learning on the market's state                      | Pinnacle's next move unpredictable; model-picked retail numbers break-even            |
| I1: is injury news priced when the official report is filed?       | No: about two-thirds is priced four days earlier                                      |
| O1/T1: openers, stale totals                                       | No value; stale totals −1.8%                                                          |
| X1: stale exchange prices, after fees                              | −1.2%; only the no-fee exchange was near break-even (registered for confirmation)     |
| Systems: Wong teasers and ten public situational systems (2016–25) | None beat the price it would need; a walk-forward ML system did no better             |

**What they say together:** information flows from the market makers to everyone else, and everyone else charges for the lag, retail books through juice and exchange traders through price and fees. That is the honest answer to "where is the edge?" in a public, liquid market. The forward paper portfolio keeps tracking every system so the record isn't chosen by these results.

**A correction worth noting.** Building the portfolio exposed a join bug: neutral-site games were duplicated in one backtest. After the fix, an earlier claim ("the ML system is significantly worse than chance") no longer held, so it was withdrawn in writing (ADR-055). The same pattern was then searched for across the codebase.

## Data quality as a first-class concern

A spot check by the project owner found a play-caller error. Instead of patching that one case, it led to a systematic audit ([ADR-045](DECISIONS.md)):

- **The audit:** a tool compares every game against Wikipedia's staff templates _as they stood that week_, using the revision history. It found 13 mid-season coordinator changes that end-of-season snapshots had hidden.
- **Defensive play-callers:** each defensive-minded head coach was checked against news sources.
- **Ambiguity is now recorded:** split play-calling is marked "shared", and unverified rows display as "assumed" rather than as fact.
- **Re-runs:** both affected studies were re-run, and their conclusions held.

## What I'd do next

- **Confirmation (December 2026):** re-run every Sharp-Market study once on weeks 7–14 with unchanged code, and publish every result.
- **Near-real-time data:** the provider's history endpoint is effectively live for upcoming games. With permission, a 30-minute poller would let the paper portfolio track the market-signal strategies before kickoff.
- **Practice-report timing:** the live injury snapshots (since October 18) could show when practice participation moves the line, which is where the injury study found the market reacts.
- **A screen-reader pass** on the newer pages.

## Skills demonstrated

- **Backend data pipelines:** idempotent jobs, transactional ingestion, schema design with database-enforced invariants, query performance work.
- **Full-stack TypeScript:** Next.js server components, typed query layer, view-model testing, e2e and accessibility testing.
- **Python data engineering and statistical modelling:** state-space models, maximum-likelihood fitting, simulation, walk-forward evaluation, bootstrap inference.
- **Research discipline:** pre-registration, discovery and confirmation splits, leakage audits, published nulls, withdrawn claims, and honest uncertainty in every user-facing number.
- **Quantitative market analysis:** event studies on minute-level order flow across books and exchanges, price-aware closing-line value, fee modelling, and immutable paper trading.
