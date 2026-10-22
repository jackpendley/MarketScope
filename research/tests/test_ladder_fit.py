"""MS-059 engine v3 line conversion (PREREGISTRATION.md Addendum T)."""

import numpy as np
import pandas as pd
import pytest

from marketscope_research import fair_value as fv
from marketscope_research import ladder_fit as lf
from marketscope_research import market_ml as ml
from marketscope_research import openers_totals as ot

from test_cross_market import ENGINE, KICK, ladder, rows


def pmf():
    return ENGINE.margin_pmf(-3.0, 44.0)


def no_push(conv, t):
    w, pu = conv(t)
    return w / (1 - pu)


@pytest.mark.parametrize("main", [-3.0, -6.5, 2.5])
@pytest.mark.parametrize("line", [-10.5, -3.5, -3.0, 0.5, 7.5])
def test_v2_matches_the_registered_spread_calibration(main, line):
    fav = ENGINE.margin_pmf(main, 44.0)
    conv = fv.calibrate(fv.home_margin_pmf(fav, main), -main, 0.53, "v2")
    w, pu, _lo = ml.side_probabilities(fav, main, 0.53, "home", line)
    assert conv(-line) == pytest.approx((w, pu))


@pytest.mark.parametrize("line", [38.5, 44.0, 51.5])
def test_v2_matches_the_registered_total_calibration(line):
    tp = ENGINE.total_pmf(44.5, -3.0)
    conv = fv.calibrate(tp, 44.5, 0.48, "v2")
    w, pu, _lo = ot.total_side_probabilities(tp, 44.5, 0.48, "over", line)
    assert conv(line) == pytest.approx((w, pu))


@pytest.mark.parametrize("method", fv.CONVERSIONS)
@pytest.mark.parametrize("t_main", [3.0, 3.5])
def test_every_method_reproduces_the_main_line(method, t_main):
    conv = fv.calibrate(pmf(), t_main, 0.58, method, beta=1.2)
    assert no_push(conv, t_main) == pytest.approx(0.58, abs=1e-6)


def test_home_margin_pmf_flips_an_away_favourite():
    fav = ENGINE.margin_pmf(4.0, 44.0)
    home = fv.home_margin_pmf(fav, 4.0)
    assert home.sum() == pytest.approx(1)
    assert home[home.index < 0].sum() == pytest.approx(fav[fav.index > 0].sum())


def test_scale_at_one_is_the_logit_shift():
    a = fv.calibrate(pmf(), 3.0, 0.6, "logit")
    b = fv.calibrate(pmf(), 3.0, 0.6, "scale", beta=1.0)
    assert a(10.5) == pytest.approx(b(10.5))


def test_location_shift_at_an_integer_moves_the_pmf():
    p = pmf()
    w_orig, _ = fv._tail(p.index.to_numpy(float), p.to_numpy(float), 3.5)
    target = fv._tail(p.index.to_numpy(float), p.to_numpy(float), 2.5)[0]  # pmf moved one point right
    conv = fv.calibrate(p, 3.5, target, "location")
    assert conv(3.5)[0] == pytest.approx(target, abs=1e-6)
    assert conv(6.5)[0] > fv._tail(p.index.to_numpy(float), p.to_numpy(float), 6.5)[0]
    assert w_orig < target


def test_logit_methods_stay_inside_the_unit_interval_where_v2_clips():
    # a main line far from the model's view: the additive shift runs out of room in the tail
    v2 = fv.calibrate(pmf(), 3.5, 0.95, "v2")
    lg = fv.calibrate(pmf(), 3.5, 0.95, "logit")
    assert v2(-20.5)[0] == pytest.approx(1.0)
    assert 0.95 < lg(-20.5)[0] < 1.0


def test_kl_is_zero_only_when_equal():
    p = np.array([0.3, 0.5, 0.8])
    assert lf.kl(p, p) == pytest.approx(np.zeros(3))
    assert (lf.kl(p, p + 0.05) > 0).all()


