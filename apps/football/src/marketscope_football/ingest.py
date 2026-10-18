"""Football ingest CLI.

    DATABASE_URL=... .venv/bin/python -m marketscope_football.ingest schedules  --seasons 2016-2026 [--dry-run]
    DATABASE_URL=... .venv/bin/python -m marketscope_football.ingest team-stats --seasons 2016-2026 [--refresh] [--dry-run]
    DATABASE_URL=... .venv/bin/python -m marketscope_football.ingest snaps      --seasons 2025-2026 [--dry-run]
    DATABASE_URL=... .venv/bin/python -m marketscope_football.ingest injuries   --seasons 2025-2026 [--dry-run]
    DATABASE_URL=... .venv/bin/python -m marketscope_football.ingest coaching   [--dry-run]   (data/coaching_staff.csv)
    DATABASE_URL=... .venv/bin/python -m marketscope_football.ingest context    [--dry-run]   (all seasons in nfl_games)
    DATABASE_URL=... .venv/bin/python -m marketscope_football.ingest weather    --seasons 2024-2026 [--recent] [--dry-run]

`--seasons` accepts `2016-2026`, `2025,2026` or `current`. Every run claims a job key first
(see db.py), so a repeated or overlapping run is harmless.
"""

from __future__ import annotations

import argparse
import hashlib
from collections import Counter
from collections.abc import Callable
from datetime import datetime, timezone

import nflreadpy as nfl
import pandas as pd
import psycopg

from . import pbp
from .availability import injury_rows, plan_injury_changes, snap_rows
from .coaching import validate_staff
from .db import claim_run, connect, fail_run, finish_run
from .design import STATS_VERSION
from .linker import match_events
from .schedules import game_rows, team_rows
from .store import (apply_injury_plan, apply_links, final_game_ids, latest_injury_rows, load_games_frame,
                    load_link_inputs, replace_coaching_staff, replace_game_context, replace_snaps,
                    replace_team_game_stats, team_kickoffs, upsert_games, upsert_teams, upsert_weather)
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


def _span(seasons: list[int]) -> str:
    return f"{seasons[0]}-{seasons[-1]}"


def _today() -> str:
    return f"{datetime.now(timezone.utc):%Y-%m-%d}"


def run_job(key: str, dataset: str, version: str, work: Callable[[psycopg.Connection], tuple[int, str]]) -> None:
    """Claim `key`, run `work` in one transaction, and record the outcome. `work` returns
    (rows written, summary). A failure is recorded on the run, then re-raised."""
    with connect() as conn:
        claim = claim_run(conn, key, dataset)
        conn.commit()
        if claim.run_id is None:
            print(f"job {key}: {claim.status}; nothing to do")
            return
        try:
            with conn.transaction():
                n, summary = work(conn)
                finish_run(conn, claim.run_id, n, version)
            print(f"job {key}: {summary}")
        except Exception as exc:
            conn.rollback()
            fail_run(conn, claim.run_id, f"{type(exc).__name__}: {exc}")
            conn.commit()
            raise


def ingest_schedules(seasons: list[int], dry_run: bool, job_key: str | None) -> None:
    teams = nfl.load_teams().to_pandas()
    schedules = nfl.load_schedules(seasons).to_pandas()
    t_rows, g_rows = team_rows(teams), game_rows(schedules)
    digest = hashlib.sha256(schedules.to_csv(index=False).encode()).hexdigest()[:16]
    finals = sum(r["home_score"] is not None for r in g_rows)
    print(f"nflverse: {len(t_rows)} teams, {len(g_rows)} games ({finals} final), seasons {_span(seasons)}")
    if dry_run:
        return

    def work(conn: psycopg.Connection) -> tuple[int, str]:
        n = upsert_teams(conn, t_rows) + upsert_games(conn, g_rows)
        events, games, names = load_link_inputs(conn)
        result = match_events(events, games, names)
        apply_links(conn, result)
        reasons = Counter(i["reason"] for i in result.issues)
        return n, (f"upserted {n} rows; linked {len(result.links)} of {len(events)} odds events"
                   + (f"; unlinked: {dict(reasons)}" if reasons else ""))

    run_job(job_key or f"schedules:{_span(seasons)}:{_today()}", "schedules",
            f"nflreadpy {nfl.__version__}; schedules sha256:{digest}", work)


