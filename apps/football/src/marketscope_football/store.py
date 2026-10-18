"""Writes to the football tables (upserts; idempotent)."""

from __future__ import annotations

from datetime import datetime

import pandas as pd
import psycopg

from .linker import LinkResult

GAME_COLUMNS = [
    "game_id", "season", "game_type", "week", "kickoff_utc", "home_team", "away_team", "neutral_site",
    "division_game", "home_rest_days", "away_rest_days", "home_score", "away_score", "overtime", "stadium_id",
    "stadium", "roof", "surface", "observed_temp_f", "observed_wind_mph", "referee", "home_coach", "away_coach",
    "home_qb_id", "away_qb_id", "nflverse_close_home_spread", "nflverse_close_total",
    "nflverse_close_home_moneyline", "nflverse_close_away_moneyline",
]


def upsert_teams(conn: psycopg.Connection, rows: list[dict]) -> int:
    with conn.cursor() as cur:
        cur.executemany(
            """INSERT INTO nfl_teams (abbr, franchise, full_name, nickname, conference, division, odds_api_name)
               VALUES (%(abbr)s, %(franchise)s, %(full_name)s, %(nickname)s, %(conference)s, %(division)s, %(odds_api_name)s)
               ON CONFLICT (abbr) DO UPDATE SET franchise = EXCLUDED.franchise, full_name = EXCLUDED.full_name,
                 nickname = EXCLUDED.nickname, conference = EXCLUDED.conference, division = EXCLUDED.division,
                 odds_api_name = EXCLUDED.odds_api_name""",
            rows,
        )
    return len(rows)


def upsert_games(conn: psycopg.Connection, rows: list[dict]) -> int:
    cols = ", ".join(GAME_COLUMNS)
    values = ", ".join(f"%({c})s" for c in GAME_COLUMNS)
    updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in GAME_COLUMNS if c != "game_id")
    with conn.cursor() as cur:
        cur.executemany(
            f"""INSERT INTO nfl_games ({cols}) VALUES ({values})
                ON CONFLICT (game_id) DO UPDATE SET {updates},
                  -- Stamp the moment we first saw a final score, but only for a game we already
                  -- held without one (backfilled finals stay NULL: no import time on history).
                  final_observed_at = COALESCE(nfl_games.final_observed_at,
                    CASE WHEN nfl_games.home_score IS NULL AND EXCLUDED.home_score IS NOT NULL THEN now() END),
                  updated_at = now()""",
            rows,
        )
    return len(rows)


def load_link_inputs(conn: psycopg.Connection) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, str]]:
    def frame(query: str) -> pd.DataFrame:
        with conn.cursor() as cur:
            cur.execute(query)
            return pd.DataFrame(cur.fetchall(), columns=[c.name for c in cur.description])

    events = frame("SELECT id::text AS event_id, home_team, away_team, commence_time_utc AS commence_time FROM events")
    games = frame("SELECT game_id, home_team, away_team, kickoff_utc FROM nfl_games")
    names = frame("SELECT odds_api_name, abbr FROM nfl_teams WHERE odds_api_name IS NOT NULL")
    for df, col in ((events, "commence_time"), (games, "kickoff_utc")):
        if not df.empty:
            df[col] = pd.to_datetime(df[col], utc=True)
    return events, games, dict(zip(names["odds_api_name"], names["abbr"]))


def apply_links(conn: psycopg.Connection, result: LinkResult) -> int:
    """Make nfl_games.event_id exactly reflect `result.links`."""
    with conn.cursor() as cur:
        linked_events = [e for _, e in result.links]
        cur.execute("UPDATE nfl_games SET event_id = NULL WHERE event_id IS NOT NULL AND NOT (event_id::text = ANY(%s))",
                    (linked_events,))
        # Clear first so moving a link between games never trips the unique constraint.
        cur.execute("UPDATE nfl_games SET event_id = NULL WHERE event_id::text = ANY(%s)", (linked_events,))
        cur.executemany("UPDATE nfl_games SET event_id = %s::uuid WHERE game_id = %s",
                        [(e, g) for g, e in result.links])
    return len(result.links)


