"""Integration tests against the migrated test database (TEST_DATABASE_URL; must contain 'test').
Migrations are applied by the TypeScript migrator (`pnpm db:migrate`), never by Python."""

import os
import uuid
from datetime import datetime, timezone

import psycopg
import pytest

from marketscope_football.db import claim_run, fail_run, finish_run
from marketscope_football.linker import LinkResult
from marketscope_football.store import apply_links, upsert_games, upsert_teams

URL = os.environ.get("TEST_DATABASE_URL", "postgres://localhost:5432/marketscope_test")
assert "test" in URL.rsplit("/", 1)[-1], "refusing to run against a non-test database"


@pytest.fixture
def conn():
    try:
        c = psycopg.connect(URL, connect_timeout=5)
    except psycopg.OperationalError:
        pytest.skip("test database unavailable")
    c.execute("TRUNCATE model_predictions, model_runs, rating_snapshots, nfl_game_context, nfl_weather_forecasts, nfl_coaching_staff, nfl_injury_reports, nfl_player_game_snaps, nfl_team_game_stats, nfl_games, nfl_teams, nfl_ingest_runs, events RESTART IDENTITY CASCADE")
    c.commit()
    yield c
    c.rollback()
    c.close()


TEAMS = [
    {"abbr": a, "franchise": a, "full_name": n, "nickname": n.split()[-1], "conference": "NFC",
     "division": "NFC West", "odds_api_name": n}
    for a, n in [("LA", "Los Angeles Rams"), ("SF", "San Francisco 49ers")]
]


def game(**overrides):
    row = {c: None for c in [
        "home_rest_days", "away_rest_days", "home_score", "away_score", "overtime", "stadium_id", "stadium", "roof",
        "surface", "observed_temp_f", "observed_wind_mph", "referee", "home_coach", "away_coach", "home_qb_id",
        "away_qb_id", "nflverse_close_home_spread", "nflverse_close_total", "nflverse_close_home_moneyline",
        "nflverse_close_away_moneyline"]}
    row.update(game_id="2026_01_SF_LA", season=2026, game_type="REG", week=1,
               kickoff_utc=datetime(2026, 9, 11, 0, 35, tzinfo=timezone.utc), home_team="LA", away_team="SF",
               neutral_site=True, division_game=True)
    row.update(overrides)
    return row


def test_claim_is_idempotent_and_failed_runs_are_reclaimed(conn):
    first = claim_run(conn, "schedules:test", "schedules")
    assert first.status == "claimed"
    assert claim_run(conn, "schedules:test", "schedules").status == "in-progress"
    fail_run(conn, first.run_id, "boom")
    again = claim_run(conn, "schedules:test", "schedules")
    assert again.status == "claimed" and again.run_id == first.run_id
    finish_run(conn, again.run_id, 3, "v")
    assert claim_run(conn, "schedules:test", "schedules").status == "already-completed"
    assert conn.execute("SELECT attempt, rows_upserted FROM nfl_ingest_runs").fetchone() == (2, 3)


def test_final_observed_at_only_stamps_games_we_saw_become_final(conn):
    upsert_teams(conn, TEAMS)
    upsert_games(conn, [game(home_score=7, away_score=27)])  # already final at first sight
    assert conn.execute("SELECT final_observed_at FROM nfl_games").fetchone()[0] is None
    upsert_games(conn, [game(game_id="2026_09_LA_SF", home_team="SF", away_team="LA")])  # future game
    upsert_games(conn, [game(game_id="2026_09_LA_SF", home_team="SF", away_team="LA", home_score=20, away_score=17)])
    stamped = conn.execute("SELECT final_observed_at FROM nfl_games WHERE game_id = '2026_09_LA_SF'").fetchone()[0]
    assert stamped is not None
    upsert_games(conn, [game(game_id="2026_09_LA_SF", home_team="SF", away_team="LA", home_score=20, away_score=17)])
    assert conn.execute("SELECT final_observed_at FROM nfl_games WHERE game_id = '2026_09_LA_SF'").fetchone()[0] == stamped


