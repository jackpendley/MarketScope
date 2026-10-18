"""Football ingest CLI.

    DATABASE_URL=... .venv/bin/python -m marketscope_football.ingest schedules --seasons 2016-2026 [--dry-run]

Idempotent per job key (default: one run per dataset, seasons and UTC date).
"""

from __future__ import annotations

import argparse
import hashlib
from collections import Counter
from datetime import datetime, timezone

import nflreadpy as nfl

from .db import claim_run, connect, fail_run, finish_run
from .linker import match_events
from .schedules import game_rows, team_rows
from .store import apply_links, load_link_inputs, upsert_games, upsert_teams


def parse_seasons(spec: str) -> list[int]:
    if "-" in spec:
        a, b = spec.split("-", 1)
        return list(range(int(a), int(b) + 1))
    return [int(s) for s in spec.split(",")]


def ingest_schedules(seasons: list[int], dry_run: bool, job_key: str | None) -> None:
    teams = nfl.load_teams().to_pandas()
    schedules = nfl.load_schedules(seasons).to_pandas()
    t_rows, g_rows = team_rows(teams), game_rows(schedules)
    digest = hashlib.sha256(schedules.to_csv(index=False).encode()).hexdigest()[:16]
    version = f"nflreadpy {nfl.__version__}; schedules sha256:{digest}"
    finals = sum(r["home_score"] is not None for r in g_rows)
    print(f"nflverse: {len(t_rows)} teams, {len(g_rows)} games ({finals} final), seasons {seasons[0]}-{seasons[-1]}")
    if dry_run:
        return
    key = job_key or f"schedules:{seasons[0]}-{seasons[-1]}:{datetime.now(timezone.utc):%Y-%m-%d}"
    with connect() as conn:
        claim = claim_run(conn, key, "schedules")
        conn.commit()
        if claim.run_id is None:
            print(f"job {key}: {claim.status}; nothing to do")
            return
        try:
            with conn.transaction():
                n = upsert_teams(conn, t_rows) + upsert_games(conn, g_rows)
                events, games, names = load_link_inputs(conn)
                result = match_events(events, games, names)
                apply_links(conn, result)
                finish_run(conn, claim.run_id, n, version)
            reasons = Counter(i["reason"] for i in result.issues)
            print(f"job {key}: upserted {n} rows; linked {len(result.links)} of {len(events)} odds events"
                  + (f"; unlinked: {dict(reasons)}" if reasons else ""))
        except Exception as exc:  # recorded, then re-raised so the job fails visibly
            conn.rollback()
            fail_run(conn, claim.run_id, f"{type(exc).__name__}: {exc}")
            conn.commit()
            raise


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="dataset", required=True)
    s = sub.add_parser("schedules")
    s.add_argument("--seasons", default="2016-2026")
    s.add_argument("--dry-run", action="store_true")
    s.add_argument("--job-key")
    args = parser.parse_args()
    if args.dataset == "schedules":
        ingest_schedules(parse_seasons(args.seasons), args.dry_run, args.job_key)


if __name__ == "__main__":
    main()
