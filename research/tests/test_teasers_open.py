"""MS-055a model-priced teasers and MS-057 model vs the early line."""

import numpy as np
import pandas as pd
import pytest

from marketscope_research import model_open as mo
from marketscope_research import sharp_market as sm
from marketscope_research import teasers_model as tm
from marketscope_research.backtest import teaser_break_even
from tests.test_sharp_market import rows


def games(n_per=300, seasons=(2016, 2017, 2018), seed=0):
    rng = np.random.default_rng(seed)
    out = []
    for s in seasons:
        for i in range(n_per):
            line = float(rng.choice([-1.5, -2.5, -3.0, -7.5, -8.5, -10.0]))
            margin = float(np.where(rng.random() < 0.15, 3, np.round(rng.normal(-line, 13))))
            out.append({"game_id": f"{s}-{i}", "season": s, "week": 1 + i % 17, "kickoff": pd.Timestamp(f"{s}-09-10", tz="UTC") + pd.Timedelta(hours=i),
                        "home": f"H{i}", "away": f"A{i}", "home_line": line, "total": 44.0, "margin": margin,
                        "points": 44.0})
    return pd.DataFrame(out)


def test_legs_are_walk_forward_and_priced_at_the_teased_line():
    legs = tm.leg_frame(games(), 2018, 2.0, 1000.0)
    assert set(legs["season"]) == {2018} and len(legs) == 600
    one = legs[legs["game_id"] == legs["game_id"].iloc[0]].set_index("side")
    assert one.loc["home", "teased"] == one.loc["home", "line"] + 6
    assert (legs["p"].between(0.5, 1)).all()  # six points always beats the median line


def test_teasing_a_favourite_through_3_and_7_beats_teasing_a_short_favourite_past_nothing():
    legs = tm.leg_frame(games(), 2018, 2.0, 1000.0)
    fav_8 = legs[(legs["line"] == -8.5)]["p"].mean()
    fav_10 = legs[(legs["line"] == -10.0)]["p"].mean()
    assert fav_8 > fav_10  # -8.5 -> -2.5 crosses 7 and 3; -10 -> -4 crosses only 7


def test_select_one_leg_per_game_above_break_even():
    legs = tm.leg_frame(games(), 2018, 2.0, 1000.0)
    sel = tm.select_legs(legs)
    assert sel["game_id"].is_unique and (sel["p"] >= teaser_break_even(-125)).all()


def test_model_frame_point_in_time():
    kick = pd.Timestamp("2026-10-18T17:00Z")
    schedule = pd.DataFrame([{"game_id": "g", "season": 2026, "week": 6, "kickoff": kick, "home": "KC",
                              "away": "LV", "neutral": False, "event_id": "e"},
                             {"game_id": "p", "season": 2026, "week": 5, "kickoff": pd.Timestamp("2026-10-11T17:00Z"),
                              "home": "X", "away": "Y", "neutral": False, "event_id": None}])
    ratings = pd.DataFrame({"season": [2026] * 4, "week": [0, 0, 5, 5], "team": ["KC", "LV", "KC", "LV"],
                            "adj_em": [2.0, 0.0, 6.0, 0.0]})
    tl = sm.timelines(pd.DataFrame(rows("e", "pinnacle", (pd.Timestamp("2026-10-11T12:00Z"), -3, -110, -110),
                                        (pd.Timestamp("2026-10-17T12:00Z"), -5, -110, -110))))
    f = mo.model_frame(schedule, ratings, tl)
    # d = Oct 12 17:00. Week 5's last game (Oct 11 17:00) + 16 h = Oct 12 09:00 <= d: week 5 is usable.
    assert f.loc[0, "pin_d"] == -3 and f.loc[0, "y"] == -2.0
    assert f.loc[0, "model_line"] == pytest.approx(-7.6) and f.loc[0, "x"] == pytest.approx(-4.6)
    # A game 10 hours earlier has d before the snapshot is usable, so it falls back to preseason.
    early = schedule.assign(kickoff=[kick - pd.Timedelta(hours=10), schedule["kickoff"].iloc[1]])
    assert mo.model_frame(early, ratings, tl).loc[0, "model_line"] == pytest.approx(-3.6)
