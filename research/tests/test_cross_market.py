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


def test_alt_positions_skip_the_main_line_and_flag_key_numbers():
    lad = ladder(rows("pinnacle", "spreads", -3.0, 1.909, 1.909),
                 rows("draftkings", "spreads", -3.0, 1.909, 1.909),       # main
                 rows("draftkings", "spreads", -2.5, 1.80, 2.05),         # alt across 3: away +2.5 at +105
                 rows("draftkings", "spreads", -6.5, 3.2, 1.36))          # alt far away
    alt = cm.alt_positions(lad, KICK, ENGINE, horizons=(24,))
    assert (alt["line"] != -3.0).all()
    if len(alt):
        assert alt.loc[alt["line"] == -2.5, "key"].all() and (alt["value_d"] > 0).all()


def test_engine_pmf_cache_returns_the_same_object():
    m = ENGINE.margin
    assert m.pmf(3.0, 44.0) is m.pmf(3.0, 44.0)


def test_spans_key():
    assert cm.spans_key(-3.0, -2.5) and cm.spans_key(-2.5, -3.5) and cm.spans_key(-6.5, -7.5)
    assert not cm.spans_key(-3.5, -4.5) and not cm.spans_key(-3.0, -3.0)


def test_coherent_option_ignores_a_ghost_retail_main_line():
    lad = ladder(rows("pinnacle", "spreads", -7.0, 1.909, 1.909, at="2026-10-17T12:00Z"),
                 rows("caesars", "spreads", -10.0, 1.87, 1.87, at="2026-09-01T02:00Z"),   # ghost
                 rows("caesars", "spreads", -7.0, 1.909, 1.926, at="2026-10-17T12:00Z"),
                 rows("caesars", "spreads", -7.5, 2.0, 1.83, at="2026-10-17T12:00Z"))
    cands = cm.book_candidates(lad)
    assert cm.line_at(cands, "caesars", "spreads", D).point == -10.0
    assert cm.line_at(cands, "caesars", "spreads", D, coherent=True).point == -7.0
    _a, b = cm.fixture_positions(lad, KICK, ENGINE, horizons=(24,), coherent=True)
    assert (b.loc[b["book"] == "caesars", "line"] != -10.0).all()


def test_value_direct_uses_the_sharp_books_own_price_at_that_line():
    lad = ladder(rows("pinnacle", "spreads", -3.5, 1.909, 1.909), rows("pinnacle", "spreads", -6.5, 2.6, 1.5),
                 rows("bookmaker.eu", "spreads", -6.5, 2.5, 1.55))
    cands = cm.book_candidates(lad)
    p_pin = cm.shin(cm.Line(-6.5, 2.6, 1.5))
    p_bm = cm.shin(cm.Line(-6.5, 2.5, 1.55))
    p = (p_pin + p_bm) / 2
    got = cm.value_direct(cands, "spreads", "home", -6.5, KICK, 2.8)
    assert got == pytest.approx(p * 1.8 - (1 - p))
    assert cm.value_direct(cands, "spreads", "home", -7.0, KICK, 2.8) is None  # integer line
    assert cm.value_direct(cands, "spreads", "home", -9.5, KICK, 2.8) is None  # no sharp price there
    assert cm.value_direct(cands, "moneyline", "home", 0.0, KICK, 2.0) is None


def test_b_rows_carry_the_window_the_price_was_in_effect():
    lad = ladder(rows("pinnacle", "spreads", -3.0, 1.85, 1.98), rows("fanduel", "spreads", -3.0, 2.0, 1.83),
                 rows("fanduel", "spreads", -3.0, 1.95, 1.87, at="2026-10-18T10:00Z"))
    _a, b = cm.fixture_positions(lad, KICK, ENGINE, horizons=(24,))
    r = b[b["book"] == "fanduel"].iloc[0]
    assert r["since"] == pd.Timestamp("2026-10-16T12:00Z") and r["until"] == pd.Timestamp("2026-10-18T10:00Z")


def test_corroborated_matches_book_line_side_price_and_window():
    b = pd.DataFrame([
        {"event_id": "e1", "book": "fanduel", "market": "spreads", "side": "away", "line": -3.0, "price": -120,
         "since": pd.Timestamp("2026-10-16T12:00Z"), "until": pd.Timestamp("2026-10-18T10:00Z")},
        {"event_id": "e1", "book": "fanduel", "market": "spreads", "side": "away", "line": -3.0, "price": -115,
         "since": pd.Timestamp("2026-10-16T12:00Z"), "until": pd.Timestamp("2026-10-18T10:00Z")},
        {"event_id": "e1", "book": "caesars", "market": "spreads", "side": "home", "line": -3.0, "price": -110,
         "since": pd.Timestamp("2026-10-16T12:00Z"), "until": pd.Timestamp("2026-10-18T10:00Z")},
        {"event_id": "e1", "book": "draftkings", "market": "moneyline", "side": "home", "line": 0.0, "price": -150,
         "since": pd.Timestamp("2026-10-16T12:00Z"), "until": pd.Timestamp("2026-10-17T00:00Z")},
    ])
    obs = pd.DataFrame([
        # FanDuel away +3 at -120 seen inside the window (away point is posted from the away side)
        {"event_id": "e1", "bookmaker_key": "fanduel", "market_type": "spreads", "selection": "AWAY", "point": 3.0,
         "american_price": -120, "observed_at": pd.Timestamp("2026-10-17T12:00Z")},
        # DraftKings moneyline at -150, but after the window closed
        {"event_id": "e1", "bookmaker_key": "draftkings", "market_type": "h2h", "selection": "HOME", "point": None,
         "american_price": -150, "observed_at": pd.Timestamp("2026-10-17T06:00Z")},
    ])
    assert cm.corroborated(b, obs).tolist() == [True, False, pd.NA, False]
