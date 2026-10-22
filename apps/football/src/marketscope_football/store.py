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


RATING_COLUMNS = [
    "model_version", "season", "week", "team", "adj_em", "adj_em_se", "adj_em_rank", "adj_o", "adj_o_se", "adj_o_rank",
    "adj_d", "adj_d_se", "adj_d_rank", "adj_st", "adj_st_se", "adj_st_rank", "adj_pace", "adj_pace_se",
    "adj_pace_rank", "prior_weight", "pass_off", "pass_def", "rush_off", "rush_def", "succ_off", "succ_def",
    "ppd_off", "ppd_def", "games", "wins", "losses", "ties", "points_for", "points_against", "expected_wins",
    "pythag_wins", "luck", "luck_rank", "one_score_luck", "fumble_luck", "int_luck", "fg_luck", "return_td_diff",
    "sos", "sos_rank", "opp_adj_o", "opp_adj_d", "nondiv_sos", "remaining_sos", "remaining_games",
    "off_success_rate", "def_success_rate", "off_explosiveness", "def_explosiveness", "off_start_yardline",
    "def_start_yardline", "off_points_per_opp", "def_points_per_opp", "off_turnovers", "def_turnovers",
]


def replace_rating_snapshots(conn: psycopg.Connection, frame: pd.DataFrame, model_version: str) -> int:
    """Replace every snapshot of one model version. Filtered snapshots are deterministic given the
    data, so a rebuild rewrites identical history and adds the new weeks."""
    def clean(v):
        if v is None or v is pd.NA or (isinstance(v, float) and v != v):
            return None
        return v.item() if hasattr(v, "item") else v

    with conn.cursor() as cur:
        cur.execute("DELETE FROM rating_snapshots WHERE model_version = %s", (model_version,))
        with cur.copy(f"COPY rating_snapshots ({', '.join(RATING_COLUMNS)}) FROM STDIN") as copy:
            for r in frame[RATING_COLUMNS].itertuples(index=False):
                copy.write_row([clean(v) for v in r])
    return len(frame)


PROJECTION_COLUMNS = ["model_version", "season", "week", "team", "sims", "games_played", "strength", "mean_wins",
                      "win_dist", "playoff_p", "division_p", "seed1_p", "conf_p", "sb_p"]


def replace_season_projections(conn: psycopg.Connection, frame: pd.DataFrame, model_version: str) -> int:
    """Replace every season projection of one model version (deterministic given the data and seeds,
    so a rebuild rewrites identical history and adds the new weeks)."""
    import json as _json

    with conn.cursor() as cur:
        cur.execute("DELETE FROM season_projections WHERE model_version = %s", (model_version,))
        with cur.copy(f"COPY season_projections ({', '.join(PROJECTION_COLUMNS)}) FROM STDIN") as copy:
            for r in frame.assign(model_version=model_version)[PROJECTION_COLUMNS].itertuples(index=False):
                row = [v.item() if hasattr(v, "item") else v for v in r]
                row[PROJECTION_COLUMNS.index("win_dist")] = _json.dumps([float(x) for x in r.win_dist])
                copy.write_row(row)
    return len(frame)


PROVENANCE_KEYS = ("params_sha256", "feature_schema_sha256", "code_sha", "input_sha256")


def insert_predictions(conn: psycopg.Connection, rows: list[dict], model_version: str, predicted_at,
                       provenance: dict | None = None) -> int:
    """Append-only: one new row per game per run; existing rows are never touched. `provenance` (ADR-074):
    params, feature-schema and input hashes and the code commit, stored on every row of the run."""
    import json as _json

    prov = {k: (provenance or {}).get(k) for k in PROVENANCE_KEYS}
    with conn.cursor() as cur:
        cur.executemany(
            """INSERT INTO model_predictions (model_version, game_id, predicted_at, kickoff_utc, home_team, away_team,
                 expected_margin, expected_total, home_score, away_score, p_home, home_qb, away_qb, home_qb_p, away_qb_p,
                 contributions, params_sha256, feature_schema_sha256, code_sha, input_sha256)
               VALUES (%(model_version)s, %(game_id)s, %(predicted_at)s, %(kickoff_utc)s, %(home_team)s, %(away_team)s,
                 %(expected_margin)s, %(expected_total)s, %(home_score)s, %(away_score)s, %(p_home)s, %(home_qb)s,
                 %(away_qb)s, %(home_qb_p)s, %(away_qb_p)s, %(contributions)s, %(params_sha256)s,
                 %(feature_schema_sha256)s, %(code_sha)s, %(input_sha256)s)
               ON CONFLICT DO NOTHING""",
            [{**r, **prov, "model_version": model_version, "predicted_at": predicted_at,
              "contributions": _json.dumps(r["contributions"])} for r in rows],
        )
    return len(rows)


def upsert_model_run(conn: psycopg.Connection, run: dict) -> int:
    """Insert a model run from its committed JSON record (idempotent on model_version + kind + seasons + ran_at)."""
    import json as _json

    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO model_runs (model_version, run_kind, seasons, games, metrics, params_sha256, code_sha, notes, ran_at)
               SELECT %(model_version)s::text, %(run_kind)s::text, %(seasons)s::text, %(games)s::int, %(metrics)s::jsonb,
                 %(params_sha256)s::text, %(code_sha)s::text, %(notes)s::text, %(ran_at)s::timestamptz
               WHERE NOT EXISTS (SELECT 1 FROM model_runs WHERE model_version = %(model_version)s::text
                 AND run_kind = %(run_kind)s::text AND seasons = %(seasons)s::text AND ran_at = %(ran_at)s::timestamptz)""",
            {**run, "metrics": _json.dumps(run["metrics"])},
        )
        return cur.rowcount