def ingest_team_stats(seasons: list[int], refresh: bool, dry_run: bool, job_key: str | None) -> None:
    """Aggregate cached play-by-play into nfl_team_game_stats for games final in nfl_games.
    `refresh` re-downloads play-by-play (use for the current season; past seasons are stable)."""
    frames = {s: team_game_stats(pbp.load_season(s, refresh=refresh)) for s in seasons}
    print(f"play-by-play: {sum(f.height for f in frames.values())} team-games, seasons {_span(seasons)}")
    if dry_run:
        return
    manifest = pbp.read_manifest()
    digest = "".join(manifest.get(str(s), {}).get("sha256", "?")[:8] for s in seasons)
    # One run per day per (definitions, play-by-play content): unchanged data is never rewritten.
    data = hashlib.sha256(f"{STATS_VERSION}|{digest}".encode()).hexdigest()[:12]

    def work(conn: psycopg.Connection) -> tuple[int, str]:
        finals = final_game_ids(conn, seasons)
        n, skipped = 0, 0
        for season, frame in frames.items():
            final = frame.filter(frame["game_id"].is_in(list(finals)))
            skipped += frame.height - final.height
            n += replace_team_game_stats(conn, season, final.to_dicts(), STATS_VERSION)
        return n, f"wrote {n} team-games" + (f"; skipped {skipped} not final in nfl_games" if skipped else "")

    run_job(job_key or f"team-stats:{_span(seasons)}:{_today()}:{data}", "team-stats",
            f"{STATS_VERSION}; {pbp.source_version(seasons)}", work)


def ingest_snaps(seasons: list[int], dry_run: bool, job_key: str | None) -> None:
    players = nfl.load_players()
    frames = {s: snap_rows(nfl.load_snap_counts([s]), players) for s in seasons}
    rows = sum(f.height for f in frames.values())
    unmapped = sum(f["gsis_id"].null_count() for f in frames.values())
    digest = hashlib.sha256(b"".join(f.write_csv().encode() for f in frames.values())).hexdigest()[:12]
    print(f"snap counts: {rows} player-games ({unmapped} without a gsis_id), seasons {_span(seasons)}")
    if dry_run:
        return

    def work(conn: psycopg.Connection) -> tuple[int, str]:
        n = sum(replace_snaps(conn, s, f.to_dicts()) for s, f in frames.items())
        return n, f"wrote {n} player-games" + (f"; dropped {rows - n} for games not in nfl_games" if rows > n else "")

    run_job(job_key or f"snaps:{_span(seasons)}:{_today()}:{digest}", "snaps",
            f"nflreadpy {nfl.__version__}; snap_counts sha256:{digest}", work)


def ingest_injuries(seasons: list[int], dry_run: bool, job_key: str | None) -> None:
    """Snapshot injury reports: append status changes seen before kickoff (live), keep the final
    report for games already played (backfill). Safe to run several times a day."""
    fetched = injury_rows(nfl.load_injuries(seasons))
    print(f"injury reports: {len(fetched)} player-weeks, seasons {_span(seasons)}")
    if dry_run:
        return
    now = datetime.now(timezone.utc)

    def work(conn: psycopg.Connection) -> tuple[int, str]:
        games = team_kickoffs(conn, seasons)
        plan = plan_injury_changes(fetched, latest_injury_rows(conn, seasons),
                                   {k: v[1] for k, v in games.items()}, now)
        n = apply_injury_plan(conn, plan, {k: v[0] for k, v in games.items()})
        live = sum(r["first_seen_at"] is not None for r in plan.inserts)
        return n, (f"{live} live and {len(plan.inserts) - live} backfill rows inserted; {len(plan.touch)} unchanged; "
                   f"{len(plan.backfill_updates)} backfill corrections")

    run_job(job_key or f"injuries:{_span(seasons)}:{now:%Y-%m-%dT%H}", "injuries", f"nflreadpy {nfl.__version__}", work)


def ingest_coaching(dry_run: bool, job_key: str | None) -> None:
    """Load the curated coaching CSV (validated first: a broken file never reaches the DB)."""
    import csv
    from pathlib import Path

    path = Path(__file__).resolve().parents[2] / "data" / "coaching_staff.csv"
    raw = path.read_bytes()
    rows = list(csv.DictReader(raw.decode().splitlines()))
    problems = validate_staff(rows)
    if problems:
        raise SystemExit("coaching_staff.csv is invalid:\n" + "\n".join(problems[:20]))
    digest = hashlib.sha256(raw).hexdigest()[:12]
    print(f"coaching staff: {len(rows)} rows, seasons {min(r['season'] for r in rows)}-{max(r['season'] for r in rows)}")
    if dry_run:
        return

    def work(conn: psycopg.Connection) -> tuple[int, str]:
        n = replace_coaching_staff(conn, rows)
        return n, f"loaded {n} coaching rows"

    run_job(job_key or f"coaching:{digest}", "coaching", f"coaching_staff.csv sha256:{digest}", work)


