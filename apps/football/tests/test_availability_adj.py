"""Non-QB availability: recent snap shares, P(miss) from the report and reserve status,
point-in-time (never the game's own snaps), season boundary."""

import pandas as pd
import pytest

from marketscope_football.ratings.availability_adj import AvailabilityAdjuster, absences

T0 = pd.Timestamp("2020-09-13", tz="UTC")


def games(n, season=2020):
    return pd.DataFrame({"game_id": [f"{season}_{i}" for i in range(n)], "season": season, "week": range(1, n + 1),
                         "kickoff_utc": [T0 + pd.Timedelta(days=7 * i + 365 * (season - 2020)) for i in range(n)],
                         "home": "KC", "away": "NE"})


def snaps(rows):
    return pd.DataFrame(rows, columns=["game_id", "team", "player", "group", "share"])


def report(rows):
    return pd.DataFrame(rows, columns=["season", "week", "team", "gsis_id", "report_status"])


def reserve(rows):
    return pd.DataFrame(rows, columns=["season", "week", "team", "gsis_id"])


def kc(table, week):
    return table[(table["team"] == "KC")].iloc[week - 1]


def test_recent_share_times_probability_of_missing():
    g = games(5)
    s = snaps([(f"2020_{i}", "KC", "T1", "ol", 1.0) for i in range(4)] + [("2020_0", "KC", "W1", "skill", 0.9)])
    rep = report([(2020, 4, "KC", "T1", "Questionable"), (2020, 2, "KC", "W1", "Out")])
    t = absences(g, s, rep, reserve([]))
    assert kc(t, 1)["avail_ol"] == 0 and not kc(t, 1)["has_history"]  # no earlier games
    assert kc(t, 2)["avail_skill"] == pytest.approx(0.9)  # W1 out, played 90% of the one earlier game
    assert kc(t, 4)["avail_ol"] == pytest.approx(0.323)  # questionable full-timer
    assert kc(t, 5)["avail_skill"] == 0  # W1 absent from the last 3 games: no longer counted


def test_reserve_status_counts_and_window_is_three_games():
    g = games(6)
    s = snaps([(f"2020_{i}", "KC", "C1", "db", 0.6) for i in range(2)])
    t = absences(g, s, report([]), reserve([(2020, 3, "KC", "C1"), (2020, 6, "KC", "C1")]))
    assert kc(t, 3)["avail_db"] == pytest.approx(0.6)  # placed on IR after two 60% games
    assert kc(t, 6)["avail_db"] == 0  # last 3 games without him


def test_never_uses_the_games_own_snaps_or_last_season():
    g = pd.concat([games(2, 2019), games(2, 2020)], ignore_index=True)
    s = snaps([("2019_1", "KC", "D1", "front7", 1.0), ("2020_0", "KC", "D1", "front7", 0.0)])
    rep = report([(2020, 1, "KC", "D1", "Out"), (2019, 2, "KC", "D1", "Out")])
    t = absences(g, s, rep, reserve([]))
    assert t[(t["game_id"] == "2019_1") & (t["team"] == "KC")]["avail_front7"].iloc[0] == 0  # own game's snaps unseen
    assert t[(t["game_id"] == "2020_0") & (t["team"] == "KC")]["avail_front7"].iloc[0] == 0  # new season: no history


def test_adjuster_is_home_minus_away():
    t = pd.DataFrame([{"game_id": "g", "team": "KC", "avail_ol": 1.0, "avail_skill": 0.0, "avail_rb": 0.0,
                       "avail_front7": 0.0, "avail_db": 0.5},
                      {"game_id": "g", "team": "NE", "avail_ol": 0.25, "avail_skill": 0.0, "avail_rb": 0.0,
                       "avail_front7": 0.0, "avail_db": 0.0}])
    f = AvailabilityAdjuster(t).features(pd.Series({"game_id": "g", "home": "KC", "away": "NE"}))
    assert f["avail_ol"] == pytest.approx(0.75) and f["avail_db"] == pytest.approx(0.5)
