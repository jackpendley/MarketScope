"""Addendum V: evaluation boundaries, the MS-057 baseline, the confirmation family."""

import numpy as np
import pandas as pd
import pytest

from marketscope_research import evaluation as ev
from marketscope_research import model_open as mo


def planted(n=400, seed=0):
    """Noisy early line L = T + e, close = T. The 'model' knows nothing about T; the baseline knows T roughly."""
    rng = np.random.default_rng(seed)
    t = rng.normal(0, 6, n)
    early = t + rng.normal(0, 1.0, n)
    model = rng.normal(0, 6, n)            # useless
    baseline = t + rng.normal(0, 0.5, n)   # the market's own earlier information
    return pd.DataFrame({"event_id": [f"g{i}" for i in range(n)], "week": np.arange(n) % 12, "pin_d": early,
                         "model_line": model, "x": model - early, "xb": baseline - early, "y": t - early})


def test_a_useless_model_gets_a_positive_slope_from_the_shared_line():
    f = planted()
    slope = ev.ols_ci(f, "y", ["x"])[0]
    assert slope.low > 0  # the trap Addendum V describes
    perm = mo.permutation_slopes(f, n=200)
    assert np.nanmean(perm) > 0 and np.nanquantile(perm, 0.025) > 0


def test_a_noisy_baseline_leaves_a_small_bias_that_the_permutation_null_catches():
    f = planted()
    model, base = ev.ols_ci(f, "y", ["x", "xb"])
    assert base.low > 0.5 and abs(model.value) < 0.02  # almost all of the slope was the shared line
    null = mo.joint_permutation(f, n=300)
    assert model.value <= np.quantile(null, 0.975)  # Addendum W: not credited


def test_an_informative_model_beats_the_permutation_null():
    f = planted()
    rng = np.random.default_rng(5)
    t = f["y"] + f["pin_d"]
    informed = t + rng.normal(0, 2, len(f))  # knows T better than the early line's error suggests
    g = f.assign(model_line=informed, x=informed - f["pin_d"])
    model, _ = ev.ols_ci(g, "y", ["x", "xb"])
    assert model.low > 0 and model.value > np.quantile(mo.joint_permutation(g, n=300), 0.975)


def test_mean_bootstrap_clusters_and_p_value():
    df = pd.DataFrame({"event_id": ["a", "a", "b", "c"], "week": [1, 1, 1, 2], "v": [1.0, 3.0, 2.0, 2.0]})
    by_game = ev.mean_bootstrap(df, "v")
    by_week = ev.mean_bootstrap(df, "v", cluster="week")
    assert by_game.value == by_week.value == 2.0
    assert by_game.clusters == 3 and by_week.clusters == 2 and by_game.p < 0.05
    assert ev.boot_p(np.array([-1.0, 1.0, 2.0, 3.0])) == 0.5


def test_ols_ci_ignores_row_order():
    f = planted(120)
    a = ev.ols_ci(f, "y", ["x"], resamples=300)[0]
    b = ev.ols_ci(f.sample(frac=1, random_state=3), "y", ["x"], resamples=300)[0]
    assert (a.low, a.high) == pytest.approx((b.low, b.high))


def test_holm_step_down():
    got = ev.holm({"a": 0.001, "b": 0.02, "c": 0.03, "d": 0.5})
    assert got == {"a": True, "b": False, "c": False, "d": False}  # 0.02 > 0.05 / 3 stops the procedure
    assert ev.holm({"a": 0.01, "b": 0.02}) == {"a": True, "b": True}


def test_frozen_first_keeps_decisions_after_the_freeze():
    df = pd.DataFrame({"decision_at": pd.to_datetime(["2026-10-21T20:00Z", "2026-10-22T01:00Z"], utc=True)})
    assert len(ev.frozen_first(df, "decision_at", "O")) == 1


def test_market_ratings_recover_planted_teams_point_in_time():
    rng = np.random.default_rng(1)
    teams = [f"T{i}" for i in range(8)]
    true = dict(zip(teams, rng.normal(0, 5, 8)))
    rows, k0 = [], pd.Timestamp("2026-09-10T17:00Z")
    for w in range(16):
        order = rng.permutation(teams)
        for h, a in zip(order[::2], order[1::2]):
            rows.append({"home": h, "away": a, "neutral": False, "kickoff": k0 + pd.Timedelta(days=7 * w),
                         "close": -(true[h] - true[a] + 1.6)})
    closes = pd.DataFrame(rows)
    ratings, hfa = mo.market_ratings(closes, k0 + pd.Timedelta(days=60))
    est = np.array([ratings[t] for t in teams])
    assert np.corrcoef(est, [true[t] for t in teams])[0, 1] > 0.95
    assert hfa == pytest.approx(1.6, abs=0.5)
    assert mo.market_ratings(closes, k0) is None  # nothing final before the first kickoff