def final_game_ids(conn: psycopg.Connection, seasons: list[int]) -> set[str]:
    """Games with a final score in nfl_games; only these get team-game stats (no partial games)."""
    rows = conn.execute(
        "SELECT game_id FROM nfl_games WHERE season = ANY(%s) AND home_score IS NOT NULL", (seasons,)
    ).fetchall()
    return {r[0] for r in rows}


def replace_team_game_stats(conn: psycopg.Connection, season: int, rows: list[dict], stats_version: str) -> int:
    """Replace one season's rows wholesale, so a definition change never leaves a mix of versions."""
    if not rows:
        return 0
    cols = list(rows[0].keys()) + ["stats_version"]
    with conn.cursor() as cur:
        cur.execute("DELETE FROM nfl_team_game_stats WHERE season = %s", (season,))
        with cur.copy(f"COPY nfl_team_game_stats ({', '.join(cols)}) FROM STDIN") as copy:
            for r in rows:
                copy.write_row([*r.values(), stats_version])
    return len(rows)


def replace_snaps(conn: psycopg.Connection, season: int, rows: list[dict]) -> int:
    """Replace one season's snap counts (only games present in nfl_games)."""
    if not rows:
        return 0
    cols = list(rows[0].keys())
    with conn.cursor() as cur:
        cur.execute("DELETE FROM nfl_player_game_snaps WHERE season = %s", (season,))
        cur.execute("DROP TABLE IF EXISTS snaps_in")
        cur.execute("CREATE TEMP TABLE snaps_in (LIKE nfl_player_game_snaps) ON COMMIT DROP")
        with cur.copy(f"COPY snaps_in ({', '.join(cols)}) FROM STDIN") as copy:
            for r in rows:
                copy.write_row(list(r.values()))
        cur.execute(f"""INSERT INTO nfl_player_game_snaps ({', '.join(cols)})
                        SELECT {', '.join('s.' + c for c in cols)} FROM snaps_in s
                        JOIN nfl_games g ON g.game_id = s.game_id""")
        return cur.rowcount


def team_kickoffs(conn: psycopg.Connection, seasons: list[int]) -> dict[tuple, tuple[str, datetime]]:
    """(season, week, team) -> (game_id, kickoff_utc) for both teams of every game."""
    rows = conn.execute(
        """SELECT season, week, home_team, game_id, kickoff_utc FROM nfl_games WHERE season = ANY(%s)
           UNION ALL
           SELECT season, week, away_team, game_id, kickoff_utc FROM nfl_games WHERE season = ANY(%s)""",
        (seasons, seasons),
    ).fetchall()
    return {(s, w, t): (g, k) for s, w, t, g, k in rows}


def latest_injury_rows(conn: psycopg.Connection, seasons: list[int]) -> dict[tuple, dict]:
    rows = conn.execute(
        """SELECT DISTINCT ON (season, week, team, gsis_id) season, week, team, gsis_id, id, content_hash, first_seen_at
           FROM nfl_injury_reports WHERE season = ANY(%s)
           ORDER BY season, week, team, gsis_id, first_seen_at DESC NULLS LAST, id DESC""",
        (seasons,),
    ).fetchall()
    return {(s, w, t, g): {"id": i, "content_hash": h, "first_seen_at": f} for s, w, t, g, i, h, f in rows}


INJURY_COLUMNS = [
    "season", "week", "game_type", "team", "game_id", "gsis_id", "full_name", "position", "report_status",
    "report_primary_injury", "report_secondary_injury", "practice_status", "practice_primary_injury", "content_hash",
    "first_seen_at", "last_seen_at",
]


def apply_injury_plan(conn: psycopg.Connection, plan, game_ids: dict[tuple, str]) -> int:
    def with_game(r: dict) -> dict:
        return {**r, "game_id": game_ids.get((r["season"], r["week"], r["team"]))}

    cols = ", ".join(INJURY_COLUMNS)
    values = ", ".join(f"%({c})s" for c in INJURY_COLUMNS)
    with conn.cursor() as cur:
        if plan.inserts:
            cur.executemany(f"INSERT INTO nfl_injury_reports ({cols}) VALUES ({values})",
                            [with_game(r) for r in plan.inserts])
        if plan.touch:
            cur.execute("UPDATE nfl_injury_reports SET last_seen_at = now() WHERE id = ANY(%s)", (plan.touch,))
        if plan.backfill_updates:
            sets = ", ".join(f"{c} = %({c})s" for c in INJURY_COLUMNS if c not in ("first_seen_at", "last_seen_at"))
            cur.executemany(f"UPDATE nfl_injury_reports SET {sets} WHERE id = %(id)s",
                            [with_game(r) for r in plan.backfill_updates])
    return len(plan.inserts) + len(plan.touch) + len(plan.backfill_updates)


