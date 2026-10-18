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
PYTHONPATH=src DATABASE_URL=... .venv/bin/python -m marketscope_football.ingest coaching           # load data/coaching_staff.csv
PYTHONPATH=src .venv/bin/python -m marketscope_football.coaching_build [--refresh]                # rebuild the CSV from sources
PYTHONPATH=src .venv/bin/python -m marketscope_football.coaching_build --report reports/coaching-staff.md
PYTHONPATH=src .venv/bin/python -m marketscope_football.coaching_build --check                    # drift vs Wikipedia (current season)
PYTHONPATH=src DATABASE_URL=... .venv/bin/python -m marketscope_football.ingest context            # nfl_game_context (all seasons)
PYTHONPATH=src DATABASE_URL=... .venv/bin/python -m marketscope_football.ingest weather --seasons 2024-2026 [--recent]
PYTHONPATH=src DATABASE_URL=... .venv/bin/python -m marketscope_football.weather_report --out reports/weather-forecast-skill.md
PYTHONPATH=src .venv/bin/python -m marketscope_football.venues                                     # refresh venue coordinates/elevation/time zone
PYTHONPATH=src .venv/bin/python -m marketscope_football.plays_report --out reports/plays-given-status.md
PYTHONPATH=src .venv/bin/python -m marketscope_football.crosscheck --seasons 2016-2026 --out reports/team-stats-crosscheck.md
PYTHONPATH=src .venv/bin/python -m marketscope_football.luck_fit   # reproduces the frozen constants in design.py
PYTHONPATH=src .venv/bin/python -m marketscope_football.eval.run_benchmarks --out reports/benchmarks.md  # walk-forward benchmarks
```

`--seasons` accepts `2016-2026`, `2025,2026` or `current`. The daily GitHub workflow (`.github/workflows/football-data.yml`) runs `schedules`, `team-stats --refresh`, `snaps` and `injuries` for the current season at 13:00 UTC, and `injuries` again at 23:00 UTC.

- **Schedules** (`schedules.py`): games, results, venue, observed weather (post-hoc), referee, coaches, and the nflverse closing line converted to our home orientation (`-spread_line`).
- **Linker** (`linker.py`): odds events ↔ games by exact team names and kickoff within 36 h. Swapped orientation is reported, never repaired.
- **Idempotent runs** (`db.py`): one job key per dataset, seasons and UTC date; failed runs are reclaimed.
- **Play-by-play cache** (`pbp.py`): one Parquet file per season in `.cache/pbp/` (gitignored), selected columns only, with `manifest.json` recording the nflreadpy version, rows and SHA-256. Play-by-play never goes into Postgres.
- **Team-game stats** (`team_stats.py`, ADR-029): one row per team per final game, offense + own special teams; defense = the opponent's row. Raw EPA plus the model channel (luck-adjusted, capped, WP-weighted EPA), Five Factors, pace/PROE, drives, turnover luck, special teams. Constants in `design.py` are fit on 2016–22 only (`luck_fit.py`).
- **Cross-check** (`crosscheck.py`): counts vs nflverse `load_team_stats` must match; see `reports/team-stats-crosscheck.md`.
- **Availability** (`availability.py`, ADR-030): snap counts with gsis ids attached; injury reports as a point-in-time history (live rows appended before kickoff, history as backfill with `first_seen_at` NULL); P(plays | status) with Wilson intervals (`plays_report.py`).
- **Coaching staff** (`coaching.py`, `coaching_build.py`, ADR-031): head coaches (nflverse, or Wikipedia where nflverse is stale), coordinators (Wikipedia, cited by revision) and play-callers (season lists, dated overrides, or the coordinator rule), assembled into `data/coaching_staff.csv` and validated. To record a change, add a row to `data/coordinator_changes.csv` or `data/playcaller_overrides.csv` with its source, rebuild, and commit.
- **Venues** (`venues.py`, `data/venues.csv`, `venue_aliases.csv`, `venue_overrides.csv`): roof type (curated), coordinates (Wikipedia), elevation and time zone (Open-Meteo); overrides fix nflverse's mislabelled 2025 international games.
- **Weather** (`weather.py`, ADR-032): Open-Meteo Previous Runs forecasts at leads 0/1/3/7 days for outdoor and retractable venues, game-window averages, 2024+.
- **Context** (`context.py`): rest, bye, short week, travel, time-zone shift, body clock, altitude, road streak, coaching tenure.
- **Evaluation** (`eval/`, ADR-033): walk-forward runner (results removed before `predict`; 2025 refused), pre-registered design, benchmarks (naive home field, 538 Elo, ridge SRS, market-implied ratings, the nflverse close), paired bootstrap scoring. Schedules 1999+ cached in `.cache/schedules/` with a manifest. See `reports/benchmarks.md`.
- `final_observed_at` is stamped only when a game we already held becomes final. Backfilled history never gets the import time.

Data: [nflverse](https://github.com/nflverse) (CC-BY 4.0). Coaching facts: Wikipedia (cited by revision) and the news sources in `data/*.csv`.
