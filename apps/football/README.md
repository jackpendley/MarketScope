# MarketScope football pipeline

Python app (ADR-028) that loads nflverse data into the `nfl_*` tables. The schema is owned by Drizzle (`packages/db/src/schema.ts`); this app never migrates.

```bash
cd apps/football
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m pytest -q          # unit tests + integration tests against TEST_DATABASE_URL (migrated)
PYTHONPATH=src DATABASE_URL=... .venv/bin/python -m marketscope_football.ingest schedules --seasons 2016-2026 [--dry-run]
```

- **Schedules** (`schedules.py`): games, results, venue, observed weather (post-hoc), referee, coaches, and the nflverse closing line converted to our home orientation (`-spread_line`).
- **Linker** (`linker.py`): odds events ↔ games by exact team names and kickoff within 36 h. Swapped orientation is reported, never repaired.
- **Idempotent runs** (`db.py`): one job key per dataset, seasons and UTC date; failed runs are reclaimed.
- `final_observed_at` is stamped only when a game we already held becomes final. Backfilled history never gets the import time.

Data: [nflverse](https://github.com/nflverse) (CC-BY 4.0).
