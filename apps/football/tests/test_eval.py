"""Evaluation harness: point-in-time guarantees, benchmark math and scoring, on synthetic games."""

import math

import numpy as np
import pandas as pd
import pytest

from marketscope_football.eval import design as d
from marketscope_football.eval.benchmarks import Elo538, NaiveHomeField, NflverseClose, RidgeRatings, ridge_ratings
from marketscope_football.eval.data import games_frame, no_vig_home
from marketscope_football.eval.metrics import fit_sigma, score_table, win_probability
from marketscope_football.eval.run_benchmarks import ridge_grid
from marketscope_football.eval.walkforward import HeldOutSeasonError, run_models, walk_forward

TEAMS = ["A", "B", "C", "D"]
STRENGTH = {"A": 6.0, "B": 2.0, "C": -2.0, "D": -6.0}


def synthetic(seasons=range(2020, 2025), weeks=6, noise=0.0, seed=1) -> pd.DataFrame:
    """Two games a week; margin = strength difference + 2 (home field) + noise."""
    rng = np.random.default_rng(seed)
    rows = []
    pairings = [(("A", "B"), ("C", "D")), (("A", "C"), ("B", "D")), (("A", "D"), ("B", "C"))]
    for s in seasons:
        start = pd.Timestamp(f"{s}-09-10", tz="UTC")
        for w in range(1, weeks + 1):
            for i, (h, a) in enumerate(pairings[(w - 1) % 3]):
                if w % 2 == 0:
                    h, a = a, h
                m = round(STRENGTH[h] - STRENGTH[a] + 2 + noise * rng.standard_normal())
                rows.append({"game_id": f"{s}_{w:02d}_{a}_{h}", "season": s, "game_type": "REG", "week": w,
                             "kickoff_utc": start + pd.Timedelta(days=7 * (w - 1), hours=i), "home": h, "away": a,
                             "neutral": False, "home_score": 20 + max(m, 0), "away_score": 20 + max(-m, 0),
                             "margin": float(m), "total": 40.0 + abs(m),
                             "home_win": 1.0 if m > 0 else 0.0 if m < 0 else 0.5,
                             "close_margin": STRENGTH[h] - STRENGTH[a] + 2, "close_total": 44.0, "close_p_home": np.nan})
    return pd.DataFrame(rows)


class PeekingModel:
    """A model that (wrongly) reads the result of the game it predicts."""

    name = "peeking"

    def predict(self, games):
        return pd.DataFrame({"margin": games["margin"], "p_home": 0.5}, index=games.index)

    def update(self, results):
        pass


def test_predict_never_sees_results_of_its_own_week():
    with pytest.raises(KeyError):
        walk_forward(synthetic(), PeekingModel(), [2023])


def test_predictions_do_not_change_when_later_games_are_removed():
    full = synthetic(noise=8.0)
    cut = full[(full["season"] < 2023) | ((full["season"] == 2023) & (full["week"] <= 3))]
    for make in (lambda: Elo538(), lambda: RidgeRatings("srs", "margin", 12.0, 84, 2.0), lambda: NaiveHomeField(12.0)):
        a = walk_forward(full, make(), [2023])
        b = walk_forward(cut, make(), [2023])
        a = a[a["week"] <= 3].reset_index(drop=True)
        pd.testing.assert_frame_equal(a, b.reset_index(drop=True))


def test_runner_refuses_the_test_season():
    with pytest.raises(HeldOutSeasonError):
        walk_forward(synthetic(seasons=range(2023, 2026)), Elo538(), [2024, d.TEST_SEASON])


def test_elo_update_matches_the_published_formula():
    g = synthetic(seasons=[2020], weeks=1).iloc[[0]]  # A (home) beats B by 6
    elo = Elo538()
    elo.update(g)
    diff = 65.0
    p = 1 / (1 + 10 ** (-diff / 400))
    shift = 20 * math.log(7) * 2.2 / (diff * 0.001 + 2.2) * (1 - p)
    assert elo.elo["A"] == pytest.approx(1500 + shift) and elo.elo["B"] == pytest.approx(1500 - shift)
    elo._season(2021)  # a third of the way back to 1505
    assert elo.elo["A"] == pytest.approx(1505 / 3 + (1500 + shift) * 2 / 3)


