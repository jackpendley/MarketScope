"""MS-044 backtester and Wong-teaser legs (PREREGISTRATION.md Addendum E)."""

import pandas as pd
import pytest

from marketscope_research import backtest as bt
from marketscope_research import systems as sy


def test_grading_with_pushes():
    assert bt.grade_spread(3, -2.5) == "win" and bt.grade_spread(2, -2) == "push"
    assert bt.grade_spread(-8, 7.5) == "loss" and bt.grade_spread(-7, 7.5) == "win"
    assert bt.grade_total(45, 44.5, "over") == "win" and bt.grade_total(44, 44, "under") == "push"
    assert bt.grade_moneyline(0) == "push" and bt.grade_moneyline(-1) == "loss"


def test_prices_and_break_evens_match_the_preregistered_table():
    assert bt.profit(-125) == 0.8 and bt.profit(150) == 1.5
    assert bt.units("win", -110) == pytest.approx(100 / 110) and bt.units("push", -110) == 0
    expected = {-110: 0.724, -120: 0.739, -125: 0.745, -130: 0.752, -135: 0.758, -140: 0.764}
    for price, be in expected.items():
        assert bt.teaser_break_even(price) == pytest.approx(be, abs=0.0006)


def test_teaser_push_conventions():
    assert bt.teaser_units(("win", "win"), -125, "loses") == 0.8
    assert bt.teaser_units(("win", "push"), -125, "loses") == -1
    assert bt.teaser_units(("win", "push"), -125, "voids") == 0
    assert bt.teaser_units(("loss", "push"), -125, "voids") == -1


def legs_frame(results, weeks=None):
    n = len(results)
    weeks = weeks or [1] * n
    return pd.DataFrame({"season": 2020, "week": weeks,
                         "kickoff": pd.date_range("2020-09-13", periods=n, freq="h", tz="UTC"),
                         "team": [f"T{i}" for i in range(n)], "result": results})


def test_chronological_pairing_drops_the_odd_leg_and_stays_within_weeks():
    t = bt.pair_chronological(legs_frame(["win", "loss", "win", "win", "win"], weeks=[1, 1, 1, 2, 2]))
    assert list(zip(t["week"], t["leg1"], t["leg2"])) == [(1, "win", "loss"), (2, "win", "win")]


def test_all_pairs_counts_every_pair_in_a_week():
    assert len(bt.pair_all(legs_frame(["win"] * 4))) == 6


def test_planted_perfect_legs_pay_the_price_and_drawdown():
    t = bt.pair_chronological(legs_frame(["win"] * 6))
    assert bt.score_teasers(t, -120, "loses").tolist() == pytest.approx([100 / 120] * 3)
    assert bt.max_drawdown(pd.Series([1.0, -1, -1, 0.5, -1, 2])) == 2.5


def test_cluster_interval_is_reproducible():
    v = pd.Series([1.0, 0, 1, 1, 0, 1, 1, 1] * 10)
    c = pd.Series(range(80)) // 2
    a, b = bt.cluster_mean_ci(v, c, resamples=300), bt.cluster_mean_ci(v, c, resamples=300)
    assert a == b and a.low <= a.value <= a.high and a.value == 0.75


def games(*rows):
    cols = ["game_id", "season", "week", "kickoff", "home", "away", "home_line", "total", "margin"]
    return pd.DataFrame([dict(zip(cols, r)) for r in rows])


K = pd.Timestamp("2020-09-13T17:00Z")


def test_wong_ranges_and_teased_grading():
    g = games(("a", 2020, 1, K, "KC", "LV", -8.0, 47, 3),   # home fav -8 -> -2: wins by 3
              ("b", 2020, 1, K, "NE", "MIA", 2.5, 44, -8),   # home dog +2.5 -> +8.5: loses by 8, covers
              ("c", 2020, 1, K, "BUF", "NYJ", -2.0, 41, 1),  # away dog +2 -> +8: home wins by 1, covers
              ("d", 2020, 1, K, "DAL", "PHI", -3.0, 45, 0),  # not in range
              ("e", 2020, 1, K, "SF", "LAR", -7.5, 52, 1))   # fav -7.5 -> -1.5: wins by 1, loses
    legs = sy.wong_legs(g)
    assert list(legs["game_id"]) == ["a", "b", "c", "e"]
    assert list(legs["team"]) == ["KC", "NE", "NYJ", "SF"]
    assert list(legs["teased"]) == [-2.0, 8.5, 8.0, -1.5]
    assert list(legs["result"]) == ["win", "win", "win", "loss"]
    assert list(legs["role"]) == ["favourite", "underdog", "underdog", "favourite"]


def test_wong_push_on_an_integer_teased_line():
    legs = sy.wong_legs(games(("a", 2020, 1, K, "KC", "LV", -8.0, 47, 2)))
    assert legs["result"].tolist() == ["push"]


def test_variants_filter_totals_and_home_teams():
    g = games(("a", 2020, 1, K, "KC", "LV", -8.0, 47, 3),    # home leg, total 47
              ("c", 2020, 1, K, "BUF", "NYJ", -2.0, 41, 1),  # road leg, total 41
              ("e", 2020, 1, K, "SF", "LAR", -7.5, 52, 1))   # home leg, total 52
    assert list(sy.wong_legs(g, "V1")["game_id"]) == ["a", "c"]
    assert list(sy.wong_legs(g, "V2")["game_id"]) == ["c"]
