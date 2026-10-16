<!--
  Original project handoff, stored verbatim (2026-10-15) as the authoritative scope reference.
  Changes and clarifications made since are recorded in docs/DECISIONS.md and docs/ROADMAP.md;
  where they differ, those files win. Notably, the week-by-week timeline in §20 was dropped by
  the project owner in favor of milestone-driven development.
-->

# MARKETSCOPE — COMPLETE SOFTWARE ENGINEERING PROJECT HANDOFF

**Project:** MarketScope — NFL Sportsbook Market Intelligence Platform  
**Planning date:** October 15, 2026  
**Status:** Planning complete; implementation has not yet started  
**Project owner:** Independent developer building a portfolio-quality software engineering project  
**Initial development target:** 12 weeks, approximately 8–10 hours per week  
**Primary objective:** Build a sophisticated, reliable sports betting market analysis platform while developing demonstrable full-stack, backend, data engineering, cloud, and machine learning skills.

---

# 0. INSTRUCTIONS TO THE AI CODING AGENT

You are acting as my senior software engineering mentor, technical architect, and pair programmer.

This document contains the complete context from an extended planning conversation. Treat it as the authoritative starting specification for the project.

I want to begin building MarketScope with your assistance.

Your responsibilities:

1. Help architect and implement the application using sound, modern software engineering practices.
2. Break development into small, independently testable milestones.
3. Write maintainable, properly typed, well-organized code.
4. Explain important engineering decisions, including trade-offs and alternatives.
5. Help me learn software engineering rather than simply generating an application I cannot understand.
6. Prioritize a working vertical slice over unnecessarily elaborate architecture.
7. Develop real backend, database, API, testing, and deployment functionality, not just an attractive frontend.
8. Use proper version control, documentation, environment-variable management, migrations, and automated tests.
9. Preserve the product scope and defer features explicitly identified as future work.
10. Maintain a running record of architectural decisions, completed milestones, problems encountered, and next steps.

**Important collaboration preferences:**

- Assume I know how to program and have a computer science degree, but may need to refresh certain technologies.
- Provide explanations for important concepts, especially database design, asynchronous programming, APIs, and production engineering.
- Allow me to meaningfully participate in implementation.
- For complex features, explain the design and implementation plan before making substantial changes.
- Challenge questionable design choices rather than blindly following them.
- Do not add frameworks, abstractions, microservices, or infrastructure without a clear engineering reason.
- Prefer proven, well-supported technologies.
- Use current stable dependency versions that are mutually compatible.
- Do not pretend data, API endpoints, provider capabilities, or application features have been verified when they have not.
- Never fabricate sportsbook odds, historical coverage, or model performance.
- When repository access is available, inspect existing code before modifying anything.
- Do not request or expose secrets in chat, source control, logs, or browser-accessible code.
- Do not purchase subscriptions, deploy public services, or activate recurring paid infrastructure without approval.

**Start implementation after reviewing this specification. Do not simply produce another high-level plan.**

If no repository exists, begin with the initial project scaffolding and first milestone.

---

# 1. DEVELOPER BACKGROUND AND CAREER OBJECTIVES

## 1.1 Professional background

I am 26 years old and graduated from the University of Michigan in April 2023 with a Bachelor of Science in Computer Science.

I work full-time at FOX as a Digital Operations Specialist II, having recently been promoted from level I.

I have approximately 2.5 years of professional technical experience, primarily focused on production operations, live streaming reliability, incident response, and internal technology systems.

My professional experience includes:

- Monitoring production applications, live video playback, CDNs, and APIs.
- Troubleshooting production incidents and coordinating with engineering teams.
- Building or contributing to internal dashboards, automation, and workflows.
- Working with technologies including React, Next.js, TypeScript, JavaScript, Python, Node.js, and AWS.
- Using Datadog, Grafana, Splunk, Conviva, Mux, PagerDuty, and other observability tools.
- Working with AWS Lambda, API Gateway, Step Functions, DynamoDB, EC2, S3, and CloudWatch.
- Collaborating on internal tools, including a project called Waypoint involving dashboards, AWS services, and operational workflows.

I also founded and led a machine learning club called OpenMI at the University of Michigan.

## 1.2 Technical background

Technologies with which I have varying levels of experience:

**Languages:** Python, JavaScript, TypeScript, C++, SQL.

**Frontend:** React, Next.js, HTML, CSS.

**Backend:** Node.js, Express, Flask, REST APIs, GraphQL.

**Databases:** PostgreSQL, Supabase, MongoDB, DynamoDB.

**Cloud:** AWS, Vercel.

**Development tools:** Git, GitHub, VS Code, Cursor, Claude Code, ChatGPT, Postman, Docker concepts.

**Machine learning:** Python, PyTorch, TensorFlow, and general ML concepts.

Some of these technologies need reinforcement. Do not assume expert-level proficiency simply because I have encountered them.

## 1.3 Career objectives

My long-term career goal is to transition into a full-time software engineering position.

I am particularly interested in:

- Full-stack web development.
- Backend engineering.
- Data engineering.
- Machine learning.
- Data-intensive and real-time applications.

My immediate employment target is an entry-level or early-career software engineering role, preferably backend-oriented full-stack engineering.

My current challenges are:

- My operations-oriented job title does not strongly communicate software development experience.
- I need more concrete proof that I can independently design, implement, test, and deploy software.
- I need to strengthen practical software engineering fundamentals.
- I often struggle in technical coding interviews.
- I need a substantial engineering project I can confidently discuss with recruiters and interviewers.

MarketScope should help address the project-based and practical engineering portions of these challenges.

This is not merely an attempt to build a betting app. It is a deliberate investment in my software engineering career.

## 1.4 Personal interests

I am an avid NFL and sports fan.

I frequently use legal online sportsbooks and am knowledgeable about:

- American odds.
- Moneylines.
- Point spreads.
- Totals.
- Alternate lines.
- Odds shopping.
- Sportsbook pricing differences.
- Hedging.
- Betting market movement.
- Closing line value.
- Professional or "sharp" bettors.
- Reverse line movement.
- Ticket percentages versus money/handle percentages.

I am familiar with products such as OddsJam.

I want to apply this existing domain knowledge to a technically ambitious and genuinely useful software application.

---

# 2. PRODUCT OVERVIEW

## 2.1 Project name

**MarketScope**

Working subtitle: **NFL Sportsbook Market Intelligence Platform**

## 2.2 Product vision

Build a web application that allows users to:

1. Compare sportsbook odds across a customized set of operators.
2. Understand how a betting market changes over time.
3. Reconstruct historical line movements.
4. Identify sportsbook disagreements and unusual market behavior.
5. Investigate potentially meaningful betting-market indicators.
6. Analyze how different sportsbooks respond to one another.
7. Conduct historical research into betting-market hypotheses.
8. Eventually use machine learning to analyze and forecast market behavior.

**Product philosophy:**

"Compare the market. Replay its history. Investigate the signals. Test the evidence."

MarketScope should eventually resemble a hybrid between an odds shopping application and a financial market research terminal.

The odds board is the entry point.

Historical line movement and market intelligence are the differentiating features.

## 2.3 How MarketScope differs from OddsJam

I do not want to build a generic OddsJam clone.

The project should emphasize market transparency, historical reconstruction, and empirical investigation.

Instead of simply showing the best currently available odds, MarketScope should help answer:

- What was the earliest observed line?
- How has the market moved since then?
- Which sportsbook appeared to move first?
- Which sportsbooks followed?
- Did the movement cross important NFL spread values such as 3 or 7?
- Was the movement driven by a change in the point spread, the price, or both?
- Did different sportsbooks disagree substantially?
- Did the disagreement persist or converge?
- How did the consensus market change?
- What signals were visible before a subsequent movement?
- Have similar situations historically produced predictable outcomes?

The app should separate observable evidence from speculation.

It should not label something "confirmed sharp action" merely because an unusual line movement occurred.

## 2.4 Initial target user

Initially, this is a personal research tool for me.

The application should be designed for expansion, but multi-user functionality is not an MVP requirement.

## 2.5 Initial league

NFL only.

Do not expand to NBA, MLB, NHL, or college football during initial development.

NFL is an ideal starting league because:

- I understand it well.
- I regularly follow NFL odds.
- NFL spreads have important key numbers.
- Weekly game schedules provide manageable scope.
- Historical NFL statistics are relatively accessible.
- The NFL season is underway as of October 15, 2026.

## 2.6 Target sportsbooks

The initial application should focus on exactly five online sportsbooks:

1. DraftKings
2. FanDuel
3. BetMGM
4. Caesars Sportsbook
5. Hard Rock Bet

