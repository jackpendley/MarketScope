"""MS-046 market ML (PREREGISTRATION.md Addendum G): value model, point-in-time features, walk-forward."""

import numpy as np
import pandas as pd
import pytest

from marketscope_research import market_ml as ml
from marketscope_research import sharp_market as sm
from tests.test_sharp_market import KICK, rows, ts

# Favourite margins with heavy mass on 3 and 7, like the NFL.
TABLE = pd.Series({-7: .05, -3: .08, 0: .02, 1: .06, 2: .06, 3: .15, 4: .07, 5: .05, 6: .06, 7: .12, 8: .05,
                   10: .08, 14: .08, 17: .07})
TABLE = TABLE / TABLE.sum()


def test_bucket_of_half_point_spreads():
    assert [ml.bucket_of(x) for x in (0, -2.5, 3, -4, 4.5, 7, -7.5, 14)] == [0, 0, 1, 1, 2, 2, 3, 3]


def test_calibration_reproduces_pinnacle_at_the_close():
    for p in (0.45, 0.5, 0.58):
        w, pu, l = ml.side_probabilities(TABLE, -3.0, p, "home", -3.0)
        assert w / (w + l) == pytest.approx(p, abs=1e-9)
        aw, apu, al = ml.side_probabilities(TABLE, -3.0, p, "away", 3.0)
        assert (aw, apu, al) == pytest.approx((l, pu, w))


def test_more_points_is_worth_more_and_three_is_worth_most():
    # Compare expected value, not win probability: at +3 some games push.
    def ev(line):
        w, _pu, lo = ml.side_probabilities(TABLE, -3.0, 0.5, "away", line)
        return ml.expected_value(w, lo, -110)

    assert ev(3.5) > ev(3.0) > ev(2.5)
    assert ev(3.5) - ev(2.5) > ev(5.5) - ev(4.5)  # crossing 3 is worth more than crossing 5


def test_expected_value_is_zero_at_a_fair_price():
    assert ml.expected_value(0.5, 0.5, 100) == pytest.approx(0)
    assert ml.expected_value(0.5238, 0.4762, -110) == pytest.approx(0, abs=1e-3)
    assert ml.no_vig_home(-110, -110) == pytest.approx(0.5)


def books_for(*groups):
    df = pd.DataFrame([r for g in groups for r in g])
    return sm.timelines(df)["g"]


def base_books(extra_pin=()):
    return books_for(
        rows("g", "pinnacle", (ts("10:00", 16), -3, -110, -110, 5000), (ts("10:00", 17), -3.5, -105, -115, 7500),
             *extra_pin),
        rows("g", "draftkings", (ts("09:00", 16), -3, -110, -110)),
        rows("g", "circa", (ts("09:00", 16), -3.5, -110, -110)))


def test_features_never_use_rows_after_the_decision_time():
    empty = pd.DataFrame(columns=["t", "toward"])
    before = ml.game_features(base_books(), KICK, empty)
    # A Pinnacle move 30 minutes before kickoff must not change any horizon >= 1 h.
    after = ml.game_features(base_books(extra_pin=[(ts("16:30"), -6.5, -110, -110, 9000)]), KICK, empty)
    strip = lambda rs: [{k: v for k, v in r.items() if k != "_d"} for r in rs]  # noqa: E731
    assert strip(before) == strip(after)


def test_feature_values_at_a_horizon():
    f = {r["h"]: r for r in ml.game_features(base_books(), KICK, pd.DataFrame(columns=["t", "toward"]))}
    r24 = f[24]  # d = Oct 17 17:00: Pinnacle -3.5 (moved at Oct 17 10:00), DK still -3, Circa -3.5
    assert r24["pin_line"] == -3.5 and r24["retail_mean"] == 0.5 and r24["circa_diff"] == 0
    assert r24["changes_24h"] == 1 and r24["net_dir_6h"] == 0  # the move was 7 h before d
    assert r24["limit_change_6h"] == pytest.approx(np.log(7500) - np.log(7500))
    assert r24["imbalance"] == 10  # -105 vs -115 on the cents scale


def test_build_units_targets():
    games = pd.DataFrame({"event_id": ["g"], "kickoff": [KICK], "week": [3]})
    tl = {"g": base_books(extra_pin=[(ts("16:30"), -6.5, -110, -110, 9000)])}
    g1, g2 = ml.build_units(tl, games, [TABLE] * 4)
    assert set(g1["y"]) == {-1}  # Pinnacle's home line fell further by the close: toward home
    dk = g2[(g2["book"] == "draftkings") & (g2["h"] == 24)].set_index("side")
    assert dk.loc["home", "side_diff"] == 0.5 and dk.loc["away", "side_diff"] == -0.5
    assert dk.loc["home", "at_pin_previous"] == 1.0
    assert dk.loc["home", "value"] > dk.loc["away", "value"]  # home -3 vs a -6.5 close


def planted_g1(weeks, flip_week=None, n=60, seed=0):
    rng = np.random.default_rng(seed)
    out = []
    for w in weeks:
        for i in range(n):
            x = float(rng.choice([-1.0, 1.0]))
            y = int(x) if w != flip_week else int(-x)
            out.append({"event_id": f"{w}-{i}", "week": w, **{c: 0.0 for c in ml.G1_FEATURES},
                        "h": 24, "retail_mean": x, "y": y})
    return pd.DataFrame(out)


def test_g1_walk_forward_beats_the_baseline_on_a_planted_signal():
    res = ml.walk_forward_g1(planted_g1(range(1, 7)))
    assert set(res["week"]) == {3, 4, 5, 6}
    assert res["ridge"].mean() < res["baseline"].mean() - 0.3


def test_g1_walk_forward_never_trains_on_the_week_it_predicts():
    res = ml.walk_forward_g1(planted_g1(range(1, 7), flip_week=5))
    wk5 = res[res["week"] == 5]
    assert wk5["ridge"].mean() > wk5["baseline"].mean()  # a leak would have learned the flip


def test_g2_walk_forward_recovers_value_from_the_line_difference():
    rng = np.random.default_rng(1)
    out = []
    for w in range(1, 7):
        for i in range(80):
            diff = float(rng.choice([-1.0, -0.5, 0.0, 0.5, 1.0]))
            out.append({"event_id": f"{w}-{i}", "week": w, "book": "draftkings", "side": "home",
                        **{c: 0.0 for c in ml.G1_FEATURES + ml.G2_EXTRA}, "side_diff": diff, "price": -110,
                        "value": 0.1 * diff - 0.02})
    res = ml.walk_forward_g2(pd.DataFrame(out))
    assert np.corrcoef(res["ridge"], res["value"])[0, 1] > 0.99


def test_price_aware_value_of_a_stale_number():
    tl = {"g": base_books(extra_pin=[(ts("16:30"), -3.5, -110, -110, 9000)])}
    ev = pd.DataFrame({"event_id": ["g", "g"], "side": ["home", "home"], "line": [-3.0, -3.0],
                       "price": [-110, -140]})
    v = ml.price_aware_values(ev, tl, pd.Series({"g": KICK}), [TABLE] * 4)
    assert v.iloc[0] > v.iloc[1]  # the same number is worth less at a worse price
    assert v.iloc[0] > ml.expected_value(0.5, 0.5, -110)  # -3 against a -3.5 close beats a coin flip
