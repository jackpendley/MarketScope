"""MS-047 injury-report windows (PREREGISTRATION.md Addendum I)."""

import numpy as np
import pandas as pd
import pytest

from marketscope_research import injury_windows as iw
from marketscope_research import sharp_market as sm
from tests.test_sharp_market import rows

T = pd.Timestamp


def test_report_deadline_by_game_day_in_eastern_time():
    # Sunday 1 pm ET (EDT) -> Friday 4 pm EDT = 20:00 UTC
    assert iw.report_deadline(T("2026-10-18T17:00Z")) == T("2026-10-16T20:00Z")
    # Thursday 8:15 pm ET -> Wednesday 4 pm ET
    assert iw.report_deadline(T("2026-10-23T00:15Z")) == T("2026-10-21T20:00Z")  # Thu night = Fri 00:15 UTC
    # Monday night -> Saturday
    assert iw.report_deadline(T("2026-10-20T00:15Z")) == T("2026-10-17T20:00Z")
    # After the November clock change: Friday 4 pm EST = 21:00 UTC
    assert iw.report_deadline(T("2026-11-08T18:00Z")) == T("2026-11-06T21:00Z")


def test_net_events_is_away_minus_home():
    games = pd.DataFrame({"event_id": ["g"], "season": [2026], "week": [5], "home": ["KC"], "away": ["LV"]})
    ev = pd.DataFrame({"season": [2026] * 3, "week": [5] * 3, "team": ["LV", "LV", "KC"], "gsis_id": list("abc")})
    assert iw.net_events(games, ev).to_dict() == {"g": 1}


KICK = T("2026-10-18T17:00Z")  # deadline Friday Oct 16 20:00 UTC; window 16:00-22:00 UTC


def test_window_move_uses_the_line_at_each_window_edge():
    df = pd.DataFrame(rows("g", "pinnacle", (T("2026-10-12T10:00Z"), -3, -110, -110),
                           (T("2026-10-16T19:00Z"), -4, -110, -110),
                           (T("2026-10-16T23:00Z"), -6, -110, -110)))  # after the window: not counted
    games = pd.DataFrame({"event_id": ["g"], "week": [6], "kickoff": [KICK]})
    m = iw.window_moves(sm.timelines(df), games, pd.Series({"g": 1}))
    assert m.loc[0, "window_move"] == 1.0  # -3 -> -4: one point toward home
    assert m.loc[0, "full_move"] == 3.0  # -3 six days out -> -6 at the close


def test_news_window_tagging():
    games = pd.DataFrame({"event_id": ["g", "h"], "kickoff": [KICK, KICK]})
    cases = pd.DataFrame({"event_id": ["g", "g", "g", "h"], "side": ["home", "away", "home", "home"],
                          "pin_t": [T("2026-10-16T19:00Z"), T("2026-10-16T19:00Z"), T("2026-10-15T19:00Z"),
                                    T("2026-10-16T19:00Z")]})
    tags = iw.tag_news_window(cases, games, pd.Series({"g": 2, "h": 0}))
    assert tags.tolist() == [True, False, False, False]  # with the news, inside the window, N != 0


def test_slope_ci_recovers_a_planted_slope():
    rng = np.random.default_rng(0)
    n = rng.integers(-2, 3, 200)
    df = pd.DataFrame({"n": n, "move": 0.5 * n + rng.normal(0, 0.3, 200)})
    e = iw.slope_ci(df, "move", "n", resamples=300)
    assert e.low < 0.5 < e.high and e.low > 0.3


def test_diff_bootstrap():
    df = pd.DataFrame({"event_id": np.repeat([f"g{i}" for i in range(30)], 4),
                       "v": np.tile([0.1, 0.1, -0.02, -0.02], 30), "f": np.tile([True, True, False, False], 30)})
    e = iw.diff_bootstrap(df, "v", "f", resamples=200)
    assert e.value == pytest.approx(0.12) and e.low == pytest.approx(0.12) and e.n == 60