Hard Rock coverage should correspond to Arizona where the provider distinguishes state-specific feeds.

These are the sportsbooks I personally use.

A future research layer may incorporate sharper reference markets, but they should remain separate from my personalized five-book odds board.

---

# 3. SPORTS BETTING DOMAIN REQUIREMENTS

The application must implement domain calculations carefully and accurately.

## 3.1 Core betting markets

Initial scope:

**Moneyline:** Each team's outright winning price.

**Point spread:** Each team's handicap and its associated American odds.

**Game total:** Over/Under selections, posted total points, and corresponding prices.

Do not initially implement:

- Player props.
- Alternate spreads.
- Alternate totals.
- Same-game parlays.
- Futures.
- Live betting.
- Bet placement.

These can be added after the core platform works.

## 3.2 Odds comparison rules

MarketScope must not incorrectly compare different betting products.

For example:

Home -3.5 at -110 and home -3 at -115 are different point spreads.

One should not automatically receive a "best price" badge based solely on its American odds.

Comparison logic:

- Moneyline: compare prices for the same team and event.
- Spread: compare American prices only when event, selection, market, and spread point are identical.
- Total: compare American prices only when event, Over/Under selection, and total points are identical.

Different point values should still be displayed side by side.

We may later implement more sophisticated selection comparison methods, but any such method must be clearly documented.

## 3.3 American odds mathematics

Include tested utilities for:

- Converting American odds to decimal odds.
- Converting American odds to implied probability.
- Converting decimal odds to American odds.
- Calculating potential payouts.
- Computing bookmaker margin/overround where paired outcomes are valid.

For negative American odds -A:

Implied probability = A / (A + 100)

For positive American odds +A:

Implied probability = 100 / (A + 100)

Example:

-110 = approximately 52.38% raw implied probability.

+150 = 40% raw implied probability.

Do not interpret raw implied probability as a calibrated real-world win probability.

A bookmaker's margin must be considered.

## 3.4 Closing line value

Eventually support manual bet tracking and closing-line comparisons.

Possible stored bet fields:

- Event.
- Sportsbook.
- Market.
- Selection.
- Point.
- American odds.
- Stake.
- Timestamp.

Compare the recorded entry against an appropriately defined pregame market observation.

Importantly, a spread with a changed point cannot be evaluated using price difference alone.

CLV calculations must distinguish:

- Improved price at the same point.
- Improved point spread.
- Changes that cannot be reduced to a directly comparable price without a stated modeling method.

This feature is deferred until after the initial research release.

---

# 4. MARKET INTELLIGENCE CONCEPTS

## 4.1 Sharp sportsbooks

I am particularly interested in the sportsbooks that accept influential professional action and whose prices may provide information about broader market movement.

Examples worth investigating later:

- Pinnacle.
- Circa Sports.
- BookMaker / CRIS.

These operators are not all physical Las Vegas sportsbooks.

Some are online or offshore operators.

They should be treated as potential reference markets, not automatically as perfect predictors.

Any integration must use a legitimate, accessible data source.

## 4.2 Reverse line movement

Reverse line movement is often described as a scenario where the betting line moves against the side receiving a larger percentage of tickets.

Example:

- 73% of reported tickets favor the home team.
- Only 41% of reported handle favors the home team.
- The home favorite moves from -3.5 to -2.5.

This may be described as a potential reverse-line-movement situation.

However, there are limitations:

- Ticket and handle data may represent only participating sportsbooks.
- Different sources may use different sample populations.
- Odds movement does not prove why a line moved.
- Injury reports, weather, market-making decisions, and other information can influence pricing.
- A sportsbook may adjust for risk management rather than simply copying sharp bettors.

Therefore, MarketScope should avoid making unsubstantiated causal claims.

Betting-split integrations are deferred until we identify an accessible, properly licensed, clearly documented source.

## 4.3 Opening and closing lines

A critical distinction:

**First observed line** is not necessarily the actual opening line.

**Last observed pregame line** is not necessarily the official closing line.

MarketScope must explicitly distinguish:

- First recorded observation.
- Provider-reported opening line, if verified and available.
- Most recent observation.
- Last observed line before kickoff.
- Verified closing line, only if appropriate data exists.

Never label an ordinary first-seen snapshot as the true opening line.

Historical data coverage may vary by sportsbook and season.

## 4.4 Point-spread representation

Use a consistent team orientation for historical and statistical calculations.

For example, use the home team's posted spread.

If:

Home -3.5, Away +3.5

The normalized home spread is -3.5.

If the home spread moves to -2.5, the market has moved one point in favor of the away team's spread position.

Do not accidentally invert movement direction.

The application must test these calculations carefully.

---

# 5. PRODUCT RELEASES AND FUNCTIONAL SCOPE

## Release 0 — Technical feasibility

Before investing significant effort in the UI, verify that real NFL sportsbook data is accessible.

Required:

- Obtain and securely configure an odds API key.
- Query NFL events.
- Retrieve odds from available target sportsbooks.
- Verify bookmaker identifiers.
- Check which markets each book provides.
- Inspect update timestamps.
- Verify provider usage and rate-limit metadata.
- Save a sanitized sample response for local testing.
- Document unavailable or incomplete coverage.

Success criterion:

At least one real NFL game can be fetched, normalized, and inspected.

If one target bookmaker is unavailable, continue with the supported subset rather than blocking the project.

## Release 1 — Functional odds dashboard

Implement:

- Upcoming NFL games.
- Game selection.
- Sportsbook odds comparison.
- Moneyline, spread, and total markets.
- Market and selection filters.
- Exact-line price comparisons.
- Data freshness and source information.
- Server-side ingestion.
- PostgreSQL persistence.
- Basic historical line charts.
- Responsive design.
- Automated tests.
- Initial deployment.

This should be the first substantial release.

## Release 2 — Market Replay

Implement:

- Detailed historical game views.
- Multiple sportsbook time series.
- Historical line movement charts.
- Historical American-odds price charts.
- Time-based filtering.
- Bookmaker filtering.
- A selectable historical cursor.
- First/last observed values.
- Important NFL key-number crossings.
- Missing-data and stale-feed indicators.
- Historical market consensus.
- Historical market dispersion.

This is the project's central differentiator.

## Release 3 — Market Signal Lab

Implement:

- Spread movement events.
- Price movement events.
- Key-number crossings.
- Cross-book differences.
- Market consensus shifts.
- Bookmaker outliers.
- Rapid market movement.
- Versioned signal calculations.
- Historical signal analysis.
- Evidence supporting each detected signal.

Every signal must have a reproducible definition.

## Release 4 — Machine Learning Laboratory

Implement an initial research workflow for predicting future market movement.

Begin with a simple statistical baseline.

Introduce ML only when sufficient historical data is available.

Build a reproducible experiment and publish transparent evaluation results.

Do not prioritize an impressive-looking AI dashboard over a valid underlying experiment.

## Future releases

Potential future features:

- Alternate spreads and totals.
- NFL player props.
- Sharp sportsbook reference prices.
- Ticket/handle betting splits.
- Manual bet tracking.
- Closing line value analysis.
- Custom alerts.
- Saved filters.
- More leagues.
- Advanced market prediction models.
- Additional data engineering infrastructure.

These are future opportunities, not requirements for the first 12 weeks.

---

# 6. RECOMMENDED TECHNOLOGY STACK

I want a modern, pragmatic stack that strengthens skills relevant to professional software engineering roles.

## Frontend

**Next.js with TypeScript and React**

Use:

- Next.js App Router.
- React functional components.
- TypeScript strict mode.
- Tailwind CSS.
- shadcn/ui where useful.
- Recharts initially for data visualization.

The app should feel like professional financial analytics software.

Prioritize readability, dense but understandable data tables, and useful interactive charts.

Use a dark-friendly design with good contrast. Support responsive layouts.

## Backend

**Node.js / TypeScript**

Use Next.js route handlers for the initial read API.

Do not introduce Express, NestJS, or another backend framework unless a real architectural need emerges.

Implement clear boundaries between:

- Routes.
- Validation.
- Domain services.
- Database queries.
- External provider adapters.
- Data normalization.
- Ingestion.

The ingestion worker should be runnable separately from the web frontend.

## Database

**PostgreSQL**

Use a managed PostgreSQL provider, such as Supabase, or local PostgreSQL during development.

Use:

- Drizzle ORM.
- Drizzle migrations.
- Raw SQL when useful for analytics or performance.
- Proper foreign keys.
- Unique constraints.
- Indexes.
- Database transactions.

I specifically want to develop stronger relational database skills, so explain significant schema and query decisions.

## Data ingestion

