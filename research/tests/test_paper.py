"""MS-045b paper portfolio job: quote choice, point-in-time cutoff, selection and grading."""

import numpy as np
import pandas as pd

from marketscope_research import paper
from tests.test_catalogue import BASE

T = pd.Timestamp


def quote_rows(book, at, home_line=-3.0, total=45.0, prices=(-110, -110, -110, -110)):
    hp, ap, op, up = prices
    rows = [("spreads", "HOME", home_line, hp), ("spreads", "AWAY", -home_line, ap),
            ("totals", "OVER", total, op), ("totals", "UNDER", total, up)]
    return [{"event_id": "e1", "bookmaker_key": book, "market_type": m, "selection": s, "point": p, "price": pr,
             "observed_at": T(at)} for m, s, p, pr in rows]


def test_book_line_prefers_caesars_and_never_uses_a_quote_after_the_cutoff():
    q = pd.DataFrame(quote_rows("draftkings", "2026-10-25T12:07Z", -2.5)
                     + quote_rows("williamhill_us", "2026-10-25T06:07Z", -3.0)
                     + quote_rows("williamhill_us", "2026-10-25T16:55Z", -8.0))
    b = paper.book_line(q, "e1", T("2026-10-25T16:50Z"))
    assert b["book"] == "williamhill_us" and b["home_line"] == -3.0
    assert b["observed_at"] == T("2026-10-25T06:07Z")


def test_book_line_falls_back_when_the_preferred_book_lacks_a_market():
    rows = [r for r in quote_rows("williamhill_us", "2026-10-25T12:07Z") if r["market_type"] == "spreads"]
    q = pd.DataFrame(rows + quote_rows("draftkings", "2026-10-25T12:07Z", -2.5))
    assert paper.book_line(q, "e1", T("2026-10-25T16:00Z"))["book"] == "draftkings"
    assert paper.book_line(q, "e1", T("2026-10-25T11:00Z")) is None


def test_grading_spreads_totals_and_teaser_legs():
    assert paper.grade_one("spread", "KC", -3, None, "KC", 7, 45) == "win"
    assert paper.grade_one("spread", "LV", 3, None, "KC", 3, 45) == "push"
    assert paper.grade_one("teaser_leg", "LV", 2.5, 8.5, "KC", 7, 45) == "win"
    assert paper.grade_one("total", "under", 45, None, "KC", 7, 44) == "win"


def history(n=200):
    rng = np.random.default_rng(3)
    return pd.DataFrame([{**BASE, "game_id": f"h{i}", "season": 2016 + i % 10,
                          "margin": float(rng.normal(0, 13))} for i in range(n)])


def test_selections_cover_every_strategy_shape():
    g = pd.DataFrame([{**BASE, "game_id": "w", "home_line": -8.0, "total": 47.0},       # Wong V0/V1, F3
                      {**BASE, "game_id": "d", "home_line": 3.0, "division": True}])    # F1, F2, F7
    s = paper.selections(g, history())
    by = {(r.strategy, r.game_id): r for r in s.itertuples()}
    assert by[("wong-V0", "w")].market == "teaser_leg" and by[("wong-V0", "w")].teased_line == -2.0
    assert ("wong-V1", "w") in by and ("wong-V2", "w") not in by  # home favourite: not a road leg
    assert by[("F3", "w")].side == "LV" and by[("F3", "w")].line == 8.0
    assert {k for k in by if k[1] == "d"} >= {("F1", "d"), ("F2", "d"), ("F7", "d")}
    assert by[("F7", "d")].market == "total" and by[("F7", "d")].side == "under"
    model = s[s["strategy"] == "wong-model"]
    assert (model["market"] == "teaser_leg").all() and (model["teased_line"] == model["line"] + 6).all()