def sharp_ladder():
    return ladder(
        rows("pinnacle", "spreads", -3.0, 1.95, 1.95),
        rows("pinnacle", "spreads", -6.5, 2.75, 1.47),
        rows("pinnacle", "spreads", -7.0, 2.90, 1.43),     # integer: not a target
        rows("pinnacle", "spreads", -14.5, 6.00, 1.13),    # more than 10 points away
        rows("pinnacle", "spreads", 0.5, 1.50, 2.70),
        rows("pinnacle", "totals", 44.5, 1.95, 1.95),
        rows("pinnacle", "totals", 41.5, 1.60, 2.40),
        rows("pinnacle", "moneyline", 0.0, 1.65, 2.35),
        rows("draftkings", "spreads", -3.5, 1.95, 1.95),   # not a sharp book
    )


def test_fixture_observations_pick_half_point_alternates_and_moneylines():
    obs = lf.fixture_observations(sharp_ladder(), KICK)
    assert set(obs["book"]) == {"pinnacle"} and len(obs) == len(lf.HORIZONS) * 4
    one = obs[obs["h"] == 24]
    assert sorted(one.loc[one["market"] == "spreads", "line"]) == [-6.5, 0.5]
    assert one.loc[one["market"] == "totals", "line"].tolist() == [41.5]
    m = one[one["market"] == "moneyline"].iloc[0]
    assert m["main"] == -3.0 and m["p_star"] > 0.5
    assert one.loc[(one["market"] == "spreads") & (one["line"] == -6.5), "key"].item()
    assert one["p_main"].tolist() == pytest.approx([0.5] * 4)


def test_selection_recovers_the_method_that_made_the_ladder():
    obs = lf.fixture_observations(sharp_ladder(), KICK)
    planted = obs.assign(p_star=lf.predict(obs, ENGINE, "location"))
    chosen, losses = lf.select(planted, ENGINE, beta=1.0)
    assert chosen == "location" and losses["location"] == pytest.approx(0.0, abs=1e-9)


def test_choose_beta_finds_a_planted_scale():
    obs = lf.fixture_observations(sharp_ladder(), KICK)
    planted = obs.assign(p_star=lf.predict(obs, ENGINE, "scale", 1.2))
    beta, losses = lf.choose_beta(planted, ENGINE)
    assert beta == 1.2 and len(losses) == len(fv.BETAS)


V3 = {"spreads": {"method": "scale", "beta": 0.98}, "totals": {"method": "scale", "beta": 1.06},
      "moneyline": {"method": "v2", "beta": 1.0}}


def v3_engine():
    import dataclasses
    return dataclasses.replace(ENGINE, conversion=V3)


@pytest.mark.parametrize("side,line", [("home", -6.5), ("away", 6.5), ("away", 2.5), ("home", -3.0)])
def test_engine_v2_path_is_the_registered_function(side, line):
    assert ENGINE.spread_side(-3.0, 44.0, 0.52, side, line) == \
        ml.side_probabilities(ENGINE.margin_pmf(-3.0, 44.0), -3.0, 0.52, side, line)


@pytest.mark.parametrize("home_spread", [-3.0, 4.5])
def test_engine_v3_spreads_follow_the_calibrated_curve(home_spread):
    e = v3_engine()
    conv = fv.calibrate(fv.home_margin_pmf(e.margin_pmf(home_spread, 44.0), home_spread), -home_spread, 0.52,
                        "scale", 0.98)
    w, pu, lo = e.spread_side(home_spread, 44.0, 0.52, "home", -9.5)
    assert (w, pu) == pytest.approx(conv(9.5))
    aw, apu, alo = e.spread_side(home_spread, 44.0, 0.52, "away", 9.5)
    assert (aw, alo) == pytest.approx((lo, w))
    hw, hpu, hlo = e.spread_side(home_spread, 44.0, 0.52, "home", home_spread)
    assert hw / (hw + hlo) == pytest.approx(0.52)


def test_engine_v3_totals_and_unadopted_moneyline():
    e = v3_engine()
    w, pu, lo = e.total_side(44.5, -3.0, 0.47, "under", 50.5)
    assert (lo, pu) == pytest.approx(fv.calibrate(e.total_pmf(44.5, -3.0), 44.5, 0.47, "scale", 1.06)(50.5))
    assert e.moneyline_home(-3.0, 44.0, 0.55) == ENGINE.moneyline_home(-3.0, 44.0, 0.55)
