"""MS-054 cross-market value (PREREGISTRATION.md Addendum P)."""

import numpy as np
import pandas as pd
import pytest

from marketscope_research import cross_market as cm
from marketscope_research import fair_value as fv

KICK = pd.Timestamp("2026-10-18T17:00Z")
D = KICK - pd.Timedelta(hours=24)


def engine():
    rng = np.random.default_rng(0)
    n = 4000
    s = rng.choice([1.5, 2.5, 3.0, 3.5, 6.5, 7.0], n)
    k = np.where(rng.random(n) < 0.12, 3, np.round(rng.normal(s, 13)).astype(int))
    g = pd.DataFrame({"home_line": -s, "total": 44.0, "margin": k, "points": np.round(rng.normal(44, 10)),
                      "season": 2016 + np.arange(n) % 9})
    f = fv.favourite_frame(g)
    return fv.Engine(fv.margin_model(f, 2.0, 1000.0), fv.total_model(f, 2.0, 6.0), fv.bucket_pmf(f, "k"),
                     fv.bucket_pmf(f, "pts"), "shin")


ENGINE = engine()


def rows(book, market, handicap, d1, d2, at="2026-10-16T12:00Z"):
    names = {"spreads": ("1", "2"), "totals": ("Over", "Under"), "moneyline": ("1", "2")}[market]
    mid = {"spreads": 100, "totals": 200, "moneyline": 141}[market] + int(handicap * 10)
    return [{"book": book, "market_id": mid, "market_type": market, "handicap": handicap, "outcome_name": n,
             "outcome_id": mid * 10 + i, "created_at": pd.Timestamp(at), "price": p, "active": True, "limit": None}
            for i, (n, p) in enumerate(zip(names, (d1, d2)))]


def ladder(*groups):
    return pd.DataFrame([r for g in groups for r in g])


def test_shin_and_bands():
    assert cm.shin(cm.Line(0, 1.909, 1.909)) == pytest.approx(0.5)
    assert cm.in_band(1.5) and not cm.in_band(1.25)  # -200 ok, -400 out


def test_line_at_respects_time():
    lad = ladder(rows("pinnacle", "spreads", -3.0, 1.91, 1.91), rows("pinnacle", "spreads", -3.5, 1.91, 1.91,
                                                                      at="2026-10-18T16:00Z"))
    cands = cm.book_candidates(lad)
    assert cm.line_at(cands, "pinnacle", "spreads", D).point == -3.0  # the -3.5 entry is later than d
    assert cm.line_at(cands, "pinnacle", "spreads", KICK).point in (-3.0, -3.5)


def test_moneyline_generous_against_its_own_spread_is_flagged():
    # DK: home -3 at -110/-110 implies roughly -160 on the moneyline; DK offers home -120.
    lad = ladder(rows("draftkings", "spreads", -3.0, 1.909, 1.909), rows("draftkings", "moneyline", 0, 1.833, 2.05),
                 rows("pinnacle", "moneyline", 0, 1.625, 2.4), rows("pinnacle", "spreads", -3.0, 1.909, 1.909))
    a, _b = cm.fixture_positions(lad, KICK, ENGINE, horizons=(24,))
    home = a[a["side"] == "home"]
    assert len(home) == 1 and home["value_d"].iloc[0] > 0
    assert home["value"].iloc[0] > 0  # Pinnacle's -160 close agrees home -120 was a good price


def test_same_line_value_against_the_consensus():
    lad = ladder(rows("pinnacle", "spreads", -3.0, 1.85, 1.98), rows("circasports", "spreads", -3.0, 1.87, 1.96),
                 rows("fanduel", "spreads", -3.0, 2.0, 1.83))
    _a, b = cm.fixture_positions(lad, KICK, ENGINE, horizons=(24,))
    got = b[(b["book"] == "fanduel") & (b["market"] == "spreads")]
    # Sharps lean home at -3; FanDuel offers home -3 at +100: the home side is worth more than fair.
    assert got["side"].tolist() == ["home"] and got["value_d"].iloc[0] > 0


def test_no_sharp_source_means_no_position():
    lad = ladder(rows("fanduel", "spreads", -3.0, 2.0, 1.83))
    _a, b = cm.fixture_positions(lad, KICK, ENGINE, horizons=(24,))
    assert b.empty