**TypeScript/Node.js worker**

Use an external odds provider adapter.

The collector should:

1. Request current odds.
2. Validate external data.
3. Normalize sportsbook outcomes.
4. Upsert event metadata.
5. Record an ingestion run.
6. Append quote observations.
7. Record provider usage.
8. Report errors.
9. Safely support retries.

Start with a manually invoked command.

Add automated scheduling after the collector and cost controls work.

## Cloud deployment

Initial plan:

- Vercel for the Next.js application.
- Managed PostgreSQL database.
- AWS Lambda with EventBridge Scheduler for collection when needed.
- GitHub Actions for CI.

Use simple local execution before introducing AWS infrastructure.

## Machine learning

**Python**

Later use:

- pandas.
- NumPy.
- scikit-learn.
- Matplotlib.
- Possibly XGBoost or another gradient-boosting library.

Use reproducible scripts and notebooks.

Avoid deep learning unless it is justified by the problem and data.

## Testing

- Vitest for unit tests.
- Database integration tests.
- Playwright for end-to-end testing.
- GitHub Actions for automated quality checks.

## Package management

Use pnpm workspaces.

Keep the repository in a monorepo for simplicity.

Do not introduce Turborepo or Nx unless needed.

---

# 7. PROPOSED MONOREPO STRUCTURE

```
marketscope/

  apps/
  
    web/
      app/
        nfl/
        api/
        signals/
        research/
        ml/
        about/
      components/
      lib/
      public/

    collector/
      src/
        index.ts
        config.ts
        providers/
          the-odds-api.ts
        normalize.ts
        persist.ts
        usage.ts

  packages/

    db/
      src/
        schema.ts
        client.ts
        queries/
      drizzle/

    shared/
      src/
        odds.ts
        types.ts
        validators.ts
        calculations.ts

  research/
    notebooks/
    src/
    reports/
    models/

  tests/
    fixtures/

  docs/
    PRODUCT_SPEC.md
    ARCHITECTURE.md
    DATA_DICTIONARY.md
    PROVIDER_COVERAGE.md
    SIGNAL_DEFINITIONS.md
    MODEL_CARD.md
    DECISIONS.md

  .github/
    workflows/

  .env.example
  .gitignore
  pnpm-workspace.yaml
  package.json
  README.md
```

The layout is a recommendation, not a mandate.

Prefer whichever structure provides clarity without needless abstraction.

Shared packages should contain genuinely reusable types and business logic.

---

# 8. EXTERNAL ODDS DATA PROVIDER

## 8.1 Primary provider

Start with The Odds API.

Website:

https://the-odds-api.com/

API documentation:

https://the-odds-api.com/liveapi/guides/v4/

Bookmaker information:

https://the-odds-api.com/sports-odds-data/bookmaker-apis.html

Historical data:

https://the-odds-api.com/historical-odds-data/

Terms:

https://the-odds-api.com/terms-and-conditions.html

The provider's documented capabilities were examined during project planning on October 15, 2026.

**The coding agent must reverify relevant API documentation rather than blindly assuming that all identifiers, endpoints, billing rules, or plan details remain unchanged.**

## 8.2 Sport identifier

Initial sport:

americanfootball_nfl

## 8.3 Bookmaker identifiers

Previously identified provider keys:

- DraftKings: draftkings
- FanDuel: fanduel
- BetMGM: betmgm
- Caesars: williamhill_us
- Hard Rock Arizona: hardrockbet_az

These keys must be verified with actual API responses.

As documented during planning, Caesars may require a paid subscription.

Hard Rock Arizona may belong to a different provider region than the other books.

Do not assume that a listed bookmaker always has complete coverage.

## 8.4 Initial markets

Request:

h2h,spreads,totals

Use American odds and ISO-formatted timestamps.

## 8.5 Example request

GET https://api.the-odds-api.com/v4/sports/americanfootball_nfl/odds/

Query parameters:

- apiKey=SERVER_SECRET
- bookmakers=draftkings,fanduel,betmgm,williamhill_us,hardrockbet_az
- markets=h2h,spreads,totals
- oddsFormat=american
- dateFormat=iso

Do not expose this request with a real API key from browser-side JavaScript.

## 8.6 Historical endpoint

The previously documented historical odds endpoint is:

/v4/historical/sports/americanfootball_nfl/odds

It supports requesting a historical snapshot using a timestamp.

Verify request format, snapshot resolution, billing, and access requirements in current provider documentation.

Persist both:

- Requested historical timestamp.
- Actual provider snapshot timestamp returned.

Do not assign the current import timestamp to old observations.

## 8.7 Provider abstraction

Create a provider adapter so the application is not tightly coupled to The Odds API.

For example:

OddsProvider:

- fetchUpcomingEvents()
- fetchCurrentOdds()
- fetchHistoricalOdds(), added later
- parseUsageMetadata()

Exact method signatures may evolve.

The provider should return normalized application-domain objects rather than leak the external provider's nested data structure throughout the codebase.

## 8.8 Coverage validation

The initial provider verification should measure:

- Number of NFL games returned.
- Bookmaker IDs present.
- Which books have moneylines.
- Which books have spreads.
- Which books have totals.
- Market availability by game.
- Latest source timestamps.
- Response time.
- API credit consumption.
- Errors and incomplete responses.

Save a readable coverage report.

Test at multiple points during an NFL week when practical.

Do not interpret an absent bookmaker as proof that the sportsbook itself is not offering that market.

## 8.9 API cost controls

During planning, The Odds API listed:

- Free tier: 500 credits/month.
- 20,000-credit tier: approximately $30/month.
- 100,000-credit tier: approximately $59/month.

These are planning figures and must be reverified before purchase.

The API historically used a billing formula related to markets requested and regions or bookmaker groups.

For up to ten explicitly named bookmakers, the provider documented a single region-equivalent for quota calculations.

If a three-market request costs three credits, four polls per day for 30 days would consume approximately 360 credits.

This is only a planning estimate, not a guarantee.

Always read actual provider quota headers.

Historical requests can be considerably more expensive.

Build:

- Monthly credit-budget configuration.
- Remaining-credit tracking.
- Per-run estimated credit cost.
- A hard collection stop at a configured budget threshold.
- Failure logging.
- Caching of historical responses.
- Rate-limit handling.
- Exponential backoff for appropriate transient errors.

Never automatically purchase credits.

Start with the free plan and manual collection.

Only upgrade when justified by the functioning application.

---

# 9. DATA MODEL AND DATABASE DESIGN

The most important data engineering requirement is that MarketScope must preserve historical observations.

We are not merely storing the latest sportsbook price.

We need the ability to reconstruct what was observable at different times.

## 9.1 Core entities

### events

Fields:

- id: UUID primary key.
- provider_event_id: unique text.
- sport_key: text.
- season: integer.
- week: optional integer.
- home_team: text.
- away_team: text.
- commence_time_utc: timestamp with timezone.
- status: text or enum.
- created_at: timestamp.
- updated_at: timestamp.

The provider event ID should be mapped to our internal event ID.

Do not derive team orientation alphabetically.

### bookmakers

Fields:

- key: text primary key.
- display_name: text.
- region_hint: optional text.
- is_primary: boolean.
- enabled: boolean.

Seed the five preferred sportsbooks.

### ingestion_runs

Fields:

- id: UUID primary key.
- job_key: unique idempotency identifier.
- provider: text.
- request_type: live or historical.
- requested_snapshot_at: nullable timestamp.
- provider_snapshot_at: nullable timestamp.
- started_at: timestamp.
- finished_at: nullable timestamp.
- status: started, completed, failed, or equivalent.
- credits_used: nullable integer.
- credits_remaining: nullable integer.
- events_seen: integer.
- quotes_seen: integer.
- error_code: nullable text.
- error_message: nullable sanitized text.

This table should make ingestion behavior observable.

### odds_observations

Fields:

- id: bigint primary key.
- ingestion_run_id: foreign key.
- event_id: foreign key.
- bookmaker_key: foreign key.
- market_type: h2h, spreads, totals.
- selection: HOME, AWAY, OVER, UNDER.
- point: nullable decimal.
- american_price: integer.
- bookmaker_updated_at: nullable timestamp.
- observed_at: timestamp.
- is_live: boolean.
- source: text.

Use append-only records.

For the three initial featured markets, enforce a uniqueness constraint preventing duplicate bookmaker/event/market/selection observations within the same ingestion run.

This constraint will need to evolve if alternate lines are introduced because there may be multiple point values for the same selection.

Do not attempt to solve every possible future market type now.

## 9.2 Historical observation semantics

A recorded quote represents an observation of a bookmaker's reported market price at a particular time.

