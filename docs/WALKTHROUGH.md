# Reviewer walkthrough

A short tour of MarketScope for someone evaluating the engineering. Everything below runs **without production credentials**: the site uses a synthetic demo database (labelled synthetic on every page), and the data tools run on local or synthetic inputs. The deployed site is invite-only.

## 1. Run the site on synthetic data

Requirements: Node ≥ 22.12, pnpm 10, PostgreSQL 17, Python 3.11.

```bash
pnpm install
createdb marketscope_demo
DATABASE_URL=postgres://localhost:5432/marketscope_demo pnpm db:migrate
DATABASE_URL=postgres://localhost:5432/marketscope_demo pnpm --filter @marketscope/collector seed:synthetic --reset
DATABASE_URL=postgres://localhost:5432/marketscope_demo pnpm --filter @marketscope/web users create --username demo --email demo@example.com
DATABASE_URL=postgres://localhost:5432/marketscope_demo pnpm dev     # http://localhost:3000, sign in as demo
```

Then look at:

- **`/nfl`:** the odds board compares prices only at identical lines, and missing books show as missing.
- **A game page → Replay:** history rebuilt from stored observations, with each move placed in the interval between two snapshots, never at an invented moment.
- **`/ratings`, `/matchups`, `/model`:** the football model, its estimates and its scorecard.
- **`/research`, `/systems`, `/portfolio`:** pre-registered studies with their nulls, backtests, and a hypothetical paper portfolio.

## 2. The three stories, in code

**Ingestion that cannot quietly lose data.**

- `apps/collector/src/collect.ts`: claim a job key, guard the budget, fetch outside the transaction, write once.
- `apps/collector/src/line-moves-import.integration.test.ts`: an oversized book makes the run `partial`, which is kept by default and retried on request (ADR-071).
- `apps/collector/src/providers/oddspapi/stream.test.ts`: the streaming parser, including a truncated body that must fail (ADR-076).
- Prove a backup restores, on the demo database:

  ```bash
  SOURCE_URL=postgres://localhost:5432/marketscope_demo scripts/db-backup.sh
  scripts/db-restore-check.sh backups/<the new file>.dump      # compares every table's row count (ADR-075)
  ```

**Two measurement errors that made the market look beatable.**

- **Ghost markets:** `apps/collector/src/providers/oddspapi/transform.ts` (`withoutGhosts`) and its tests. The validation against independently collected snapshots is in ADR-065.
- **Engine tails:** `research/src/marketscope_research/fair_value.py` (`calibrate`) and `ladder_fit.py`, with the selection protocol committed before the code (`research/PREREGISTRATION.md`, Addendum T) and the results in ADR-066.

**Reproducible modelling with honest evaluation.**

- **Lake identity and provenance:** `research/src/marketscope_research/lake/store.py` and `research/tests/test_lake_provenance.py`, which test that the same content gives the same dataset ID, that an interrupted build resumes, that a tampered archive is refused, and that streamed batches write identical bytes (ADR-070).
- **The shared-line check:** `research/tests/test_evaluation.py` plants a model with no information and shows both the trap and the permutation null that catches it (Addenda V and W).
- **The ratings model end to end:** `apps/football/src/marketscope_football/ratings/feature_schema.py`, `provenance.py` and `model_card.py` (ADR-074). Generate a model card from synthetic data:

  ```bash
  cd apps/football && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
  PYTHONPATH=src .venv/bin/python -m marketscope_football.ratings.model_card \
      --scored tests/fixtures/synthetic_forward_test.csv --json /tmp/card.json --markdown /tmp/card.md
  ```

## 3. Run the checks

```bash
pnpm format:check && pnpm lint && pnpm typecheck && pnpm test
(cd research && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt && PYTHONPATH=src .venv/bin/python -m pytest -q)
(cd apps/football && PYTHONPATH=src .venv/bin/python -m pytest -q)
```

CI runs the same checks, plus Playwright end-to-end tests with axe-core accessibility checks, on every pull request.

## 4. What the data can and cannot say

- **Prices, not bets.** The odds are posted prices collected from providers. Nothing here observes who bet or how much, so "Pinnacle moved first" is about price ordering, never about "sharp money".
- **Scheduled, not streaming.** Live collection is 4 snapshots a day. Minute-level history is reconstructed afterwards from a provider's change log (its `createdAt`), so it is a retrospective reconstruction, not something observed in real time.
- **One provider's feed is not independent verification.** Only prices our own collector also saw count as that (Addendum S).
- **Model estimates, not advice.** Paper results are hypothetical. The 2026 forward test is the only prospective evidence for the model.
