"""QB layer: expected-starter rule, point-in-time inputs, rating and baseline arithmetic."""

import pandas as pd
import pytest

from marketscope_football.ratings.qb import QBAdjuster, QBParams, QBTracker, expected_starters

P = QBParams(half_life_days=365.0, prior_dropbacks=250.0, baseline_half_life_days=56.0, replacement=-0.1)
T0 = pd.Timestamp("2020-09-13", tz="UTC")


def games(qbs, season=2020, team="KC"):
    return pd.DataFrame({"game_id": [f"g{i}" for i in range(len(qbs))], "season": season, "week": range(1, len(qbs) + 1),
                         "kickoff_utc": [T0 + pd.Timedelta(days=7 * i) for i in range(len(qbs))], "team": team,
                         "actual_qb": qbs})


def depth(rows):
    return pd.DataFrame([{"season": 2020, "week": w, "dt": pd.NaT, "team": "KC", "rank": r, "gsis_id": q}
                         for w, r, q in rows])


def injuries(rows):
    return pd.DataFrame([{"season": 2020, "week": w, "team": "KC", "gsis_id": q, "position": "QB", "report_status": s}
                         for w, q, s in rows], columns=["season", "week", "team", "gsis_id", "position", "report_status"])


def test_expected_starter_rule():
    tg = games(["A", "A", "B", "A", "A"])
    dep = depth([(1, 1, "A"), (1, 2, "B"), (2, 1, "A"), (2, 2, "B"), (3, 1, "A"), (3, 2, "B"), (4, 1, "A"),
                 (4, 2, "B"), (5, 1, "A"), (5, 2, "C")])
    inj = injuries([(3, "A", "Out"), (5, "A", "Questionable")])
    es = expected_starters(tg, dep, inj).set_index("week")
    assert es.loc[1, "exp_qb"] == "A" and es.loc[1, "first_game"]  # first game: depth-chart QB1
    assert es.loc[2, "exp_qb"] == "A" and es.loc[2, "p_exp"] == 1.0  # previous starter
    assert es.loc[3, "exp_qb"] == "B"  # starter Out, QB1 is the injured starter -> QB2
    assert es.loc[4, "exp_qb"] == "B"  # previous starter (B) - the rule does not guess A's return
    assert (es.loc[5, "exp_qb"], es.loc[5, "alt_qb"], es.loc[5, "p_exp"]) == ("A", "C", pytest.approx(0.637))


def test_expected_starter_never_uses_the_games_own_starter():
    a = expected_starters(games(["A", "A", "A"]), depth([(1, 1, "A")]), injuries([]))
    b = expected_starters(games(["A", "A", "Z"]), depth([(1, 1, "A")]), injuries([]))
    assert list(a["exp_qb"]) == list(b["exp_qb"])
    assert b["actual_qb"].iloc[2] == "Z"


def test_rating_shrinks_toward_replacement_and_decays():
    tr = QBTracker(P)
    assert tr.rating("new", T0) == pytest.approx(-0.1)
    tr.update(T0, "KC", [("A", 400, 400.0, 400 * 0.2)])  # first game: league mean still 0
    assert tr.rating("A", T0) == pytest.approx((250 * -0.1 + 400 * 0.2) / 650)
    later = T0 + pd.Timedelta(days=365)  # one half-life: the evidence counts half
    assert tr.rating("A", later) == pytest.approx((250 * -0.1 + 200 * 0.2) / 450)


def test_baseline_is_dropback_weighted_current_ratings():
    tr = QBTracker(P)
    tr.update(T0, "KC", [("A", 30, 30.0, 6.0), ("B", 10, 10.0, -3.0)])
    w = {"A": 30, "B": 10}
    expected = sum(w[q] * tr.rating(q, T0) for q in w) / 40
    assert tr.baseline("KC", T0) == pytest.approx(expected)
    assert tr.baseline("NE", T0) == pytest.approx(-0.1)


def test_adjuster_oracle_uses_the_actual_starter():
    starters = pd.DataFrame([{"game_id": "g", "team": "KC", "exp_qb": "A", "alt_qb": None, "p_exp": 1.0, "actual_qb": "B"},
                             {"game_id": "g", "team": "NE", "exp_qb": "C", "alt_qb": None, "p_exp": 1.0, "actual_qb": "C"}])
    qbg = pd.DataFrame(columns=["game_id", "team", "passer_id", "dropbacks", "sw", "swx"])
    exp, ora = QBAdjuster(P, starters, qbg, 38.0), QBAdjuster(P, starters, qbg, 38.0, "oracle")
    for a in (exp, ora):
        a.tracker.update(T0, "KC", [("A", 400, 400.0, 80.0), ("B", 400, 400.0, -40.0)])
    assert exp.side("g", "KC", T0) > ora.side("g", "KC", T0)