It does not necessarily represent the exact instant the sportsbook changed its price.

Preserve:

- Source-reported bookmaker update timestamp, when available.
- Time our collector observed the record.
- Historical snapshot time, when applicable.
- Ingestion provenance.

Do not conflate these timestamps.

## 9.3 Database indexes

Initial index suggestions:

odds_observations:

(event_id, market_type, selection, bookmaker_key, observed_at DESC)

And:

(ingestion_run_id)

Other indexes should be chosen based on actual query patterns.

Use EXPLAIN ANALYZE when optimizing expensive queries.

## 9.4 Idempotency

Scheduled collection and retries must not create accidental duplicate runs or observations.

Use a deterministic job key when a run is retried.

Persist the job key with a uniqueness constraint.

Choose and document retry behavior.

A successful job retry should not duplicate its original data.

Different legitimate scheduled snapshots may contain unchanged prices, and that is acceptable.

Identical odds observed at different times are still different observations.

## 9.5 Transaction safety

A collection operation should:

1. Create or claim the ingestion run.
2. Fetch and validate the provider response.
3. Upsert required event and bookmaker metadata.
4. Insert normalized observations transactionally.
5. Mark the run successful only after persistence succeeds.
6. Record failures accurately.

Do not mark a partially persisted collection successful.

Avoid long-running database transactions around slow external HTTP requests.

## 9.6 Derived entities

Add later:

### market_signals

Store:

- Signal type.
- Event.
- Market.
- Selection.
- Trigger timestamp.
- Evaluation window.
- Calculated value.
- Algorithm version.
- Coverage metadata.
- Evidence observation IDs.

### model_runs

Store:

- Model version.
- Dataset version.
- Training period.
- Validation period.
- Test period.
- Feature definitions.
- Evaluation metrics.
- Model artifact reference.

### model_predictions

Store:

- Model version.
- Event.
- Prediction target.
- As-of timestamp.
- Forecast horizon.
- Predicted probability/value.
- Eventually observed label.
- Creation timestamp.

---

# 10. NORMALIZED TYPES AND BUSINESS LOGIC

Use strict TypeScript domain types.

An initial normalized quote concept:

```ts
type Market = 'h2h' | 'spreads' | 'totals';

type Selection = 'HOME' | 'AWAY' | 'OVER' | 'UNDER';

type NormalizedQuote = {
  providerEventId: string;
  bookmakerKey: string;
  market: Market;
  selection: Selection;
  point: number | null;
  americanPrice: number;
  bookmakerUpdatedAt: string | null;
  observedAt: string;
  isLive: boolean;
};
```

This is a conceptual contract and may be refined as needed.

## Required normalization rules

- Map sportsbook team names to HOME/AWAY using the actual event's team metadata.
- Preserve sportsbook point-spread signs.
- Map Over/Under explicitly.
- Moneyline points must be null.
- Normalize American odds as valid integers.
- Reject or explicitly handle invalid/missing prices.
- Validate timestamps.
- Handle missing books.
- Handle absent markets.
- Exclude or separately classify in-play events during pregame-only analysis.
- Preserve enough provenance to debug provider transformations.

## Required utility functions

Implement and test functions equivalent to:

- americanToImpliedProbability()
- americanToDecimal()
- decimalToAmerican()
- normalizeEventOdds()
- compareIdenticalMarketPrices()
- calculateFreshness()
- calculateConsensusSpread()
- calculateBookDispersion()
- detectLineChanges()
- detectKeyNumberCrossings()

Do not implement all these on Day 1.

Implement incrementally as their features are developed.

---

# 11. API DESIGN

Initially use Next.js route handlers.

All data comes from our PostgreSQL database.

No browser-side calls to the commercial odds provider.

## 11.1 GET /api/games

Returns upcoming NFL games.

Potential query parameters:

- from
- to
- week
- limit
- cursor

Initial default: upcoming seven days.

Response includes event IDs, teams, kickoff times, and available-book coverage.

## 11.2 GET /api/games/:id/odds

Returns latest observed odds by sportsbook.

Include:

- Event details.
- Market.
- Selection.
- Spread/total point.
- American price.
- Bookmaker.
- Source update timestamp.
- Collection timestamp.
- Freshness metadata.
- Missing bookmaker information.
- Source information.

Do not treat a quote collected hours ago as automatically live.

If collection frequency is low, label results as a timestamped snapshot, not current real-time odds.

Distinguish the age of the collection from the age of the sportsbook's reported update.

## 11.3 GET /api/games/:id/history

Query parameters:

- market
- selection
- from
- to
- bookmakers
- resolution

Returns historical observations grouped or filterable by book.

Support sensible pagination/downsampling for large datasets.

Preserve meaningful movement changes rather than silently dropping them during downsampling.

## 11.4 GET /api/games/:id/movements

Returns historical movement events.

For example:

- Bookmaker.
- Previous observed spread.
- New observed spread.
- Previous observation timestamp.
- New observation timestamp.
- Movement magnitude.
- Movement direction.
- Whether an important key number was crossed.

## 11.5 GET /api/signals

Release 3.

Query parameters:

- type
- from
- to
- event

Returns versioned signal detections and evidence.

## 11.6 GET /api/health/data

Returns safe ingestion health and coverage summaries.

Examples:

- Most recent successful run.
- Age of latest stored snapshot.
- Number of games with coverage.
- Missing target books.
- Recent ingestion failures.

Do not expose raw credentials or sensitive infrastructure information.

## 11.7 API requirements

- Validate parameters using Zod.
- Use ISO 8601 timestamps in UTC.
- Return consistent response structures.
- Use appropriate HTTP status codes.
- Implement reasonable query limits.
- Avoid unbounded database queries.
- Keep server secrets server-side.
- Test invalid parameters and missing data.

---

# 12. FRONTEND DESIGN SPECIFICATION

The application should feel like a serious data analysis tool rather than a generic betting landing page.

## 12.1 Visual direction

Inspired by:

- Financial analytics terminals.
- Modern sports data dashboards.
- Trading and market research interfaces.
- Clean developer tools.

Preferred design:

- Dark-friendly interface.
- Clear typography.
- Dense but readable tables.
- Muted surfaces.
- Limited accent colors.
- Visually meaningful state indicators.
- Responsive layout.
- Excellent numerical alignment.
- Accessible contrast.
- Minimal decorative clutter.

Do not imitate a competing product's protected branding or exact interface.

## 12.2 Navigation

Initial navigation:

- Odds Board.
- Market Replay.
- Signal Lab.
- Research.
- ML Lab.
- About/Data Sources.

Only completed features should be presented as fully functional.

Unimplemented sections may be hidden or clearly marked as future functionality.

## 12.3 NFL odds board

Primary route:

/nfl

Display:

- Upcoming games grouped by date.
- Home and away teams.
- Kickoff time.
- Consensus spread, if computable.
- Selected sportsbook odds.
- Source/freshness metadata.

Filters:

- Week/date.
- Market.
- Team/game search.
- Sportsbook visibility.

Selecting a game opens a detailed comparison.

## 12.4 Game details

Route:

/nfl/games/[id]

Display:

- Matchup information.
- Main markets.
- Price comparisons.
- All five target books, with unavailable books clearly marked.
- Point and American price together.
- Last observed timestamp.
- Data coverage details.
- Link to historical analysis.

## 12.5 Market Replay

Route:

/nfl/games/[id]/history

This should eventually be one of the most sophisticated pages.

Components:

1. Event header.
2. Market selector.
3. Selection selector.
4. Bookmaker multiselect.
5. Time range selector.
6. Historical spread/total chart.
7. Historical American-price chart.
8. Time cursor or replay control.
9. Movement event timeline.
10. Data-quality and source panel.

For spreads, chart the same consistently oriented team for each book.

Display point movement and price movement separately.

A line moving from -3 (-110) to -3 (-125) is a price movement, even though its point value stayed the same.

A move from -3 (-110) to -3.5 (+100) changes both the point and price.

The UI should correctly represent these distinctions.

## 12.6 Replay functionality

Given a selected historical timestamp:

- Display the latest qualifying observation from each book at or before that time.
- Respect a configurable freshness window.
- Show missing observations.
- Do not silently carry prices forward across arbitrarily long gaps.
- Display when a book was last observed.
- Identify intervals in which changes may have occurred.

Avoid claiming an exact line movement time when the collector only observed the change between two snapshots.

## 12.7 Empty and error states

Support:

- No upcoming games.
- Book unavailable.
- Market unavailable.
- Provider coverage incomplete.
- Database contains no history.
- Data collection delayed.
- Data source temporarily unavailable.
- Request failed.

