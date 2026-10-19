"""MS-036 football features: known values and the point-in-time (leakage) contract."""

import numpy as np
import pandas as pd
import pytest

from marketscope_research.ml import football_features as ff
from marketscope_research.ml.design_football import HOME_ADVANTAGE

K0 = pd.Timestamp("2026-09-13 17:00", tz="UTC")  # week 1 Sunday


def world():
    weeks = range(1, 6)
    schedule = pd.DataFrame([{"season": 2026, "week": w, "game_id": f"g{w}", "kickoff": K0 + pd.Timedelta(days=7 * (w - 1)),
                              "home": "KC" if w % 2 else "DEN", "away": "DEN" if w % 2 else "KC"} for w in weeks])
    ratings = pd.DataFrame([{"season": 2026, "week": w, "team": t, "adj_em": (w if t == "KC" else -w) * 1.0}
                            for w in range(0, 6) for t in ("KC", "DEN")])
    snaps = []
    for w in range(1, 5):
        snaps += [{"game_id": f"g{w}", "team": "KC", "gsis_id": "qb", "share": 1.0 if w < 4 else 0.1},
                  {"game_id": f"g{w}", "team": "KC", "gsis_id": "wr", "share": 0.8},
                  {"game_id": f"g{w}", "team": "DEN", "gsis_id": "lb", "share": 0.9}]
    weather = pd.DataFrame({"game_id": "g5", "lead_days": [0, 1, 3, 7], "wind_mph": [30.0, 20.0, 12.0, 5.0]})
    context = pd.DataFrame({"game_id": "g5", "rest_diff": [3], "away_travel_km": [900.0], "short_week_any": [0]})
    games = schedule[schedule["game_id"] == "g5"].assign(event_id="e5", neutral=False)
    return games, schedule, ratings, pd.DataFrame(snaps), weather, context


def feats(t, *w):
    games, schedule, ratings, snaps, weather, context = w
    rows = pd.DataFrame({"event_id": ["e5"], "t": [t], "consensus": [-3.0]})
    return ff.build_football_features(rows, games, schedule, ratings, snaps, weather, context).iloc[0]


def test_known_values_two_days_before_week5():
    w = world()
    kick5 = w[0]["kickoff"].iloc[0]
    f = feats(kick5 - pd.Timedelta(days=2), *w)
    # Week-4 snapshot is usable (last kickoff of week 4 + 16 h < t): KC 4, DEN -4, KC home in week 5.
    assert f["rating_gap"] == pytest.approx(8 + HOME_ADVANTAGE - 3.0)
    assert f["starters_hurt_home"] == 1 and f["starters_hurt_away"] == 0 and f["starters_hurt_net"] == -1
    assert (f["wind_mph"], f["abs_wind_change"], f["outdoor"]) == (12.0, 7.0, 1)  # 3-day lead; lead 1 not yet usable
    assert (f["rest_diff"], f["away_travel_km"]) == (3, 900.0)


def test_nothing_unusable_at_t_can_change_a_feature():
    w = world()
    games, schedule, ratings, snaps, weather, context = w
    kick5 = games["kickoff"].iloc[0]
    t = kick5 - pd.Timedelta(days=6, hours=12)  # before week 4's snapshot and its snap counts are usable
    base = feats(t, *w)
    avail = ff.rating_available_at(schedule)
    late = [k for (s, k), at in avail.items() if at > t]
    r2 = ratings.copy()
    r2.loc[r2["week"].isin(late), "adj_em"] += 50  # snapshots not yet built at t
    s2 = snaps.copy()
    s2.loc[s2["game_id"] == "g4", "share"] = 0.0  # week-4 snap counts not yet usable at t
    w2 = weather.copy()
    w2.loc[w2["lead_days"].isin([0, 1, 3]), "wind_mph"] = 99.0  # forecasts issued after t, and lead 0
    after = feats(t, games, schedule, r2, s2, w2, context)
    for col in ff.COLUMNS:
        a, b = base[col], after[col]
        assert (pd.isna(a) and pd.isna(b)) or a == pytest.approx(b), col
    # The perturbations are real: at a later t they do change the features.
    later = feats(kick5 - pd.Timedelta(hours=30), games, schedule, r2, s2, w2, context)
    assert later["wind_mph"] == 99.0 and later["rating_gap"] != base["rating_gap"]


def test_indoor_games_and_early_season_injuries():
    w = world()
    games, schedule, ratings, snaps, weather, context = w
    f = feats(games["kickoff"].iloc[0] - pd.Timedelta(days=2), games, schedule, ratings, snaps, weather.iloc[0:0], context)
    assert (f["wind_mph"], f["outdoor"]) == (0.0, 0)
    assert np.isnan(ff.starters_hurt("KC", 2026, K0 + pd.Timedelta(days=3), schedule, snaps))  # one game played


def test_experiment_detects_a_planted_direction_signal_in_the_rating_gap():
    from marketscope_research.ml import experiment_football as ef
    from marketscope_research.ml.design import DIRECTION_FEATURES, MOVE_FEATURES
    from marketscope_research.ml.football_features import COLUMNS

    rng = np.random.default_rng(11)
    rows = []
    for g in range(160):
        split = ["train"] * 3 + ["validation"] + ["test"]
        week = 1 + g % 5
        for _ in range(10):
            rows.append({"event_id": f"e{g}", "week": week, "split": split[week - 1]})
    df = pd.DataFrame(rows)
    for c in set(MOVE_FEATURES + DIRECTION_FEATURES + COLUMNS + ["outlier_dev", "pinnacle_dev"]):
        df[c] = rng.normal(size=len(df))
    df["dow_et"] = rng.integers(0, 7, len(df))
    df["moved"] = 1.0
    p_home = 1 / (1 + np.exp(-2.0 * df["rating_gap"]))
    df["direction"] = np.where(rng.uniform(size=len(df)) < p_home, "home", "away")
    r = ef.run_direction_football(df)
    row = r.test_scores.set_index("model").loc["logistic + football"]
    assert r.gate and row["d_brier_hi"] < 0 and row["d_ll_hi"] < 0
    assert r.coefficients.index[0] == "rating_gap"