def test_apply_links_moves_and_clears(conn):
    upsert_teams(conn, TEAMS)
    upsert_games(conn, [game(), game(game_id="2026_09_LA_SF", home_team="SF", away_team="LA")])
    e1, e2 = str(uuid.uuid4()), str(uuid.uuid4())
    for e in (e1, e2):
        conn.execute("""INSERT INTO events (id, provider_event_id, sport_key, season, home_team, away_team, commence_time_utc)
                        VALUES (%s, %s, 'americanfootball_nfl', 2026, 'x', 'y', now())""", (e, e))
    apply_links(conn, LinkResult(links=[("2026_01_SF_LA", e1)]))
    apply_links(conn, LinkResult(links=[("2026_09_LA_SF", e1), ("2026_01_SF_LA", e2)]))
    got = dict(conn.execute("SELECT game_id, event_id::text FROM nfl_games").fetchall())
    assert got == {"2026_09_LA_SF": e1, "2026_01_SF_LA": e2}
    apply_links(conn, LinkResult(links=[]))
    assert conn.execute("SELECT count(event_id) FROM nfl_games").fetchone()[0] == 0


def test_team_game_stats_replace_a_season_and_only_final_games_qualify(conn):
    from test_team_stats import frame, play

    from marketscope_football.store import final_game_ids, replace_team_game_stats
    from marketscope_football.team_stats import team_game_stats

    upsert_teams(conn, TEAMS)
    upsert_games(conn, [game(game_id="2025_01_SF_LA", season=2025), game(game_id="2025_02_SF_LA", season=2025, week=2)])
    conn.execute("UPDATE nfl_games SET home_score = 20, away_score = 17 WHERE game_id = '2025_01_SF_LA'")
    assert final_game_ids(conn, [2025]) == {"2025_01_SF_LA"}

    rows = team_game_stats(frame([play(1, epa=0.5)])).to_dicts()
    assert replace_team_game_stats(conn, 2025, rows, "v1") == 2
    assert replace_team_game_stats(conn, 2025, rows, "v2") == 2  # a rerun replaces, never duplicates
    got = conn.execute(
        "SELECT team, plays, epa_per_play, epa_per_dropback, stats_version FROM nfl_team_game_stats ORDER BY team"
    ).fetchall()
    assert got == [("LA", 1, 0.5, None, "v2"), ("SF", 0, None, None, "v2")]


def test_injury_snapshots_append_live_changes_and_link_the_game(conn):
    from datetime import timedelta

    from test_availability import injury, rows

    from marketscope_football.availability import plan_injury_changes
    from marketscope_football.store import apply_injury_plan, latest_injury_rows, team_kickoffs

    upsert_teams(conn, TEAMS)
    kickoff = datetime(2026, 9, 11, 0, 35, tzinfo=timezone.utc)
    upsert_games(conn, [game(kickoff_utc=kickoff)])
    games = team_kickoffs(conn, [2026])
    assert games[(2026, 1, "SF")] == ("2026_01_SF_LA", kickoff)

    def fetch(status: str, at: datetime) -> None:
        fetched = rows(injury(week=1, team="SF", report_status=status))
        plan = plan_injury_changes(fetched, latest_injury_rows(conn, [2026]), {k: v[1] for k, v in games.items()}, at)
        apply_injury_plan(conn, plan, {k: v[0] for k, v in games.items()})

    fetch("Questionable", kickoff - timedelta(days=2))
    fetch("Questionable", kickoff - timedelta(days=1))  # unchanged: touch
    fetch("Out", kickoff - timedelta(hours=20))  # change: new live row
    fetch("Questionable", kickoff + timedelta(hours=1))  # after kickoff: frozen
    got = conn.execute(
        """SELECT report_status, game_id, first_seen_at = last_seen_at FROM nfl_injury_reports
           ORDER BY first_seen_at"""
    ).fetchall()
    assert got == [("Questionable", "2026_01_SF_LA", False), ("Out", "2026_01_SF_LA", True)]


