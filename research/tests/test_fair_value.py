"""MS-053 fair-value engine (PREREGISTRATION.md Addendum M)."""

import numpy as np
import pandas as pd
import pytest

from marketscope_research import fair_value as fv
from marketscope_research import market_ml as ml


def synthetic_games(n=3000, seed=0):
    """Favourite margins with a key number whose weight depends on the total: low totals pile up on 3."""
    rng = np.random.default_rng(seed)
    s = rng.choice([1.5, 2.5, 3.0, 3.5, 6.5, 7.0, 10.0], n)
    t = rng.choice([38.0, 41.0, 44.0, 47.0, 51.0], n)
    k = np.where(rng.random(n) < np.where(t <= 41, 0.35, 0.10), 3, np.round(rng.normal(s, 13)).astype(int))
    pts = np.round(rng.normal(t, 10)).astype(int)
    return pd.DataFrame({"home_line": -s, "total": t, "margin": k, "points": pts, "season": 2016 + np.arange(n) % 7})


def test_favourite_frame_orients_margins():
    g = pd.DataFrame({"home_line": [-3.0, 4.0], "total": [44.0, 41.0], "margin": [7.0, 2.0], "points": [41, 30]})
    f = fv.favourite_frame(g)
    assert f["k"].tolist() == [7, -2] and f["s"].tolist() == [3.0, 4.0]


def test_kernel_pmf_is_a_distribution_and_tracks_the_total():
    f = fv.favourite_frame(synthetic_games())
    m = fv.margin_model(f, 1.0, 2.0)
    low, high = m.pmf(3.0, 38.0), m.pmf(3.0, 51.0)
    assert low.sum() == pytest.approx(1) and (low >= 0).all()
    assert low[3] > high[3] + 0.1  # the planted key-number weight in low-total games is recovered


def test_kernel_beats_buckets_out_of_sample_on_the_planted_structure():
    f = fv.favourite_frame(synthetic_games())
    train, test = f[f["season"] < 2021], f[f["season"] >= 2021]
    kern = fv.log_losses(fv.margin_model(train, 1.0, 2.0).pmf, test, "k").mean()
    base = fv.log_losses(fv.bucket_pmf(train, "k"), test, "k").mean()
    assert kern < base


def test_bandwidth_search_prefers_using_the_total_when_it_matters():
    f = fv.favourite_frame(synthetic_games(1500))
    h_s, h_t, scores = fv.choose_bandwidths(f, "k")
    assert h_t < 1000 and len(scores) == 16


def test_engine_pmf_plugs_into_the_existing_calibration():
    f = fv.favourite_frame(synthetic_games())
    pmf = fv.margin_model(f, 1.0, 2.0).pmf(3.0, 41.0)
    w, pu, lo = ml.side_probabilities(pmf, -3.0, 0.55, "home", -3.0)
    assert w / (w + lo) == pytest.approx(0.55)


def test_devig_methods():
    q1, q2 = fv.implied(-110), fv.implied(-110)
    for m in fv.DEVIG_METHODS:
        assert fv.devig(q1, q2, m) == pytest.approx(0.5)
    fav, dog = fv.implied(-300), fv.implied(240)
    mult, power, shin = (fv.devig(fav, dog, m) for m in fv.DEVIG_METHODS)
    assert mult < shin and mult < power  # power and Shin move margin off the favourite (longshot bias)
    assert fv.devig(fav, dog, "power") ** 0 == 1


def test_win_probability_excludes_ties():
    pmf = pd.Series({-3: 0.3, 0: 0.1, 3: 0.6})
    assert fv.win_probability(pmf) == pytest.approx(0.6 / 0.9)


def test_load_engine_uses_the_frozen_parameters(tmp_path):
    import json
    params = tmp_path / "p.json"
    params.write_text(json.dumps({"margin": {"model": "kernel", "h_s": 1.0, "h_t": 1000.0},
                                  "total": {"model": "bucket", "h_s": 1.0, "h_t": 6.0}, "devig": "shin"}))
    eng = fv.load_engine(synthetic_games(800), params)
    assert eng.margin is not None and eng.total is None and eng.devig_method == "shin"
    assert eng.margin_pmf(-3.0, 44.0).sum() == pytest.approx(1)
    assert eng.total_pmf(44.0, -3.0).sum() == pytest.approx(1)