Never fabricate data to make the UI look populated.

Use clearly labeled fixture/demo data when needed for local development.

---

# 13. HISTORICAL LINE MOVEMENT ENGINE

This is the signature technical feature.

## 13.1 Core historical functionality

For a particular NFL event and sportsbook:

Retrieve ordered market observations.

Compare each observation to the previous valid observation.

Detect:

- Spread point changes.
- American-price changes.
- Total-point changes.
- Gaps in observations.
- Changes in sportsbook availability.

Store or generate structured movement events.

## 13.2 Consensus spread

Define a simple, reproducible consensus.

Recommended initial method:

Median home-team spread among sufficiently fresh target sportsbooks at a specified observation time.

Requirements:

- Always use the home team's spread.
- Use a documented freshness threshold.
- Do not calculate consensus when too few books are available.
- Include bookmaker coverage metadata.
- Do not claim a five-book consensus when only two books reported valid odds.

Later, compare the personalized five-book consensus against sharp reference books.

## 13.3 Cross-book dispersion

Possible metrics:

- Maximum home spread minus minimum home spread.
- Standard deviation of home spreads.
- Mean absolute deviation from consensus.
- Number of books disagreeing by at least 0.5 points.

Only compare contemporaneous, sufficiently fresh observations.

## 13.4 Important NFL key numbers

Initial key-number research:

- 3
- 7

Potential later additions:

- 6
- 10
- 14

Detect when a sportsbook spread crosses or lands on an important key number.

For example:

Home -2.5 to -3.5 crosses the -3 key number.

Use consistent spread orientation and sign handling.

A key-number crossing may be meaningful, but should not automatically imply betting value.

## 13.5 Rapid movement

Define an explicit rule.

Example research definition:

Consensus home spread changes by at least 1.0 point within a six-hour window.

Store:

- Previous value.
- New value.
- Window.
- Participating books.
- Number of observations.
- Data gaps.

Avoid treating an apparent large move after several hours without collection as definitively rapid.

## 13.6 Bookmaker lead/lag analysis

Future research question:

Which sportsbooks tend to move before others?

Possible approach:

- Detect a change in bookmaker A.
- Observe whether bookmaker B moves in the same direction within a specified time window.
- Count observed sequences across games.
- Compare distributions by bookmaker.

Important limitations:

- Provider polling resolution.
- Different book update timestamps.
- Provider caching.
- Missing snapshots.
- Simultaneous moves.
- Common external information.

Observed temporal precedence is not proof that one sportsbook caused another to move.

---

# 14. MARKET SIGNAL LAB

Every signal should be defined mathematically or algorithmically.

Every signal needs supporting evidence.

## 14.1 Initial signal types

### Signal A — Spread movement

Triggered when a sportsbook's observed point spread changes from its prior valid observation.

Fields:

- Event.
- Book.
- Market.
- Selection.
- Old point.
- New point.
- Change magnitude.
- Observation interval.

### Signal B — Price movement

Triggered when American odds change while the selection and point remain identical.

### Signal C — Key-number crossing

Triggered when an observed spread moves across an important NFL key number.

### Signal D — Bookmaker divergence

Triggered when a bookmaker's home spread differs from the fresh-book consensus by at least a configured threshold, initially 0.5 points.

### Signal E — Rapid consensus movement

Triggered by a sufficiently large consensus spread change within a defined interval.

### Signal F — Same-line price disagreement

Triggered when multiple books offer the same market, selection, and point but materially different American prices.

## 14.2 Future signals

- Sharp-reference divergence.
- Sportsbook lead/lag.
- Reverse line movement.
- Ticket/handle imbalance.
- Consensus volatility anomalies.
- Significant late-week market reversals.

These require better data and validation.

## 14.3 Signal metadata

Every signal should eventually include:

- Signal type.
- Formula/definition.
- Algorithm version.
- Event.
- Market.
- Selection.
- Detection timestamp.
- Evaluation window.
- Books included.
- Books excluded.
- Freshness threshold.
- Supporting observations.
- Coverage quality.
- Known limitations.

Never show unexplained signals as investment or betting recommendations.

---

# 15. FIRST MARKET RESEARCH STUDY

The first research question should be:

**Does a sportsbook's deviation from the NFL market consensus predict whether the consensus will subsequently move toward that sportsbook's price?**

Example:

- DraftKings home spread: -3.5.
- Other reporting books clustered around -3.
- DraftKings differs from the consensus by 0.5 points.

Question:

Within the next 24 hours, does the rest of the market move toward -3.5 more frequently than a baseline predicts?

Potential methodology:

1. Define the consensus using only observations available at the evaluation time.
2. Identify outlier sportsbooks.
3. Set a threshold for meaningful divergence.
4. Track subsequent market movement.
5. Measure convergence, divergence, or no change.
6. Group results by sportsbook.
7. Report sample size and coverage.
8. Repeat across historical games.
9. Compare findings against appropriate baselines.

Important considerations:

- Time-to-kickoff.
- Snapshot frequency.
- Correlated observations from the same game.
- Missing sportsbook data.
- Market movement caused by external information.
- Minimum data requirements.
- Differences between books' update timestamps.

This study should be reproducible.

Even a null result would be valuable if the research and implementation are rigorous.

---

# 16. MACHINE LEARNING PLAN

I am interested in machine learning, but do not want to create an unrealistic system that claims it can consistently beat professional sportsbooks.

Instead, use ML to investigate measurable market behavior.

## 16.1 Initial problem

Binary classification:

Given currently available NFL betting-market information, predict whether the consensus home-team spread will move by at least 0.5 points over the next 24 hours.

## 16.2 Prediction target

At timestamp t:

Only consider games scheduled more than 24 hours after t.

Calculate:

Current consensus home spread.

Future consensus home spread near t + 24 hours.

Target:

1 if absolute difference is at least 0.5 points.

0 otherwise.

Require a reasonable tolerance window for the future observation.

If the target observation is unavailable, mark the label missing rather than fabricate it.

## 16.3 Candidate features

Initial features:

- Current consensus spread.
- Hours until kickoff.
- Number of sportsbooks reporting.
- Average bookmaker deviation.
- Maximum bookmaker deviation.
- Cross-book spread range.
- Recent consensus movement over six hours.
- Recent consensus movement over 24 hours.
- Recent volatility.
- Age of latest observations.
- NFL week.
- Day of week.

Later features, subject to licensed point-in-time availability:

- Weather.
- Injury information.
- Team performance statistics.
- Betting splits.
- Sharp sportsbook differences.

## 16.4 Initial baseline models

Start with:

1. Constant majority-class probability.
2. Empirical historical movement frequency.
3. Simple heuristic based on recent volatility.
4. Logistic regression.

Only then try:

- Gradient-boosted trees.
- Additional nonlinear models.

Complexity must be justified by improved evaluation and the available data.

## 16.5 Train/validation/test methodology

This is extremely important.

Avoid random splitting of individual time-series observations.

Observations from the same NFL game are highly correlated.

Use chronological separation and game-level grouping.

Example:

Train on earlier completed seasons or weeks.

Validate on a subsequent period.

Test on a later untouched period.

Prevent data leakage.

Every feature must have been available as of its prediction timestamp.

Do not accidentally use:

- Closing lines.
- Later injury information.
- Future statistics.
- Future prices.
- Revised data unavailable at the historical evaluation time.

## 16.6 Evaluation metrics

Report:

- Brier score.
- Log loss.
- Calibration.
- Baseline comparison.
- Precision/recall where relevant.
- Sample size.
- Confidence intervals.
- Performance by time-to-kickoff window.

Accuracy alone is insufficient.

An ML model must not be described as useful merely because its displayed probability looks sophisticated.

## 16.7 Data requirements

Before training:

- Establish a sufficient sample of distinct NFL games.
- Measure class balance.
- Evaluate missingness.
- Confirm stable time-series coverage.
- Define a minimum acceptable number of positive examples.
- Establish a chronological test period.

If the dataset is too small, postpone predictive modeling and publish an exploratory analysis.

## 16.8 Model documentation

Create docs/MODEL_CARD.md.

Include:

- Model purpose.
- Prediction target.
- Features.
- Data provenance.
- Training period.
- Evaluation period.
- Missing data handling.
- Metrics.
- Comparison against baselines.
- Limitations.
- Potential sources of bias.
- Known failure modes.

## 16.9 Future ML directions

Potential research:

- Predict closing spread.
- Predict movement magnitude.
- Predict movement direction.
- Detect anomalous sportsbook disagreement.
- Model market volatility.
- Analyze bookmaker lead/lag characteristics.

Predicting betting-market behavior does not automatically imply profitable betting opportunities after sportsbook vig.

