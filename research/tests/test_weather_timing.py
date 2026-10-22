"""MS-056 weather-forecast revisions and totals timing (PREREGISTRATION.md Addendum U)."""

import numpy as np
import pandas as pd
import pytest

from marketscope_research import fair_value as fv
from marketscope_research import weather_runs as wr
from marketscope_research import weather_timing as wt

from test_cross_market import ladder, rows


def engine():
    """Synthetic games with a real spread of total points (the cross-market test engine's are constant)."""
    rng = np.random.default_rng(1)
    n = 4000
    s = rng.choice([1.5, 3.0, 6.5], n)
    g = pd.DataFrame({"home_line": -s, "total": rng.choice([41.5, 44.5, 47.5], n),
                      "margin": np.round(rng.normal(s, 13)), "points": np.round(rng.normal(44, 10, n)),
                      "season": 2016 + np.arange(n) % 9})
    f = fv.favourite_frame(g)
    return fv.Engine(fv.margin_model(f, 2.0, 1000.0), fv.total_model(f, 2.0, 6.0), fv.bucket_pmf(f, "k"),
                     fv.bucket_pmf(f, "pts"), "shin")


ENGINE = engine()

KICK = pd.Timestamp("2026-10-18T17:00Z")


def run_frame(winds, first="2026-10-15T00:00Z"):
    runs = pd.date_range(first, periods=len(winds), freq="6h", tz="UTC")
    return pd.DataFrame({"game_id": "g", "model": wt.MODEL, "run": runs, "wind_mph": winds,
                         "gust_mph": winds, "precip_in": 0.0})


def test_runs_for_covers_leads_from_7_to_84_hours():
    runs = wr.runs_for(pd.Series([KICK]))
    assert min(KICK - r for r in runs) >= wr.MIN_LEAD and max(KICK - r for r in runs) <= wr.MAX_LEAD
    assert len(runs) == 13


def test_window_values_average_wind_and_need_every_hour():
    idx = pd.date_range("2026-10-18T16:00Z", periods=6, freq="h")
    h = pd.DataFrame({"wind_speed_10m": [1, 10, 12, 14, 16, 99], "wind_gusts_10m": [1, 20, 25, 30, 22, 99],
                      "precipitation": [1, 0.1, 0.0, 0.2, 0.0, 9]}, index=idx)
    v = wr.window_values(h, KICK)
    assert v == pytest.approx({"wind_mph": 13.0, "gust_mph": 30.0, "precip_in": 0.3})
    assert wr.window_values(h.iloc[:4], KICK) is None


def test_build_caches_runs_and_skips_unavailable(tmp_path, monkeypatch):
    calls = []

    def fake(model, run, coords):
        calls.append(run)
        if run.hour == 0:
            return None  # not in the archive
        idx = pd.date_range(run, periods=100, freq="h")
        return [pd.DataFrame({"wind_speed_10m": 10.0, "wind_gusts_10m": 15.0, "precipitation": 0.0}, index=idx)
                for _ in coords]

    monkeypatch.setattr(wr, "fetch_run", fake)
    monkeypatch.setattr(wr.time, "sleep", lambda _s: None)
    games = pd.DataFrame({"game_id": ["g"], "kickoff": [KICK], "lat": [42.8], "lon": [-78.8]})
    now = pd.Timestamp("2026-10-20T00:00Z")
    out = wr.build(games, wt.MODEL, cache=tmp_path, now=now)
    assert len(out) == 13 - sum(r.hour == 0 for r in wr.runs_for(games["kickoff"]))
    n = len(calls)
    wr.build(games, wt.MODEL, cache=tmp_path, now=now)
    assert len(calls) - n == sum(r.hour == 0 for r in wr.runs_for(games["kickoff"]))  # only the missing runs again


def test_revisions_flag_events_inside_the_window():
    # runs every 6 h from Oct 15 00:00; the 12 mph jump at the run of Oct 17 00:00 is public at 06:00, 35 h out
    winds = [8, 8, 8, 8, 8, 8, 8, 8, 14, 14, 13, 13]
    revs = wt.revisions(run_frame(winds), KICK)
    ev = revs[revs["event"]]
    assert ev["run"].tolist() == [pd.Timestamp("2026-10-17T00:00Z")] and ev["dw"].item() == 6
    assert revs.loc[revs["run"] == pd.Timestamp("2026-10-17T06:00Z"), "event"].item() is False


def test_small_or_calm_revisions_are_not_events():
    assert not wt.revisions(run_frame([8, 8, 8, 8, 8, 8, 8, 8, 11, 11]), KICK)["event"].any()  # +3 mph
    assert not wt.revisions(run_frame([2, 2, 2, 2, 2, 2, 2, 2, 7, 7]), KICK)["event"].any()   # +5, both < 12


def test_events_outside_72_hours_do_not_count():
    revs = wt.revisions(run_frame([5, 15, 15], first="2026-10-14T00:00Z"), KICK)  # public ~4 days out
    assert not revs["in_window"].any() and not revs["event"].any()


def totals_ladder(move_at=None):
    early, late = "2026-10-16T12:00Z", move_at
    g = [rows("pinnacle", "totals", 44.5, 1.95, 1.95, at=early),
         rows("circasports", "totals", 44.5, 1.95, 1.95, at=early),
         rows("draftkings", "totals", 44.5, 1.91, 1.91, at=early),
         rows("draftkings", "spreads", -3.0, 1.91, 1.91, at=early),
         rows("pinnacle", "spreads", -3.0, 1.95, 1.95, at=early)]
    if late:  # the sharp books move to 43.5 later (wind went up)
        g += [rows("pinnacle", "totals", 43.5, 1.95, 1.95, at=late), rows("circasports", "totals", 43.5, 1.95, 1.95,
                                                                          at=late)]
        df = ladder(*g)
        stale = (df["book"].isin(["pinnacle", "circasports"])) & (df["handicap"] == 44.5)
        off = df[stale].assign(created_at=pd.Timestamp(late), active=False)
        return pd.concat([df, off], ignore_index=True)
    return ladder(*g)


def event_revs():
    return wt.revisions(run_frame([8, 8, 8, 8, 8, 8, 8, 8, 14, 14, 13, 13]), KICK)


def test_positions_take_the_under_on_more_wind_and_gain_when_the_close_follows():
    lad = totals_ladder(move_at="2026-10-17T12:00Z")
    pos = wt.positions(lad, KICK, event_revs(), ENGINE)
    assert set(pos["book"]) == {"pinnacle", "draftkings"} and set(pos["side"]) == {"under"}
    assert (pos["line"] == 44.5).all() and (pos["value"] > 0).all()


def test_placebo_and_no_move():
    flat = wt.positions(totals_ladder(), KICK, event_revs(), ENGINE)
    assert flat.loc[flat["book"] == "pinnacle", "value"].item() == pytest.approx(-0.025, abs=0.002)
    early = wt.positions(totals_ladder(move_at="2026-10-17T12:00Z"), KICK, event_revs(), ENGINE, wt.PLACEBO)
    assert len(early) == 2  # positions 3 h before the run was public


def test_reaction_measures_pinnacle_moves_after_availability():
    lad = totals_ladder(move_at="2026-10-17T09:00Z")
    r = wt.reaction(lad, KICK, event_revs())
    row = r[r["run"] == pd.Timestamp("2026-10-17T00:00Z")].iloc[0]
    assert row["move_6h"] == -1.0 and row["move_close"] == -1.0
    first = wt.minutes_to_first_move(lad, KICK, event_revs())
    assert first.loc[first["event"], "minutes"].item() == pytest.approx(180)
