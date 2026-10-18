"""Margin distribution and candidate factors."""

import numpy as np
import pandas as pd
import pytest

from marketscope_football.ratings.factors import candidate_features
from marketscope_football.ratings.margin_dist import K, MarginDistribution, fit_shape
from marketscope_football.ratings.selection_design import KEY_MAX


def flat(scale=13.0):
    return MarginDistribution(scale, [1.0] * (KEY_MAX + 1))


def test_flat_distribution_is_a_discretised_normal():
    d = flat()
    assert d.pmf(np.array([0.0]))[0].sum() == pytest.approx(1.0)
    assert d.p_home([0.0])[0] == pytest.approx(0.5)
    assert d.p_home([7.0])[0] > 0.65


def test_key_number_weight_moves_mass_to_three():
    w = [1.0] * (KEY_MAX + 1)
    w[3] = 3.0
    d, base = MarginDistribution(13.0, w), flat()
    i3 = int(np.where(K == 3)[0][0])
    assert d.pmf([3.0])[0, i3] > 2 * base.pmf([3.0])[0, i3]
    cover, push = d.p_cover([3.0], [3.0])
    assert push[0] > 0.07 and cover[0] < 0.5  # a 3-point favourite often pushes at -3 (≈ 3% without the weight)


def test_fit_recovers_scale_and_tie_suppression():
    rng = np.random.default_rng(0)
    m = rng.uniform(-10, 10, 4000)
    k = np.round(m + 13.0 * rng.standard_normal(len(m)))
    k[k == 0] = 1  # no ties
    d, meta = fit_shape(m, k)
    assert meta["converged"] and d.scale == pytest.approx(13.0, rel=0.05)
    assert d.weights[0] < 0.05


def test_candidate_features_home_minus_away():
    ctx = pd.DataFrame([
        {"game_id": "g", "team": "DEN", "rest_diff": 3, "bye_before": True, "travel_km": 0.0, "tz_shift_hours": 0.0,
         "body_clock_kickoff_hour": 14.0, "altitude_change_m": 0, "hc_tenure_games": 2, "off_playcaller_tenure_games": None},
        {"game_id": "g", "team": "MIA", "rest_diff": -3, "bye_before": False, "travel_km": 2700.0, "tz_shift_hours": -2.0,
         "body_clock_kickoff_hour": 16.0, "altitude_change_m": 1600, "hc_tenure_games": 40, "off_playcaller_tenure_games": 1}])
    games = pd.DataFrame([{"game_id": "g", "home": "DEN", "away": "MIA", "neutral": False, "division": False, "game_type": "WC"}])
    f = candidate_features(ctx, games).iloc[0]
    assert (f["rest_diff"], f["bye_diff"], f["tz_diff"]) == (3, 1, 2)
    assert f["travel_diff"] == pytest.approx(2.7) and f["altitude_diff"] == pytest.approx(1.6)
    assert (f["playoff_home"], f["division_home"], f["new_hc_diff"], f["new_oc_diff"]) == (1, 0, 1, -1)