---

# 17. INGESTION SCHEDULING AND DATA QUALITY

## 17.1 Development mode

Initially run collection manually.

Example intended command:

pnpm --filter collector collect:nfl

Implement the actual package scripts accordingly.

The collector should be runnable without starting the web server.

## 17.2 Scheduled collection

Once manual collection works reliably, introduce scheduling.

AWS Lambda and EventBridge Scheduler are the recommended eventual approach.

Start with a small number of scheduled polls.

Four polls per day is an initial quota-planning example, not a promise of real-time data.

The UI must reflect actual observation timestamps and polling cadence.

If the API plan cannot support frequent updates, describe the product honestly as a periodically refreshed odds research application.

## 17.3 Collection frequency

Future adaptive polling could use:

- Less frequent collection many days before kickoff.
- More frequent collection during active NFL market windows.
- Higher frequency closer to kickoff.
- Collection stopped after kickoff for the pregame-only product.

Implement only when API costs and quota allow.

## 17.4 Data quality controls

Detect and report:

- Missing bookmakers.
- Missing markets.
- Invalid odds.
- Invalid timestamps.
- Provider errors.
- Duplicate responses.
- Unexpected bookmaker identifiers.
- Stale quotes.
- Incomplete ingestion.
- Large gaps between snapshots.

Never silently replace missing data with invented values.

## 17.5 Observability

Track:

- Ingestion success rate.
- API response time.
- Records inserted per run.
- Available sportsbooks per event.
- Latest successful collection time.
- API credits consumed.
- API credits remaining.
- Validation errors.
- Database errors.

Add basic structured logging early.

Add alerts for repeated failures after scheduled collection is introduced.

---

# 18. TESTING REQUIREMENTS

## 18.1 Unit tests

Test at minimum:

- American odds conversion.
- Implied probability calculations.
- HOME/AWAY mapping.
- OVER/UNDER mapping.
- Spread sign preservation.
- Null points for moneylines.
- Price comparison at identical spread points.
- Rejection of mismatched spread points.
- Missing sportsbook markets.
- Invalid odds values.
- Invalid timestamps.
- Movement direction.
- Key-number crossings.
- Duplicate unchanged observations not counted as price changes.

## 18.2 Integration tests

Test:

- Provider fixture to normalized records.
- Normalized records to PostgreSQL.
- Event upsert behavior.
- Repeated ingestion idempotency.
- Failed transaction handling.
- Latest observation queries.
- Missing-book handling.
- Historical query filtering.
- API validation.
- API error responses.

## 18.3 End-to-end tests

Use Playwright.

Validate:

- NFL odds board loads.
- Game details open.
- Market selector works.
- Sportsbook filtering works.
- Missing books show correct states.
- Historical chart renders from fixture data.
- Time filters work.
- Responsive layout remains usable.

## 18.4 Continuous integration

On every pull request:

- Install dependencies.
- Lint.
- Typecheck.
- Run unit tests.
- Run integration tests as appropriate.
- Build the application.

Main should remain deployable.

No secrets in GitHub Actions logs.

---

# 19. SECURITY, LICENSING, AND COMPLIANCE

## 19.1 Secret management

Never commit:

- API keys.
- Database credentials.
- Access tokens.
- Production connection strings.

Use environment variables.

Maintain a safe .env.example containing names but no credentials.

## 19.2 Data provider licensing

Read the current odds provider terms before publishing the application.

During planning, The Odds API's terms appeared to support application development, historical research, and ML use, with restrictions involving raw-data redistribution and competing feeds.

Do not assume that a public odds redistribution service is permitted.

Check:

- Display requirements.
- Attribution.
- Caching and storage.
- Historical retention.
- Redistribution.
- Commercial use.
- Public deployment.

Do not build a public raw-provider-data proxy.

If a feature requires a different license, mark it as blocked until authorized.

## 19.3 Responsible product positioning

MarketScope is primarily an analytics and education project.

Do not promise profitable betting picks.

Do not implement automated wagering or account integration as an MVP feature.

The product should make uncertainty and methodology visible.

## 19.4 Security basics

Implement:

- Input validation.
- Server-only API keys.
- Parameterized database access.
- Query limits.
- Safe logging.
- Sensible error handling.
- Dependency maintenance.

Public hosting should only occur after data-display permissions are reviewed.

---

# 20. COMPLETE 12-WEEK DEVELOPMENT ROADMAP

The schedule assumes approximately 8–10 hours per week.

The coding agent should turn the following items into GitHub issues or an equivalent project backlog.

Each task should have clear acceptance criteria.

## WEEK 1 — INITIALIZATION AND DATA FEASIBILITY

### MS-001 — Initialize repository

Tasks:

- Create the MarketScope Git repository.
- Configure pnpm workspace.
- Scaffold Next.js with TypeScript.
- Enable strict TypeScript.
- Configure Tailwind.
- Establish initial shared package structure.
- Configure linting.
- Create README.
- Create .gitignore.
- Create .env.example.
- Document the project scope.

Acceptance criteria:

A fresh clone can install dependencies, run the web application, and pass initial quality checks.

### MS-002 — Odds API feasibility

Tasks:

- Obtain/configure API key.
- Implement server-side odds request.
- Verify NFL sport identifier.
- Verify bookmaker IDs.
- Examine available markets.
- Parse provider quota headers.
- Document coverage.
- Save sanitized fixtures.

Acceptance criteria:

At least one real NFL matchup and available sportsbook markets can be fetched and inspected.

### MS-003 — Normalization layer

Tasks:

- Define shared types.
- Build Zod provider schemas.
- Implement outcome mapping.
- Normalize quotes.
- Test signs, points, prices, timestamps, and incomplete responses.

Acceptance criteria:

A raw provider response produces validated normalized market records.

## WEEK 2 — DATABASE AND HISTORICAL STORAGE

### MS-004 — Database setup

- Configure PostgreSQL.
- Configure Drizzle.
- Build first migrations.
- Create events table.
- Create bookmakers table.
- Create ingestion_runs table.
- Create odds_observations table.
- Add initial indexes and constraints.

### MS-005 — Persistent collector

- Fetch odds.
- Normalize.
- Upsert metadata.
- Insert observations.
- Record ingestion runs.
- Handle errors.
- Implement idempotency.

### MS-006 — Ingestion tests

- Fixture-based testing.
- Database integration testing.
- Credit metadata testing.
- Failure handling.

Acceptance milestone:

Run the collector twice and verify two separate historical observations through SQL.

## WEEK 3 — READ API

### MS-007 — Games API

Implement:

GET /api/games

And:

GET /api/games/:id/odds

### MS-008 — API reliability

Implement:

- Input validation.
- Latest-quote selection.
- Coverage metadata.
- Freshness logic.
- Error handling.
- API tests.

Acceptance milestone:

The frontend can retrieve reliable normalized NFL odds from our database.

## WEEK 4 — ODDS BOARD

### MS-009 — NFL game board

Build:

- Layout.
- Navigation.
- Game list.
- Matchup cards/rows.
- Kickoff times.
- Responsive design.

### MS-010 — Bookmaker comparison

Build:

- Moneyline tab.
- Spread tab.
- Total tab.
- Bookmaker comparison.
- Exact-line price highlighting.
- Stale/missing states.
- Game detail page.

Acceptance milestone:

A working odds-shopping experience powered by our own backend.

## WEEK 5 — INITIAL HISTORICAL VISUALIZATION

### MS-011 — History API

Implement:

GET /api/games/:id/history

Support:

- Market selection.
- Team/side selection.
- Bookmaker filtering.
- Time range.
- Timestamped records.

### MS-012 — Historical charts

Build:

- Spread-over-time chart.
- Price-over-time chart.
- Bookmaker toggles.
- Timestamp labels.
- Basic missing-data visualization.

Acceptance milestone:

View historical odds movement for a selected NFL game.

## WEEK 6 — DEPLOYED MVP

### MS-013 — Deployment

- Configure production database.
- Deploy Next.js.
- Secure environment variables.
- Test production API.
- Verify read performance.

### MS-014 — Scheduled collection

- Introduce scheduler.
- Configure quotas.
- Add ingestion logs.
- Add failure handling.
- Set credit limits.

### MS-015 — Documentation and E2E tests

- Document setup.
- Write architecture notes.
- Add Playwright smoke test.
- Document source and freshness.

Acceptance milestone:

A deployed, functioning MVP with a repeatable collection process.

## WEEK 7 — MARKET REPLAY

### MS-016 — Historical cursor

- Select a historical timestamp.
- Retrieve latest qualifying quote per book.
- Synchronize chart and odds table.
- Display historical market state.

