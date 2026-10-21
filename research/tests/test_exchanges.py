"""MS-051 exchanges with fees (PREREGISTRATION.md Addendum K)."""

import pandas as pd
import pytest

from marketscope_research import exchanges as ex
from marketscope_research import sharp_market as sm
from tests.test_market_ml import TABLE
from tests.test_openers_totals import TOTALS
from tests.test_sharp_market import KICK, rows, ts


def test_fees():
    assert ex.win_profit("novig", 100) == pytest.approx(1.0)
    assert ex.win_profit("prophetx", 100) == pytest.approx(0.98)
    assert ex.win_profit("prophetx", 100, prophetx_fee=0.01) == pytest.approx(0.99)
    # Kalshi at p = 0.5: fee 0.07 * 0.25 = 0.0175 per contract; cost 0.5175, profit 0.4825.
    assert ex.win_profit("kalshi", 100) == pytest.approx(0.4825 / 0.5175)


def with_sizes(event, book, *moves):
    """rows() plus a second-side size equal to the first."""
    out = rows(event, book, *moves)
    for r in out:
        r["limit2"] = r["limit1"]
    return out


def books_frame(novig_size=500):
    return pd.DataFrame(
        with_sizes("g", "pinnacle", (ts("10:00", 16), -3, -110, -110), (ts("10:00", 17), -3.5, -105, -115),
                   (ts("12:00"), -4, -110, -110))
        + with_sizes("g", "novig", (ts("09:00", 16), -3, 102, -104, novig_size))
    )


def test_stale_exchange_cases_need_size():
    tl = sm.timelines(books_frame())
    cases = ex.stale_exchange_cases(tl, pd.Series({"g": KICK}), "spreads")
    first = cases[cases["pin_to"] == -3.5]
    assert first[["retail", "side", "line", "price"]].values.tolist() == [["novig", "home", -3.0, 102]]
    thin = ex.stale_exchange_cases(sm.timelines(books_frame(novig_size=50)), pd.Series({"g": KICK}), "spreads")
    assert thin.empty


def test_values_after_fees_and_against_the_close():
    tl = sm.timelines(books_frame())
    cases = ex.stale_exchange_cases(tl, pd.Series({"g": KICK}), "spreads")
    v = ex.add_values(cases, tl, pd.Series({"g": KICK}), [TABLE] * 4, [TOTALS] * 4, "retail")
    assert (v > 0).all()  # home -3 at +102 against a -4 close
    k = ex.position_value(tl["g"], KICK, "spreads", "home", -3.0, 102, "kalshi", [TABLE] * 4, [TOTALS] * 4)
    assert k < v.iloc[0]  # Kalshi's fee costs more than Novig's none


def test_horizon_positions_compare_with_pinnacle_at_that_time():
    tl = sm.timelines(books_frame())
    h = ex.horizon_exchange_positions(tl, pd.Series({"g": KICK}), "spreads", horizons=(24,))
    # At 24 h Pinnacle is -3.5 and Novig -3: the home side is better at Novig.
    assert h[["exchange", "side", "line"]].values.tolist() == [["novig", "home", -3.0]]
