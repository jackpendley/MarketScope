"""MS-035 study functions on synthetic data with known answers (no database)."""

import numpy as np
import pandas as pd
import pytest

from marketscope_research import football_studies as fs


def test_ols_recovers_coefficients_and_slope_interval_covers_truth():
    rng = np.random.default_rng(1)
    x = rng.normal(size=400)
    y = 2.0 + 0.5 * x + rng.normal(scale=0.5, size=400)
    beta, se = fs.ols(y, x)
    assert beta == pytest.approx([2.0, 0.5], abs=0.1)
    est = fs.slope(y, x, resamples=500)
    assert est.low < 0.5 < est.high and est.excludes_zero() == "above 0"
    null = fs.slope(rng.normal(size=400), x, resamples=500)
    assert null.excludes_zero() == "includes 0"


def test_consensus_at_leads_uses_the_nearest_snapshot_within_tolerance():
    kick = pd.Timestamp("2026-09-13 17:00", tz="UTC")
    times = [kick - pd.Timedelta(days=6, hours=5), kick - pd.Timedelta(days=3, hours=20),
             kick - pd.Timedelta(hours=26), kick - pd.Timedelta(hours=2)]
    cons = pd.DataFrame({"event_id": "e", "observed_at": times, "consensus": [-3.0, -3.5, -4.0, -4.5], "books": 4})
    out = fs.consensus_at_leads(cons, pd.Series({"e": kick})).iloc[0]
    assert out["6 days"] == -3.0
    assert np.isnan(out["3 days"])  # 20 h off: outside ±12 h
    assert out["1 day"] == -4.0
    assert out["close"] == -4.5
    late = fs.consensus_at_leads(cons.iloc[:3], pd.Series({"e": kick})).iloc[0]
    assert np.isnan(late["close"])  # last snapshot 26 h before kickoff is not a close


def test_r1_pairs_errors_by_game():
    df = pd.DataFrame({"event_id": [f"g{i}" for i in range(60)], "margin": [3.0] * 60,
                       "6 days": [-1.0] * 60, "3 days": [-2.0] * 60, "1 day": [-3.0] * 60, "close": [-3.0] * 60,
                       "nflverse_close": [-2.5] * 60})
    r = fs.r1_accuracy(df)
    assert r["gate"] and r["mae"]["6 days"] == 2.0 and r["mae"]["close"] == 0.0
    assert r["diff_vs_close"]["6 days"].value == 2.0
    assert r["mae"]["nflverse close"] == 0.5


def test_rating_games_use_the_previous_week_snapshot():
    games = pd.DataFrame({"game_id": ["a", "b"], "season": 2020, "week": [1, 6], "home": "KC", "away": "LV",
                          "neutral": [False, True], "margin": [7.0, -3.0], "close_margin": [3.0, 1.0]})
    snaps = pd.DataFrame({"season": 2020, "week": [0, 0, 5, 5], "team": ["KC", "LV", "KC", "LV"],
                          "adj_em": [4.0, -1.0, 6.0, 0.0], "luck": [0.0, 0.0, 1.5, -0.5]})
    g = fs.rating_games(games, snaps).set_index("game_id")
    assert g.loc["a", "rating_margin"] == pytest.approx(5.0 + fs.HOME_ADVANTAGE)
    assert g.loc["b", "rating_margin"] == 6.0  # neutral site
    assert g.loc["b", "luck_diff"] == 2.0
    assert g.loc["a", "ats"] == 4.0 and g.loc["b", "gap"] == 5.0


def test_r5_detects_a_planted_market_bias_and_persistence_null():
    rng = np.random.default_rng(3)
    n = 2000
    luck = rng.normal(scale=1.5, size=n)
    g = pd.DataFrame({"week": 8, "luck_diff": luck, "ats": -1.0 * luck + rng.normal(scale=13, size=n),
                      "rating_resid": rng.normal(scale=13, size=n)})
    r = fs.r5_luck(g)
    assert r["market"].excludes_zero() == "below 0"
    assert r["ratings"].excludes_zero() == "includes 0"
    snaps = pd.DataFrame({"season": 2020, "week": np.repeat([9, 17], 32), "team": [f"T{i}" for i in range(32)] * 2,
                          "luck": np.concatenate([rng.normal(size=32), np.zeros(32)])})
    snaps.loc[snaps.week == 17, "luck"] = snaps.loc[snaps.week == 9, "luck"].to_numpy() + rng.normal(size=32)
    p = fs.r5_persistence(snaps, {2020: 17})
    assert p["team_seasons"] == 32 and p["slope"].excludes_zero() == "includes 0"


def test_r3_buckets_and_gate():
    rng = np.random.default_rng(4)
    n = 300
    wind = rng.uniform(0, 25, n)
    df = pd.DataFrame({"wind_mph": wind, "precip_in": 0.0, "season": rng.choice([2024, 2025], n),
                       "close_total": 45 - 0.2 * wind, "total": 45 - 0.2 * wind + rng.normal(scale=10, size=n)})
    r = fs.r3_pricing(df)
    assert r["gate"] and r["games"] == n
    assert [b["wind"] for b in r["buckets"]] == ["< 10", "10-15", ">= 15"]
    assert r["close_per_mph"][0] == pytest.approx(-0.2, abs=1e-6)
    assert fs.r3_movement(pd.DataFrame({"crossed": [True] * 3 + [False] * 50, "move": 0.0}))["gate"] is False


