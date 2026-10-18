"""Writes to the football tables (upserts; idempotent)."""

from __future__ import annotations

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