### MS-017 — Data-quality correctness

- Handle missing periods.
- Label first/last observed.
- Prevent stale carry-forward.
- Improve timezones.
- Detect genuine point/price changes.

Acceptance milestone:

A usable historical replay view that communicates uncertainty accurately.

## WEEK 8 — SIGNAL ENGINE, PART ONE

### MS-018 — Initial movement signals

Implement:

- Spread changes.
- Price changes.
- Key-number crossings.
- Rapid consensus movement.

### MS-019 — Signal evidence

- Show calculations.
- Show participating sportsbooks.
- Show observation windows.
- Show signal limitations.
- Link to relevant history.

Acceptance milestone:

Reproducible movement signal detections.

## WEEK 9 — SIGNAL ENGINE, PART TWO

### MS-020 — Cross-book analysis

- Consensus deviations.
- Cross-book spread ranges.
- Bookmaker outlier detection.
- Same-line price disagreement.

### MS-021 — First market research report

Investigate the outlier-versus-consensus hypothesis.

Include:

- Method.
- Dataset.
- Results.
- Sample size.
- Missingness.
- Limitations.

Acceptance milestone:

A defensible, reproducible sportsbook market research case study.

## WEEK 10 — HISTORICAL DATA EXPANSION

### MS-022 — Historical import

Evaluate whether paid historical data is worth purchasing.

If approved:

- Implement bounded historical imports.
- Cache historical requests.
- Record provider snapshot time.
- Enforce credit limits.
- Support resumable imports.

### MS-023 — Data quality and performance

- Coverage dashboard.
- Query optimization.
- Index review.
- Storage review.
- Historical completeness report.

Acceptance milestone:

A dataset suitable for deeper historical studies, or clearly documented reasons why the sample remains too limited.

## WEEK 11 — MACHINE LEARNING BASELINE

### MS-024 — ML dataset construction

- Build point-in-time feature table.
- Create movement labels.
- Exclude missing targets.
- Prevent leakage.
- Group observations by game.
- Split chronologically.

### MS-025 — Baseline modeling

- Majority-class baseline.
- Simple rule-based baseline.
- Logistic regression.
- Brier score.
- Log loss.
- Calibration analysis.

Acceptance milestone:

One reproducible ML experiment with honest baseline comparisons.

## WEEK 12 — PORTFOLIO RELEASE

### MS-026 — Technical documentation

- Architecture diagram.
- Database schema.
- Model card.
- Screenshots.
- Product demonstration.
- Trade-off explanations.

### MS-027 — Quality and performance

- Fix important bugs.
- Improve accessibility.
- Review tests.
- Resolve high-priority performance issues.
- Check secret handling.

### MS-028 — Portfolio case study

Document:

- Problem.
- System design.
- Implementation decisions.
- Data engineering challenges.
- Results.
- Testing.
- Deployment.
- Research methodology.
- Lessons learned.

Acceptance milestone:

A project I can share with software engineering recruiters and explain confidently during technical interviews.

---

# 21. DEFINITION OF DONE

The project is portfolio-ready when:

- The application is functional and deployed.
- The NFL odds board uses real permitted provider data.
- Historical observations are stored persistently.
- At least one game has demonstrable historical market replay.
- Sportsbook price comparisons are logically correct.
- Missing and stale odds are handled honestly.
- The ingestion pipeline is observable and cost-controlled.
- Automated tests cover major business rules.
- CI runs automatically.
- The architecture is documented.
- At least one market research hypothesis has been investigated.
- A recruiter can understand the core product within two minutes.
- I can explain the system architecture without relying on AI.

Machine learning is a valuable addition but is not a prerequisite for a strong initial portfolio release if historical data is insufficient.

---

# 22. PROJECT SUCCESS METRICS

Track engineering progress separately from sports betting outcomes.

## Engineering metrics

- Number of successfully ingested games.
- Number of participating sportsbooks.
- Number of observations stored.
- Historical coverage duration.
- Ingestion success rate.
- Average ingestion duration.
- API response time.
- Automated test coverage of key business rules.
- Deployment reliability.
- API credits consumed per observation period.
- Application performance.

## Research metrics

- Number of unique historical NFL games analyzed.
- Bookmaker coverage by game.
- Movement events detected.
- Data completeness.
- Signal reproducibility.
- Hypothesis sample sizes.
- Model baseline comparisons, if applicable.

Do not measure success by gambling profit.

---

# 23. INITIAL ENVIRONMENT CONFIGURATION

Create an .env.example with variable names and safe defaults.

Suggested configuration:

ODDS_API_KEY=

DATABASE_URL=

COLLECTOR_ENABLED=false

MONTHLY_CREDIT_BUDGET=400

MAX_CREDITS_PER_RUN=3

QUOTE_FRESHNESS_MINUTES=15

These are starting points, not final production settings.

The credit-per-run assumption must be checked against actual provider billing.

A 15-minute freshness threshold is reasonable for genuinely recent market comparisons, but will often classify observations as stale if polling only four times daily. The UI must distinguish live/current quotes from older scheduled snapshots and should not imply that the entire dashboard is real-time.

Never commit actual API keys or production credentials.

---

# 24. FIRST 72 HOURS — EXECUTION INSTRUCTIONS

This is the immediate starting point for the coding agent.

## Day 1 — Repository initialization

Objective:

Establish a clean, professional TypeScript/Next.js repository.

Tasks:

1. Inspect the current development environment.
2. Verify Node.js, pnpm, Git, and other required tooling.
3. Create or inspect the marketscope repository.
4. Initialize pnpm workspaces.
5. Scaffold Next.js using current compatible versions.
6. Enable TypeScript strict mode.
7. Configure Tailwind.
8. Create project documentation folders.
9. Create initial environment configuration.
10. Configure lint and typecheck scripts.
11. Confirm the application runs locally.
12. Make an initial Git commit when the user has authorized repository changes.

Suggested starting commands, adapting as necessary:

    mkdir marketscope
    cd marketscope
    git init
    corepack enable
    pnpm create next-app@latest apps/web --ts --tailwind --eslint --app --use-pnpm

Set up workspace configuration carefully.

Avoid scaffolding packages that are not yet needed.

Deliverable:

A working Next.js development environment and a clean project foundation.

## Day 2 — First real NFL odds request

Objective:

Verify the primary data source and retrieve the first real odds response.

Tasks:

1. Create a secure provider configuration.
2. Implement a server-side verification script.
3. Query americanfootball_nfl.
4. Request main betting markets.
5. Check DraftKings, FanDuel, BetMGM, and Hard Rock Arizona first if accessible through the free plan.
6. Check Caesars only if current plan permits.
7. Inspect actual provider book IDs.
8. Log bookmaker coverage.
9. Log response timestamps.
10. Log API credit usage.
11. Save a sanitized deterministic fixture.
12. Write docs/PROVIDER_COVERAGE.md.

Do not continue assuming a bookmaker exists unless actual responses or provider documentation support that assumption.

Deliverable:

Verified NFL odds data and a clear record of available sportsbooks.

## Day 3 — Normalization and first UI feature

Objective:

Convert raw odds data into reliable application-domain objects.

Tasks:

1. Define normalized types.
2. Define Zod schemas.
3. Implement normalizeEventOdds().
4. Handle moneylines.
5. Handle spreads.
6. Handle totals.
7. Implement correct HOME/AWAY mapping.
8. Test point signs.
9. Test American odds.
10. Test missing markets.
11. Render the first matchup from fixture-backed data in Next.js.
12. Record the next database tasks.

Deliverable:

A real or fixture-backed NFL matchup rendered using validated normalized records, with passing unit tests.

---

# 25. RECOMMENDED IMPLEMENTATION ORDER

Do not implement the project strictly layer by layer for months without a usable application.

Prefer vertical slices.

First slice:

External API → normalization → fixture → basic frontend.

Second slice:

External API → normalization → PostgreSQL → read API → frontend.

Third slice:

Repeated ingestion → historical database records → history API → chart.

Fourth slice:

Historical observations → movement calculations → signals → research UI.

Fifth slice:

Historical dataset → feature generation → ML baseline → evaluation report.

Each slice should be independently demonstrable.

---

# 26. DOCUMENTATION REQUIREMENTS

Maintain these files as the project evolves:

README.md

Project overview, local setup, scripts, main features, and screenshots.

docs/PRODUCT_SPEC.md

Scope, user journeys, features, non-goals, and release plans.

docs/ARCHITECTURE.md

System diagram, technologies, component responsibilities, deployment, and data flow.

docs/DATA_DICTIONARY.md

Tables, fields, timestamp semantics, domain concepts, and data lineage.