def test_snaps_replace_a_season_and_skip_unknown_games(conn):
    from marketscope_football.store import replace_snaps

    upsert_teams(conn, TEAMS)
    upsert_games(conn, [game()])
    base = {"season": 2026, "week": 1, "gsis_id": "00-1", "player": "A", "position": "WR", "team": "LA",
            "offense_snaps": 50, "offense_pct": 0.8, "defense_snaps": 0, "defense_pct": 0.0, "st_snaps": 3,
            "st_pct": 0.1}
    snaps = [{"game_id": "2026_01_SF_LA", "pfr_player_id": "PA", **base},
             {"game_id": "2026_09_XX_YY", "pfr_player_id": "PA", **base}]
    snaps = [{k: r[k] for k in ["game_id", "season", "week", "pfr_player_id", *base.keys() - {"season", "week"}]}
             for r in snaps]
    assert replace_snaps(conn, 2026, snaps) == 1
    assert replace_snaps(conn, 2026, snaps) == 1
    assert conn.execute("SELECT count(*) FROM nfl_player_game_snaps").fetchone()[0] == 1


def test_coaching_staff_replaces_the_table(conn):
    from marketscope_football.store import replace_coaching_staff

    upsert_teams(conn, TEAMS)
    base = {"season": "2026", "team": "LA", "role": "HC", "coach_id": "Sean_McVay", "coach_name": "Sean McVay",
            "from_week": "1", "to_week": "18", "offense_playcaller": "True", "defense_playcaller": "False",
            "source_url": "nflverse", "playcaller_basis": "list", "playcaller_source_url": "https://example.org"}
    assert replace_coaching_staff(conn, [base]) == 1
    assert replace_coaching_staff(conn, [base, {**base, "role": "OC", "coach_id": "X", "coach_name": "X",
                                                "offense_playcaller": "False", "playcaller_basis": ""}]) == 2
    got = conn.execute("SELECT role, offense_playcaller, playcaller_basis FROM nfl_coaching_staff ORDER BY role").fetchall()
    assert got == [("HC", True, "list"), ("OC", False, None)]


def test_weather_upsert_is_idempotent(conn):
    from marketscope_football.store import upsert_weather

    upsert_teams(conn, TEAMS)
    upsert_games(conn, [game()])
    row = {"game_id": "2026_01_SF_LA", "lead_days": 1, "forecast_hour_utc": datetime(2026, 9, 11, 0, tzinfo=timezone.utc),
           "temperature_f": 70.0, "wind_mph": 5.0, "gust_mph": 9.0, "precip_in": 0.0, "source": "test"}
    upsert_weather(conn, [row])
    upsert_weather(conn, [{**row, "wind_mph": 6.5}])
    assert conn.execute("SELECT count(*), max(wind_mph) FROM nfl_weather_forecasts").fetchone() == (1, 6.5)


def test_rating_snapshots_replace_one_model_version(conn):
    from marketscope_football.store import RATING_COLUMNS, replace_rating_snapshots
    import pandas as pd

    upsert_teams(conn, TEAMS)
    row = {c: 0.0 for c in RATING_COLUMNS}
    row.update(model_version="kalman-v0", season=2026, week=5, sos=None, remaining_sos=None)
    for c in ("adj_em_rank", "adj_o_rank", "adj_d_rank", "adj_st_rank", "adj_pace_rank", "luck_rank", "games", "wins",
              "losses", "ties", "points_for", "points_against", "return_td_diff", "remaining_games"):
        row[c] = 1
    row["sos_rank"] = None
    frame = pd.DataFrame([{**row, "team": "LA", "adj_em": 3.5}, {**row, "team": "SF", "adj_em": -3.5}])
    assert replace_rating_snapshots(conn, frame, "kalman-v0") == 2
    assert replace_rating_snapshots(conn, frame.iloc[[0]], "kalman-v0") == 1
    rows = conn.execute("SELECT team, adj_em, sos FROM rating_snapshots ORDER BY team").fetchall()
    assert rows == [("LA", 3.5, None)]
