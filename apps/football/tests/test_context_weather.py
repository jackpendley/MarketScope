"""Game context (rest, travel, time zones, tenure) and point-in-time weather rows."""

from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from marketscope_football.context import team_game_context, tenure, utc_offset_hours
from marketscope_football.venues import haversine_km
from marketscope_football.weather import game_rows

VENUES = {
    "SEA": {"roof_type": "outdoor", "lat": "47.5952", "lon": "-122.3316", "elevation_m": "10", "timezone": "America/Los_Angeles"},
    "NYJ": {"roof_type": "outdoor", "lat": "40.8135", "lon": "-74.0745", "elevation_m": "3", "timezone": "America/New_York"},
    "DEN": {"roof_type": "outdoor", "lat": "39.7439", "lon": "-105.0201", "elevation_m": "1581", "timezone": "America/Denver"},
    "LON": {"roof_type": "outdoor", "lat": "51.5560", "lon": "-0.2794", "elevation_m": "47", "timezone": "Europe/London"},
}


def games() -> pd.DataFrame:
    rows = [
        # game_id, week, kickoff (UTC), home, away, neutral, venue, home_rest, away_rest
        ("g1", 1, "2025-09-07 17:00", "NYJ", "SEA", False, "NYJ", None, None),
        ("g2", 2, "2025-09-14 20:05", "DEN", "SEA", False, "DEN", 7, 7),
        ("g3", 3, "2025-09-21 20:05", "SEA", "DEN", False, "SEA", 7, 7),
        ("g4", 4, "2025-09-28 13:30", "NYJ", "DEN", True, "LON", 7, 7),
        ("g5", 6, "2025-10-12 17:00", "NYJ", "SEA", False, "NYJ", 14, 21),
    ]
    df = pd.DataFrame(rows, columns=["game_id", "week", "kickoff_utc", "home_team", "away_team", "neutral_site",
                                     "venue_key", "home_rest_days", "away_rest_days"])
    df["kickoff_utc"] = pd.to_datetime(df["kickoff_utc"], utc=True)
    return df.assign(season=2025, division_game=False)


def staff() -> list[dict]:
    def row(team, role, coach, a, b, off=False, de=False):
        return {"season": "2025", "team": team, "role": role, "coach_id": coach, "coach_name": coach,
                "from_week": str(a), "to_week": str(b), "offense_playcaller": str(off), "defense_playcaller": str(de)}
    return [row("SEA", "HC", "Mike Macdonald", 1, 18, de=True), row("SEA", "OC", "Klint Kubiak", 1, 18, off=True),
            row("DEN", "HC", "Sean Payton", 1, 18, off=True), row("DEN", "DC", "Vance Joseph", 1, 18, de=True),
            row("NYJ", "HC", "Aaron Glenn", 1, 18), row("NYJ", "OC", "Tanner Engstrand", 1, 3, off=True),
            row("NYJ", "OC", "New Caller", 4, 18, off=True), row("NYJ", "DC", "Steve Wilks", 1, 18, de=True)]


def ctx() -> pd.DataFrame:
    prior = pd.DataFrame({"kickoff_utc": pd.to_datetime(["2024-12-29", "2025-01-05"], utc=True),
                          "team": ["DEN", "DEN"], "coach": ["Sean Payton", "Sean Payton"]})
    return team_game_context(games(), VENUES, staff(), prior)


def pick(df, game, team) -> dict:
    return df[(df["game_id"] == game) & (df["team"] == team)].iloc[0].to_dict()


def test_travel_time_zones_and_body_clock():
    df = ctx()
    sea = pick(df, "g1", "SEA")
    assert sea["is_home"] is False and sea["home_venue_key"] == "SEA"
    assert sea["travel_km"] == pytest.approx(haversine_km(47.5952, -122.3316, 40.8135, -74.0745), abs=0.1)
    assert sea["tz_shift_hours"] == 3  # Pacific team playing in the Eastern zone
    assert sea["body_clock_kickoff_hour"] == 10.0  # 1 pm ET = 10 am Pacific
    assert pick(df, "g1", "NYJ")["travel_km"] == 0 and pick(df, "g1", "NYJ")["is_home"] is True
    assert pick(df, "g2", "SEA")["altitude_change_m"] == 1581 - 10
    london = pick(df, "g4", "NYJ")
    assert london["is_home"] is False and london["neutral_site"] is True and london["tz_shift_hours"] == 5