docs/PROVIDER_COVERAGE.md

Actual verified books, markets, API observations, limitations, and cost assumptions.

docs/SIGNAL_DEFINITIONS.md

Formal definitions, thresholds, formulas, and limitations of signals.

docs/MODEL_CARD.md

ML methodology and evaluation once applicable.

docs/DECISIONS.md

A short architecture decision log explaining meaningful changes.

Also maintain a project status file, such as docs/PROJECT_STATUS.md, that records:

- Current milestone.
- Completed work.
- Tests passing or failing.
- Known issues.
- Pending credentials or access.
- Next task.
- Open architectural decisions.

This will make it easier to resume development across Claude/Codex sessions without losing context.

---

# 27. PORTFOLIO AND CAREER OBJECTIVES

Remember why this project exists.

I want to become a competitive software engineering candidate.

MarketScope should demonstrate:

**Frontend engineering:** React components, TypeScript, application state, user experience, and data visualization.

**Backend engineering:** API design, data validation, service boundaries, asynchronous workflows, and error handling.

**Database engineering:** Relational modeling, indexes, transactions, historical storage, and optimized queries.

**Data engineering:** External ingestion, normalization, scheduling, source timestamps, and data quality.

**Cloud engineering:** Deployment, managed databases, AWS scheduled workloads, secrets, and observability.

**Testing:** Unit testing, integration testing, browser testing, and continuous integration.

**Machine learning:** Reproducible data preparation, feature engineering, baseline modeling, and honest evaluation.

**Software engineering judgment:** Documentation, trade-offs, scope control, maintainability, cost management, and reliability.

I should eventually be able to tell interviewers that I independently developed and deployed a data-intensive NFL market analysis platform integrating multiple sportsbook data sources, historical market replay, analytics, and production engineering practices.

Only claim features and measurable improvements once they have actually been implemented and validated.

The end goal is not just an impressive GitHub README. It is genuine competence and the ability to discuss design decisions confidently.

---

# 28. COLLABORATION AND LEARNING RULES

Use AI to accelerate development without bypassing the learning process.

For each substantive feature:

1. Explain what we're building.
2. Explain how it fits into the architecture.
3. Identify the important data structures and interfaces.
4. Implement in small increments.
5. Add appropriate tests.
6. Run the implementation.
7. Explain significant trade-offs.
8. Update documentation.
9. Summarize what I should understand from that work.

Occasionally identify an appropriately scoped component or test for me to implement independently.

Do not unnecessarily slow development with repetitive explanations.

However, do not obscure significant technical decisions inside generated code.

I want to be able to rebuild and explain important parts of this project myself.

When possible, suggest useful exercises that reinforce the exact concepts we're using.

Examples:

- Write a SQL query to retrieve the latest observed price for each bookmaker.
- Implement American odds conversions without AI.
- Explain database indexes.
- Design a retry strategy.
- Debug an incomplete API payload.
- Describe why event timestamps and ingestion timestamps differ.
- Explain how data leakage can invalidate a machine learning result.

---

# 29. THINGS WE SHOULD NOT DO

To control scope and preserve engineering quality:

- Do not build every planned feature immediately.
- Do not start with ML before data ingestion works.
- Do not introduce Kafka, Kubernetes, Spark, or microservices without a justified need.
- Do not build five separate sportsbook scrapers.
- Do not bypass API access restrictions.
- Do not assume all five sportsbooks always provide identical markets.
- Do not fabricate opening lines.
- Do not equate missing data with unchanged prices.
- Do not claim market signals prove professional betting activity.
- Do not compare mismatched point spreads using American price alone.
- Do not randomly split correlated time-series observations for ML evaluation.
- Do not implement automated wagering.
- Do not make the project dependent on paid services before the free prototype works.
- Do not prioritize visual polish over correct data handling.
- Do not generate an elaborate application that I cannot understand or maintain.
- Do not silently change the project's original scope.

---

# 30. LONG-TERM PRODUCT POSSIBILITIES

Once the core application is stable, there are interesting areas for expansion.

## Advanced odds shopping

- Alternate point spreads.
- Alternate totals.
- Historical best available prices.
- Sportsbook-specific market preferences.
- Saved filters.
- Alerts when a selected line becomes available.

## Professional market research

- Pinnacle reference prices.
- Circa market analysis where legitimately accessible.
- BookMaker/CRIS comparison.
- Market-making versus recreational sportsbook behavior.
- Lead/lag research.
- Market convergence.
- Late-market reversals.
- Key-number movement analytics.

## Betting portfolio analytics

- Manual bet entry.
- Historical bet records.
- Closing line value.
- Market comparison at bet time.
- Performance analytics.
- Exposure summaries.

## Machine learning

- Closing spread prediction.
- Market movement classification.
- Price volatility forecasting.
- Bookmaker behavior clustering.
- Anomaly detection.
- Historical signal evaluation.

## Data engineering

- Adaptive scheduled collection.
- Larger historical databases.
- Event-driven pipelines.
- Incremental feature computation.
- Data quality monitoring.
- Historical dataset versioning.

Only expand into these areas after the existing functionality is reliable.

---

# 31. SOURCE REFERENCES

Useful external documentation:

The Odds API:

https://the-odds-api.com/

The Odds API v4 documentation:

https://the-odds-api.com/liveapi/guides/v4/

Bookmaker identifiers:

https://the-odds-api.com/sports-odds-data/bookmaker-apis.html

Historical odds:

https://the-odds-api.com/historical-odds-data/

Provider terms:

https://the-odds-api.com/terms-and-conditions.html

NFL historical statistics and datasets:

https://github.com/nflverse/nflverse-data

Next.js:

https://nextjs.org/docs

TypeScript:

https://www.typescriptlang.org/docs/

Drizzle:

https://orm.drizzle.team/

PostgreSQL:

https://www.postgresql.org/docs/

Vitest:

https://vitest.dev/

Playwright:

https://playwright.dev/

Scikit-learn:

https://scikit-learn.org/stable/

Verify documentation against current versions when implementation begins.

---

# 32. CURRENT PROJECT STATE

As of October 15, 2026:

**Completed:**

- Initial career and portfolio planning.
- Product concept selection.
- NFL initial-scope decision.
- Selection of five preferred sportsbooks.
- Identification of a candidate odds API provider.
- Initial tech stack recommendations.
- Preliminary system architecture.
- Database schema planning.
- MVP feature planning.
- Historical market research design.
- Machine learning research direction.
- 12-week roadmap.
- Initial implementation backlog.

**Not yet completed or verified:**

- Repository initialization.
- Development environment setup.
- API key acquisition.
- Live provider coverage test.
- Database implementation.
- Frontend development.
- Backend implementation.
- Ingestion pipeline.
- Historical collection.
- Deployment.
- ML experiments.

Do not assume any of the uncompleted steps have happened.

The existing work consists of this specification and planning discussion.

---

# 33. EXACT NEXT ACTION FOR THE CODING AGENT

We are ready to begin implementation.

Please do the following:

**Step 1 — Review the plan.**

Identify any genuine technical blockers, contradictory requirements, or high-impact assumptions that should be resolved before coding.

Do not redesign the entire project or propose an unnecessarily different technology stack.

**Step 2 — Examine the development environment and repository.**

If an existing MarketScope repository is accessible, inspect its structure before changing anything.

If no repository exists, initialize the project following the recommended architecture.

**Step 3 — Execute MS-001.**

Establish:

- Next.js application.
- TypeScript.
- pnpm workspace.
- Core project structure.
- Environment configuration.
- Lint/typecheck.
- Initial README and documentation.

Ensure it runs successfully.

**Step 4 — Prepare MS-002.**

Implement or scaffold the server-side odds API verification script.

Explain how I should provide the API key securely through my local environment.

Do not hard-code a key.

If the key is not available, use fixture-based development while identifying the live verification step as pending.

**Step 5 — Present a concise engineering checkpoint.**

At the end of the implementation session, summarize:

- Files created or modified.
- Commands executed.
- Tests and checks performed.
- What works.
- What remains unverified.
- Any credentials or permissions needed.
- The next recommended engineering task.
- The most important technical concept I should understand from the work.

Maintain docs/PROJECT_STATUS.md to preserve progress across future sessions.

Do not substitute another broad project proposal for implementation.

**BEGIN WITH MS-001: MARKETScope REPOSITORY INITIALIZATION AND DEVELOPMENT ENVIRONMENT SETUP.**

Our immediate goal is to establish a clean, working foundation and make the first real NFL odds API request.

Build MarketScope incrementally, carefully, and with the expectation that it will eventually be demonstrated to professional software engineering interviewers.
