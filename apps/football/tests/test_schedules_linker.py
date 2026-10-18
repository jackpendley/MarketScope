from datetime import datetime, timezone

import pandas as pd

from marketscope_football.linker import match_events
from marketscope_football.schedules import game_rows, home_spread_from_nflverse, kickoff_utc, team_rows


def test_kickoff_is_eastern_time_with_dst():
    assert kickoff_utc("2026-09-13", "13:00") == datetime(2026, 9, 13, 17, 0, tzinfo=timezone.utc)  # EDT
    assert kickoff_utc("2026-12-13", "13:00") == datetime(2026, 12, 13, 18, 0, tzinfo=timezone.utc)  # EST


def test_nflverse_spread_sign_becomes_home_oriented():
    assert home_spread_from_nflverse(3.0) == -3.0  # home favored by 3 -> home -3
    assert home_spread_from_nflverse(-7.5) == 7.5
    assert home_spread_from_nflverse(float("nan")) is None


def schedule(**overrides):
    base = dict(game_id="2026_01_SF_LA", season=2026, game_type="REG", week=1, gameday="2026-09-10", gametime="20:35",
                away_team="SF", home_team="LA", away_score=27, home_score=7, location="Neutral", overtime=0,
                away_rest=7, home_rest=7, div_game=1, roof="dome", surface="grass", temp=None, wind=None,
                referee="Ref", home_coach="Sean McVay", away_coach="Kyle Shanahan", stadium_id="MEL00",
                stadium="MCG", home_qb_id="q1", away_qb_id="q2", spread_line=3.5, total_line=47.5,
                home_moneyline=-218, away_moneyline=180)
    base.update(overrides)
    return pd.DataFrame([base])


def test_game_rows():
    r = game_rows(schedule())[0]
    assert r["neutral_site"] and r["division_game"] and r["overtime"] is False
    assert r["nflverse_close_home_spread"] == -3.5 and r["nflverse_close_home_moneyline"] == -218
    assert r["observed_temp_f"] is None
    future = game_rows(schedule(home_score=float("nan"), away_score=float("nan"), overtime=float("nan")))[0]
    assert future["home_score"] is None and future["overtime"] is None


def test_team_rows_map_relocated_franchises_and_skip_their_odds_name():
    teams = pd.DataFrame([
        {"team_abbr": "OAK", "team_name": "Oakland Raiders", "team_nick": "Raiders", "team_conf": "AFC", "team_division": "AFC West"},
        {"team_abbr": "LV", "team_name": "Las Vegas Raiders", "team_nick": "Raiders", "team_conf": "AFC", "team_division": "AFC West"},
    ])
    oak, lv = team_rows(teams)
    alias = team_rows(pd.DataFrame([{"team_abbr": "LAR", "team_name": "Los Angeles Rams", "team_nick": "Rams",
                                     "team_conf": "NFC", "team_division": "NFC West"}]))[0]
    assert alias["franchise"] == "LA" and alias["odds_api_name"] is None
    assert oak["franchise"] == "LV" and oak["odds_api_name"] is None
    assert lv["franchise"] == "LV" and lv["odds_api_name"] == "Las Vegas Raiders"


NAMES = {"Los Angeles Rams": "LA", "San Francisco 49ers": "SF", "Seattle Seahawks": "SEA"}
GAMES = pd.DataFrame({
    "game_id": ["2026_01_SF_LA", "2026_09_LA_SF"],
    "home_team": ["LA", "SF"],
    "away_team": ["SF", "LA"],
    "kickoff_utc": pd.to_datetime(["2026-09-11T00:35:00Z", "2026-11-08T21:25:00Z"], utc=True),
})


def events(*rows):
    df = pd.DataFrame(rows, columns=["event_id", "home_team", "away_team", "commence_time"])
    df["commence_time"] = pd.to_datetime(df["commence_time"], utc=True)
    return df


def test_links_same_orientation_within_36_hours():
    r = match_events(events(("e1", "Los Angeles Rams", "San Francisco 49ers", "2026-09-11T03:00:00Z")), GAMES, NAMES)
    assert r.links == [("2026_01_SF_LA", "e1")] and r.issues == []


def test_swapped_orientation_is_reported_not_linked():
    r = match_events(events(("e1", "San Francisco 49ers", "Los Angeles Rams", "2026-09-11T00:35:00Z")), GAMES, NAMES)
    assert r.links == [] and r.issues[0]["reason"] == "swapped_orientation"


def test_unknown_team_and_no_game():
    r = match_events(events(("e1", "Springfield Isotopes", "Seattle Seahawks", "2026-09-11T00:35:00Z"),
                            ("e2", "Los Angeles Rams", "San Francisco 49ers", "2026-09-20T00:35:00Z")), GAMES, NAMES)
    assert [i["reason"] for i in r.issues] == ["unknown_team", "no_game"]