def test_rest_byes_and_road_streaks():
    df = ctx()
    assert pick(df, "g5", "NYJ")["bye_before"] is True and pick(df, "g5", "NYJ")["rest_diff"] == -7
    assert pick(df, "g2", "SEA")["short_week"] is False
    # SEA: away g1, away g2, home g3 -> streaks 1, 2, 0; DEN: home g2, away g3, neutral g4 -> 0, 1, 2
    assert [pick(df, g, "SEA")["road_streak"] for g in ("g1", "g2", "g3")] == [1, 2, 0]
    assert [pick(df, g, "DEN")["road_streak"] for g in ("g2", "g3", "g4")] == [0, 1, 2]


def test_tenure_counts_prior_games_and_marks_censored_runs():
    assert tenure([("a", "x"), ("b", "x"), ("c", "y"), ("d", "y")]) == [0, 1, 0, 1]
    df = ctx()
    # Payton's prior 2024 games seed head-coach tenure: 2 before g2.
    assert pick(df, "g2", "DEN")["hc_tenure_games"] == 2
    # Play-caller runs that began at the first game we have are left-censored (NULL).
    assert pd.isna(pick(df, "g1", "NYJ")["off_playcaller_tenure_games"])
    nyj_new = pick(df, "g4", "NYJ")
    assert nyj_new["off_playcaller"] == "New Caller" and nyj_new["off_playcaller_tenure_games"] == 0
    assert bool(nyj_new["new_off_playcaller"]) is True


def test_utc_offsets_follow_daylight_saving():
    assert utc_offset_hours("America/New_York", datetime(2025, 9, 7, tzinfo=timezone.utc)) == -4
    assert utc_offset_hours("America/New_York", datetime(2025, 12, 7, tzinfo=timezone.utc)) == -5


def hourly(start="2025-09-07 17:00", hours=6) -> pd.DataFrame:
    idx = pd.date_range(start, periods=hours, freq="h", tz="UTC")
    data = {}
    for var, base in (("temperature_2m", 70.0), ("wind_speed_10m", 10.0), ("wind_gusts_10m", 20.0),
                      ("precipitation", 0.01)):
        for n in (0, 1, 3, 7):
            name = f"{var}_previous_day{n}" if n else var
            data[name] = [base + n + i for i in range(hours)]
    return pd.DataFrame(data, index=idx)


def test_weather_rows_average_the_game_window_and_respect_lead_availability():
    g = pd.DataFrame({"game_id": ["g1"], "kickoff_utc": [pd.Timestamp("2025-09-07 17:25", tz="UTC")]})
    now = datetime(2025, 9, 5, 12, tzinfo=timezone.utc)  # 2 days before: leads 3 and 7 exist, 0 and 1 not yet
    rows = {r["lead_days"]: r for r in game_rows(g, hourly(), now)}
    assert sorted(rows) == [3, 7]
    r3 = rows[3]
    assert r3["forecast_hour_utc"] == datetime(2025, 9, 7, 17, tzinfo=timezone.utc)
    assert r3["temperature_f"] == pytest.approx(70 + 3 + 1.5)  # mean of hours 0-3
    assert r3["gust_mph"] == pytest.approx(20 + 3 + 3)  # max over the window
    assert r3["precip_in"] == pytest.approx(sum(0.01 + 3 + i for i in range(4)))
    later = game_rows(g, hourly(), now + timedelta(days=3))
    assert sorted(r["lead_days"] for r in later) == [0, 1, 3, 7]


def test_weather_rows_skip_incomplete_windows():
    g = pd.DataFrame({"game_id": ["g1"], "kickoff_utc": [pd.Timestamp("2025-09-07 21:00", tz="UTC")]})
    assert game_rows(g, hourly(hours=6), datetime(2025, 10, 1, tzinfo=timezone.utc)) == []
    h = hourly()
    h.iloc[1, 0] = None
    g2 = pd.DataFrame({"game_id": ["g1"], "kickoff_utc": [pd.Timestamp("2025-09-07 17:00", tz="UTC")]})
    assert 0 not in {r["lead_days"] for r in game_rows(g2, h, datetime(2025, 10, 1, tzinfo=timezone.utc))}