COACHING_COLUMNS = ["season", "team", "role", "coach_id", "coach_name", "from_week", "to_week", "offense_playcaller",
                    "defense_playcaller", "source_url", "playcaller_basis", "playcaller_source_url"]


def replace_coaching_staff(conn: psycopg.Connection, rows: list[dict]) -> int:
    """Replace the whole table from the curated CSV (small; the CSV is the source of truth)."""
    def value(r: dict, c: str):
        v = r[c]
        if c in ("season", "from_week", "to_week"):
            return int(v)
        if c in ("offense_playcaller", "defense_playcaller"):
            return v in (True, "True", "true")
        return v or None

    with conn.cursor() as cur:
        cur.execute("DELETE FROM nfl_coaching_staff")
        with cur.copy(f"COPY nfl_coaching_staff ({', '.join(COACHING_COLUMNS)}) FROM STDIN") as copy:
            for r in rows:
                copy.write_row([value(r, c) for c in COACHING_COLUMNS])
    return len(rows)


def load_games_frame(conn: psycopg.Connection, seasons: list[int] | None = None) -> pd.DataFrame:
    where = "WHERE season = ANY(%s)" if seasons else ""
    with conn.cursor() as cur:
        cur.execute(f"""SELECT game_id, season, week, kickoff_utc, home_team, away_team, neutral_site, division_game,
                               home_rest_days, away_rest_days, stadium, home_score
                        FROM nfl_games {where} ORDER BY kickoff_utc""", (seasons,) if seasons else None)
        return pd.DataFrame(cur.fetchall(), columns=[c.name for c in cur.description])


CONTEXT_COLUMNS = [
    "game_id", "team", "opponent", "season", "week", "is_home", "neutral_site", "division_game", "venue_key",
    "roof_type", "rest_days", "rest_diff", "bye_before", "short_week", "home_venue_key", "travel_km",
    "tz_shift_hours", "body_clock_kickoff_hour", "venue_local_kickoff_hour", "altitude_m", "altitude_change_m",
    "road_streak", "hc_coach", "off_playcaller", "def_playcaller", "hc_tenure_games", "off_playcaller_tenure_games",
    "def_playcaller_tenure_games", "new_off_playcaller", "new_def_playcaller",
]


def replace_game_context(conn: psycopg.Connection, frame: pd.DataFrame) -> int:
    def clean(v):
        if v is None or v is pd.NA or (isinstance(v, float) and v != v):
            return None
        return v.item() if hasattr(v, "item") else v

    with conn.cursor() as cur:
        cur.execute("DELETE FROM nfl_game_context")
        with cur.copy(f"COPY nfl_game_context ({', '.join(CONTEXT_COLUMNS)}) FROM STDIN") as copy:
            for r in frame[CONTEXT_COLUMNS].itertuples(index=False):
                copy.write_row([clean(v) for v in r])
    return len(frame)


def upsert_weather(conn: psycopg.Connection, rows: list[dict]) -> int:
    with conn.cursor() as cur:
        cur.executemany(
            """INSERT INTO nfl_weather_forecasts (game_id, lead_days, forecast_hour_utc, temperature_f, wind_mph,
                 gust_mph, precip_in, source)
               VALUES (%(game_id)s, %(lead_days)s, %(forecast_hour_utc)s, %(temperature_f)s, %(wind_mph)s,
                 %(gust_mph)s, %(precip_in)s, %(source)s)
               ON CONFLICT (game_id, lead_days) DO UPDATE SET forecast_hour_utc = EXCLUDED.forecast_hour_utc,
                 temperature_f = EXCLUDED.temperature_f, wind_mph = EXCLUDED.wind_mph, gust_mph = EXCLUDED.gust_mph,
                 precip_in = EXCLUDED.precip_in, source = EXCLUDED.source, fetched_at = now()""",
            rows,
        )
    return len(rows)
