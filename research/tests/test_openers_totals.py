"""MS-050 openers and totals (PREREGISTRATION.md Addendum J)."""

import pandas as pd
import pytest

from marketscope_research import market_ml as ml
from marketscope_research import openers_totals as ot
from marketscope_research import sharp_market as sm
from tests.test_market_ml import TABLE
from tests.test_sharp_market import KICK, rows, ts

# Total points with spikes at 41, 44, 47 and 51.
TOTALS = pd.Series({34: .06, 37: .07, 38: .05, 41: .12, 43: .08, 44: .12, 45: .06, 47: .12, 48: .07, 51: .1,
                    54: .08, 58: .07})
TOTALS = TOTALS / TOTALS.sum()


def test_total_buckets():
    assert [ot.total_bucket(x) for x in (38, 40.5, 41, 44.5, 45, 48.5, 49, 55)] == [0, 0, 1, 1, 2, 2, 3, 3]


def test_totals_calibration_and_mirror():
    for p in (0.45, 0.5, 0.55):
        w, pu, lo = ot.total_side_probabilities(TOTALS, 44.0, p, "over", 44.0)
        assert w / (w + lo) == pytest.approx(p, abs=1e-9)
        uw, upu, ul = ot.total_side_probabilities(TOTALS, 44.0, p, "under", 44.0)
        assert (uw, upu, ul) == pytest.approx((lo, pu, w))


def test_lower_over_lines_are_worth_more_and_key_totals_most():
    def ev(line):
        w, _pu, lo = ot.total_side_probabilities(TOTALS, 44.5, 0.5, "over", line)
        return ml.expected_value(w, lo, -110)

    assert ev(43.5) > ev(44.0) > ev(44.5)
    assert ev(43.5) - ev(44.5) > ev(45.5) - ev(46.5)  # crossing 44 is worth more than crossing 46


def spread_books(dk_open_line, dk_open_at="2026-10-12T10:00Z", dk_price=-110):
    df = pd.DataFrame(
        rows("g", "pinnacle", (pd.Timestamp("2026-10-11T10:00Z"), -3, -110, -110),
             (pd.Timestamp("2026-10-15T10:00Z"), -4, -110, -110))
        + rows("g", "draftkings", (pd.Timestamp(dk_open_at), dk_open_line, dk_price, -110),
               (pd.Timestamp("2026-10-17T10:00Z"), -4, -110, -110)))
    return sm.timelines(df)


def test_opener_positions_compare_with_pinnacle_at_the_open_only():
    tl = spread_books(-2.5)  # DK opens -2.5 while Pinnacle is -3: home side is better
    p = ot.opener_positions(tl, pd.Series({"g": KICK}), [TABLE] * 4)
    assert p[["book", "side", "line", "pin_line"]].values.tolist() == [["draftkings", "home", -2.5, -3.0]]
    assert p.loc[0, "value"] > 0  # -2.5 against a -4 close
    # Pinnacle's later move to -4 must not count at the open: DK opening -3.5 is worse for home at -3.
    later = ot.opener_positions(spread_books(-3.5), pd.Series({"g": KICK}), [TABLE] * 4)
    assert later["side"].tolist() == ["away"]


def test_opener_respects_the_price_bound():
    p = ot.opener_positions(spread_books(-2.5, dk_price=-130), pd.Series({"g": KICK}), [TABLE] * 4)
    assert p.empty


def test_horizon_totals_sides():
    df = pd.DataFrame(rows("g", "pinnacle", (ts("10:00", 16), 44.5, -110, -110))
                      + rows("g", "fanduel", (ts("10:00", 16), 43.5, -110, -110))
                      + rows("g", "draftkings", (ts("10:00", 16), 45.5, -112, -108)))
    h = ot.horizon_totals(sm.timelines(df), pd.Series({"g": KICK}), [TOTALS] * 4, horizons=(24,))
    got = {(r.book, r.side) for r in h.itertuples()}
    assert got == {("fanduel", "over"), ("draftkings", "under")}
    assert (h["value"] > -0.05).all()


def test_stale_total_values():
    df = pd.DataFrame(rows("g", "pinnacle", (ts("10:00", 16), 44.5, -110, -110), (ts("10:00", 17), 46.5, -110, -110)))
    cases = pd.DataFrame({"event_id": ["g"], "side": ["over"], "line": [44.5], "price": [-110]})
    v = ot.stale_total_values(cases, sm.timelines(df), pd.Series({"g": KICK}), [TOTALS] * 4)
    assert v.iloc[0] > 0  # over 44.5 against a 46.5 close
