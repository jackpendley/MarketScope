# MarketScope football pipeline

Python app (ADR-028) that loads nflverse data into the `nfl_*` tables. The schema is owned by Drizzle (`packages/db/src/schema.ts`); this app never migrates.

```bash
cd apps/football
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m pytest -q          # unit tests + integration tests against TEST_DATABASE_URL (migrated)
PYTHONPATH=src DATABASE_URL=... .venv/bin/python -m marketscope_football.ingest schedules --seasons 2016-2026 [--dry-run]
PYTHONPATH=src DATABASE_URL=... .venv/bin/python -m marketscope_football.ingest team-stats --seasons 2016-2026 [--refresh] [--dry-run]
PYTHONPATH=src DATABASE_URL=... .venv/bin/python -m marketscope_football.ingest snaps --seasons 2025-2026
PYTHONPATH=src DATABASE_URL=... .venv/bin/python -m marketscope_football.ingest injuries --seasons 2025-2026
PYTHONPATH=src .venv/bin/python -m marketscope_football.plays_report --out reports/plays-given-status.md
PYTHONPATH=src .venv/bin/python -m marketscope_football.crosscheck --seasons 2016-2026 --out reports/team-stats-crosscheck.md
PYTHONPATH=src .venv/bin/python -m marketscope_football.luck_fit   # reproduces the frozen constants in design.py
```

`--seasons` accepts `2016-2026`, `2025,2026` or `current`. The daily GitHub workflow (`.github/workflows/football-data.yml`) runs `schedules`, `team-stats --refresh`, `snaps` and `injuries` for the current season at 13:00 UTC, and `injuries` again at 23:00 UTC.

- **Schedules** (`schedules.py`): games, results, venue, observed weather (post-hoc), referee, coaches, and the nflverse closing line converted to our home orientation (`-spread_line`).
- **Linker** (`linker.py`): odds events ↔ games by exact team names and kickoff within 36 h. Swapped orientation is reported, never repaired.
- **Idempotent runs** (`db.py`): one job key per dataset, seasons and UTC date; failed runs are reclaimed.
- **Play-by-play cache** (`pbp.py`): one Parquet file per season in `.cache/pbp/` (gitignored), selected columns only, with `manifest.json` recording the nflreadpy version, rows and SHA-256. Play-by-play never goes into Postgres.
- **Team-game stats** (`team_stats.py`, ADR-029): one row per team per final game, offense + own special teams; defense = the opponent's row. Raw EPA plus the model channel (luck-adjusted, capped, WP-weighted EPA), Five Factors, pace/PROE, drives, turnover luck, special teams. Constants in `design.py` are fit on 2016–22 only (`luck_fit.py`).
- **Cross-check** (`crosscheck.py`): counts vs nflverse `load_team_stats` must match; see `reports/team-stats-crosscheck.md`.
- **Availability** (`availability.py`, ADR-030): snap counts with gsis ids attached; injury reports as a point-in-time history (live rows appended before kickoff, history as backfill with `first_seen_at` NULL); P(plays | status) with Wilson intervals (`plays_report.py`).
- `final_observed_at` is stamped only when a game we already held becomes final. Backfilled history never gets the import time.

Data: [nflverse](https://github.com/nflverse) (CC-BY 4.0).
