"""Football ingest CLI.

    DATABASE_URL=... .venv/bin/python -m marketscope_football.ingest schedules --seasons 2016-2026 [--dry-run]
    DATABASE_URL=... .venv/bin/python -m marketscope_football.ingest team-stats --seasons 2016-2026 [--refresh] [--dry-run]

Idempotent per job key (default: one run per dataset, seasons and UTC date).
"""

from __future__ import annotations

import argparse
import hashlib
from collections import Counter
from datetime import datetime, timezone

import nflreadpy as nfl

from . import pbp
from .db import claim_run, connect, fail_run, finish_run
from .design import STATS_VERSION
from .linker import match_events
from .schedules import game_rows, team_rows
from .store import (apply_links, final_game_ids, load_link_inputs, replace_team_game_stats, upsert_games,
                    upsert_teams)
from .team_stats import team_game_stats


def current_season(today: datetime | None = None) -> int:
    """NFL season year: a season runs September to February, so Jan-Feb belong to last year's."""
    today = today or datetime.now(timezone.utc)
    return today.year if today.month >= 3 else today.year - 1


def parse_seasons(spec: str) -> list[int]:
    if spec == "current":
        return [current_season()]
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


def ingest_team_stats(seasons: list[int], refresh: bool, dry_run: bool, job_key: str | None) -> None:
    """Aggregate cached play-by-play into nfl_team_game_stats for games final in nfl_games.
    `refresh` re-downloads play-by-play (use for the current season; past seasons are stable)."""
    frames = {s: team_game_stats(pbp.load_season(s, refresh=refresh)) for s in seasons}
    version = f"{STATS_VERSION}; {pbp.source_version(seasons)}"
    print(f"play-by-play: {sum(f.height for f in frames.values())} team-games, seasons {seasons[0]}-{seasons[-1]}")
    if dry_run:
        return
    manifest = pbp.read_manifest()
    digest = "".join(manifest.get(str(s), {}).get("sha256", "?")[:8] for s in seasons)
    # One run per day per (definitions, play-by-play content): unchanged data is never rewritten.
    data = hashlib.sha256(f"{STATS_VERSION}|{digest}".encode()).hexdigest()[:12]
    key = job_key or f"team-stats:{seasons[0]}-{seasons[-1]}:{datetime.now(timezone.utc):%Y-%m-%d}:{data}"
    with connect() as conn:
        claim = claim_run(conn, key, "team-stats")
        conn.commit()
        if claim.run_id is None:
            print(f"job {key}: {claim.status}; nothing to do")
            return
        try:
            with conn.transaction():
                finals = final_game_ids(conn, seasons)
                n, skipped = 0, 0
                for season, frame in frames.items():
                    final = frame.filter(frame["game_id"].is_in(list(finals)))
                    skipped += frame.height - final.height
                    n += replace_team_game_stats(conn, season, final.to_dicts(), STATS_VERSION)
                finish_run(conn, claim.run_id, n, version)
            print(f"job {key}: wrote {n} team-games" + (f"; skipped {skipped} not final in nfl_games" if skipped else ""))
        except Exception as exc:
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
    t = sub.add_parser("team-stats")
    t.add_argument("--seasons", default="2016-2026")
    t.add_argument("--refresh", action="store_true", help="re-download play-by-play before aggregating")
    t.add_argument("--dry-run", action="store_true")
    t.add_argument("--job-key")
    args = parser.parse_args()
    if args.dataset == "schedules":
        ingest_schedules(parse_seasons(args.seasons), args.dry_run, args.job_key)
    elif args.dataset == "team-stats":
        ingest_team_stats(parse_seasons(args.seasons), args.refresh, args.dry_run, args.job_key)


if __name__ == "__main__":
    main()