def _games_with_venues(conn: psycopg.Connection, seasons: list[int] | None = None):
    from . import venues

    games = load_games_frame(conn, seasons)
    alias = venues.aliases()
    unknown = sorted(set(games["stadium"].dropna()) - set(alias))
    if unknown or games["stadium"].isna().any():
        raise SystemExit(f"stadiums missing from data/venue_aliases.csv: {unknown or 'NULL stadium'}")
    venue_key = games["stadium"].map(alias)
    fixed = games["game_id"].map(venues.overrides())
    return games.assign(venue_key=fixed.fillna(venue_key)), venues.venues()


def ingest_context(dry_run: bool, job_key: str | None) -> None:
    """Rebuild nfl_game_context for every game in nfl_games (schedule + venues + coaching)."""
    import csv
    from pathlib import Path

    from .context import team_game_context

    staff_path = Path(__file__).resolve().parents[2] / "data" / "coaching_staff.csv"
    staff = list(csv.DictReader(staff_path.read_text().splitlines()))
    prior = nfl.load_schedules(list(range(1999, 2016))).to_pandas()
    prior_hc = pd.concat([
        prior[["gameday", "home_team", "home_coach"]].set_axis(["kickoff_utc", "team", "coach"], axis=1),
        prior[["gameday", "away_team", "away_coach"]].set_axis(["kickoff_utc", "team", "coach"], axis=1),
    ])
    prior_hc["kickoff_utc"] = pd.to_datetime(prior_hc["kickoff_utc"], utc=True)
    with connect() as conn:
        games, venue_map = _games_with_venues(conn)
    frame = team_game_context(games, venue_map, staff, prior_hc)
    print(f"context: {len(frame)} team-games")
    if dry_run:
        return
    digest = hashlib.sha256(pd.util.hash_pandas_object(frame.astype(str), index=False).values.tobytes()).hexdigest()[:12]
    run_job(job_key or f"context:{_today()}:{digest}", "context", f"context sha:{digest}",
            lambda conn: (replace_game_context(conn, frame), f"wrote {len(frame)} team-games"))


def ingest_weather(seasons: list[int], recent: bool, dry_run: bool, job_key: str | None) -> None:
    """Point-in-time forecasts (Open-Meteo Previous Runs, 2024+) for outdoor/retractable venues.
    `recent` limits to games from 10 days ago to 8 days ahead (the daily job)."""
    from datetime import timedelta

    from .weather import fetch_for_games

    now = datetime.now(timezone.utc)
    with connect() as conn:
        games, venue_map = _games_with_venues(conn, seasons)
    games = games[pd.to_datetime(games["kickoff_utc"], utc=True) >= pd.Timestamp("2024-01-01", tz="UTC")]
    if recent:
        k = pd.to_datetime(games["kickoff_utc"], utc=True)
        games = games[(k >= now - timedelta(days=10)) & (k <= now + timedelta(days=8))]
    rows = fetch_for_games(games[["game_id", "kickoff_utc", "venue_key"]], venue_map, now)
    print(f"weather: {len(rows)} game-lead forecasts for {len(set(r['game_id'] for r in rows))} games")
    if dry_run or not rows:
        return
    run_job(job_key or f"weather:{_span(seasons)}:{now:%Y-%m-%dT%H}{':recent' if recent else ''}", "weather",
            "open-meteo previous-runs api", lambda conn: (upsert_weather(conn, rows), f"upserted {len(rows)} forecasts"))


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="dataset", required=True)
    for name in ("schedules", "team-stats", "snaps", "injuries", "coaching", "context", "weather"):
        p = sub.add_parser(name)
        p.add_argument("--seasons", default="current")
        p.add_argument("--dry-run", action="store_true")
        p.add_argument("--job-key")
        if name == "team-stats":
            p.add_argument("--refresh", action="store_true", help="re-download play-by-play before aggregating")
        if name == "weather":
            p.add_argument("--recent", action="store_true", help="only games from 10 days ago to 8 days ahead")
    args = parser.parse_args()
    seasons = parse_seasons(args.seasons)
    if args.dataset == "schedules":
        ingest_schedules(seasons, args.dry_run, args.job_key)
    elif args.dataset == "team-stats":
        ingest_team_stats(seasons, args.refresh, args.dry_run, args.job_key)
    elif args.dataset == "snaps":
        ingest_snaps(seasons, args.dry_run, args.job_key)
    elif args.dataset == "coaching":
        ingest_coaching(args.dry_run, args.job_key)
    elif args.dataset == "context":
        ingest_context(args.dry_run, args.job_key)
    elif args.dataset == "weather":
        ingest_weather(seasons, args.recent, args.dry_run, args.job_key)
    else:
        ingest_injuries(seasons, args.dry_run, args.job_key)


if __name__ == "__main__":
    main()