def test_r7_units_callers_and_qbs():
    tg = pd.DataFrame({"season": 2020, "team": ["A", "B", "A", "B"], "opponent": ["B", "A", "B", "A"],
                       "drives": [10, 10, 10, 10], "drive_points": [30, 10, 20, 20]})
    u = fs.season_units(tg).set_index("team")
    assert u.loc["A", "off"] == pytest.approx(0.5) and u.loc["A", "def"] == pytest.approx(-0.5)  # league 2.0 ppd
    staff = pd.DataFrame({"season": 2020, "team": "A", "coach_id": ["oc1", "hc", "dc"], "from_week": [1, 9, 1],
                          "to_week": [8, 21, 21], "offense_playcaller": [True, True, False],
                          "defense_playcaller": [False, False, True]})
    assert fs.caller_at(staff, "offense", {2020: 17})[(2020, "A")] == "hc"
    assert fs.caller_at(staff, "offense", {2020: 1})[(2020, "A")] == "oc1"
    assert fs.main_caller(staff, "offense")[(2020, "A")] == "hc"  # 9 regular-season weeks vs 8
    starts = pd.DataFrame({"season": 2020, "team": "A", "week": [1, 2, 3, 4], "qb_id": ["q1", "q1", "q2", "q2"]})
    assert fs.main_qb(starts)[(2020, "A")] == "q2"  # tie on starts: the later starter


def test_r7_detects_planted_continuity_interaction():
    rng = np.random.default_rng(5)
    n = 600
    x = rng.normal(scale=0.3, size=n)
    same_c, same_q = rng.uniform(size=n) < 0.7, rng.uniform(size=n) < 0.7
    y = (0.2 + 0.4 * same_c + 0.2 * same_q) * x + rng.normal(scale=0.15, size=n)
    p = pd.DataFrame({"season": 2020, "team": "T", "x_off": x, "y_off": y, "same_off": same_c, "same_qb": same_q,
                      "x_def": x, "y_def": 0.3 * x + np.random.default_rng(6).normal(scale=0.15, size=n), "same_def": same_c})
    r = fs.r7_carryover(p, resamples=500)
    assert r["gate"] and r["interaction"].excludes_zero() == "above 0"
    assert r["interaction"].low < 0.4 < r["interaction"].high
    assert r["defense"]["interaction"].excludes_zero() == "includes 0"
    assert len(r["groups"]) == 4


def test_scheme_movers_follow_the_coach_to_a_new_team():
    callers = pd.Series({(2020, "A"): "c1", (2021, "B"): "c1", (2020, "B"): "c2", (2021, "A"): "c3"})
    callers.index = callers.index.set_names(["season", "team"])
    traits = pd.DataFrame({"season": [2020, 2020, 2021, 2021], "team": ["A", "B", "A", "B"], "proe": [5.0, -3.0, 0.0, 4.0]})
    m = fs.scheme_movers(traits, callers)
    assert len(m) == 1 and m.iloc[0]["to"] == "B"
    assert (m.iloc[0]["proe_caller"], m.iloc[0]["proe_prior"], m.iloc[0]["proe_new"]) == (5.0, -3.0, 4.0)


def test_injury_events_need_a_recent_starter_who_played_last_game():
    snaps = pd.DataFrame({"season": 2026, "team": "KC", "gsis_id": ["a", "a", "a", "b", "b", "c"],
                          "week": [1, 2, 3, 1, 2, 3], "offense_pct": [0.9, 0.8, 0.95, 0.9, 0.9, 0.2],
                          "defense_pct": 0.0})
    final = pd.DataFrame({"season": 2026, "week": 4, "team": "KC", "gsis_id": ["a", "b", "c", "a"],
                          "position": ["QB", "WR", "WR", "QB"], "report_status": ["Out", "Out", "Out", "Questionable"]})
    ev = fs.injury_events(final, snaps)
    # a: starter who played week 3 -> event; b: missed week 3 (already out) -> not news; c: not a starter.
    assert ev["gsis_id"].tolist() == ["a"] and bool(ev["qb"].iloc[0])


def test_r2w_slope_recovers_a_planted_move_per_event():
    rng = np.random.default_rng(7)
    n = 300
    games = pd.DataFrame({"season": 2026, "week": rng.integers(2, 7, n), "home": [f"H{i}" for i in range(n)],
                          "away": [f"A{i}" for i in range(n)]})
    away_n = rng.poisson(0.6, n)
    events = pd.DataFrame([{"season": 2026, "week": w, "team": a, "gsis_id": f"{a}{k}", "qb": False}
                           for w, a, c in zip(games["week"], games["away"], away_n) for k in range(c)])
    games["move"] = 0.8 * away_n + rng.normal(scale=0.5, size=n)
    r = fs.r2w(games, events, resamples=400)
    assert r["gate"] and r["slope"].low < 0.8 < r["slope"].high and not r["qb_gate"]