def test_ridge_recovers_ratings_and_home_field_without_noise():
    g = synthetic(seasons=[2020], weeks=6)
    r, hfa = ridge_ratings(g, "margin", g["kickoff_utc"].max(), half_life=1e9, lam=1e-6)
    assert hfa == pytest.approx(2.0, abs=1e-3)
    for t in TEAMS:
        assert r[t] == pytest.approx(STRENGTH[t], abs=1e-3)


def test_ridge_grid_agrees_with_the_walk_forward_model():
    g = synthetic(noise=8.0)
    grid = ridge_grid(g, "margin", (2023, 2024))
    point = grid[(grid["half_life"] == 84) & (grid["lambda"] == 2.0)]["margin_mae"].iloc[0]
    p = walk_forward(g, RidgeRatings("srs", "margin", 12.0, 84, 2.0), [2023, 2024])
    assert point == pytest.approx((p["margin"] - p["actual_margin"]).abs().mean())


def test_close_benchmark_and_naive_home_field():
    g = synthetic(noise=8.0)
    preds = run_models(g, {"naive": lambda: NaiveHomeField(12.0), d.REFERENCE: lambda: NflverseClose(12.0)}, [2024])
    close = preds[preds["model"] == d.REFERENCE]
    assert (close["margin"] == g.set_index("game_id").loc[close["game_id"], "close_margin"].to_numpy()).all()
    naive = preds[preds["model"] == "naive"]
    hist = g[(g["season"] >= 2021) & (g["season"] < 2024)]
    assert naive["margin"].iloc[0] == pytest.approx(hist["margin"].mean())


def test_no_vig_and_sigma():
    assert no_vig_home(-110, -110) == pytest.approx(0.5)
    assert no_vig_home(-200, 170) == pytest.approx((2 / 3) / (2 / 3 + 100 / 270))
    rng = np.random.default_rng(0)
    m = rng.uniform(-10, 10, 20000)
    y = (m + 13.0 * rng.standard_normal(m.size) > 0).astype(float)
    assert fit_sigma(m, y) == pytest.approx(13.0, rel=0.05)
    assert win_probability(np.array([0.0]), 13.0)[0] == pytest.approx(0.5)


def test_score_table_is_paired_and_requires_the_same_games():
    g = synthetic(noise=8.0)
    preds = run_models(g, {d.REFERENCE: lambda: NflverseClose(12.0), "elo": lambda: Elo538()}, [2024])
    t = score_table(preds, d.REFERENCE, resamples=200).set_index("model")
    assert t.loc[d.REFERENCE, "d_margin_mae"] == 0 and t.loc[d.REFERENCE, "d_margin_mae_hi"] == 0
    assert t.loc["elo", "margin_mae_lo"] <= t.loc["elo", "margin_mae"] <= t.loc["elo", "margin_mae_hi"]
    with pytest.raises(ValueError):
        score_table(preds.iloc[1:], d.REFERENCE, resamples=10)


def test_games_frame_unifies_franchises_and_orients_the_close():
    s = pd.DataFrame([{"game_id": "2019_01_SD_OAK", "season": 2019, "game_type": "REG", "week": 1,
                       "gameday": "2019-09-09", "gametime": "22:20", "home_team": "OAK", "away_team": "SD",
                       "location": "Home", "home_score": 24, "away_score": 24, "result": 0, "total": 48,
                       "spread_line": -3.0, "total_line": 47.0, "home_moneyline": 130, "away_moneyline": -150}])
    g = games_frame(s).iloc[0]
    assert (g["home"], g["away"], g["home_win"], g["margin"]) == ("LV", "LAC", 0.5, 0.0)
    assert g["close_margin"] == -3.0 and g["close_p_home"] < 0.5
