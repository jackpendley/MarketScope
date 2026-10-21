"""MS-047: injury-report windows and the line (research/PREREGISTRATION.md Addendum I, committed
before this code). Pure functions; loading and reporting live in run_injury_windows.py.

Clubs file game-status designations by 4 pm ET the day before a Thursday game and two days before any
other game. The window [R - 4 h, R + 2 h] around that deadline R is when Out designations become
public and books react.
"""

from __future__ import annotations

from datetime import time, timedelta

import numpy as np
import pandas as pd

from . import sharp_market as sm
from .football_studies import RESAMPLES, SEED, Estimate

ET = "America/New_York"
BEFORE, AFTER = pd.Timedelta(hours=4), pd.Timedelta(hours=2)
I1_MIN_EVENTS, I2_MIN_CASES = 30, 50


def report_deadline(kickoff: pd.Timestamp) -> pd.Timestamp:
    """4 pm ET on the filing day: the day before a Thursday game, two days before any other."""
    local = kickoff.tz_convert(ET)
    days = 1 if local.weekday() == 3 else 2
    day = (local - timedelta(days=days)).date()
    return pd.Timestamp.combine(day, time(16, 0)).tz_localize(ET).tz_convert("UTC")


def net_events(games: pd.DataFrame, events: pd.DataFrame) -> pd.Series:
    """Per event_id: away events minus home events (games: event_id, season, week, home, away)."""
    cnt = events.groupby(["season", "week", "team"]).size()
    get = lambda s, w, t: int(cnt.get((s, w, t), 0))  # noqa: E731
    return pd.Series({g.event_id: get(g.season, g.week, g.away) - get(g.season, g.week, g.home)
                      for g in games.itertuples()}, dtype=int)


def window_moves(tl: dict[str, dict[str, sm.Book]], games: pd.DataFrame, net: pd.Series) -> pd.DataFrame:
    """I1 frame: Pinnacle's move across the window and from 6 days out to the close (margin points)."""
    rows = []
    for g in games.itertuples():
        pin = tl.get(g.event_id, {}).get("pinnacle")
        if pin is None:
            continue
        r = report_deadline(g.kickoff)
        a, b = pin.at(r - BEFORE), pin.at(r + AFTER)
        if a is None or b is None:
            continue
        early = pin.at(g.kickoff - pd.Timedelta(days=6))
        close = sm.close_line(pin, g.kickoff)
        rows.append({"event_id": g.event_id, "week": g.week, "n": int(net.get(g.event_id, 0)),
                     "window_move": a.point - b.point,
                     "full_move": (early.point - close) if early is not None and close is not None else np.nan})
    return pd.DataFrame(rows, columns=["event_id", "week", "n", "window_move", "full_move"])


def slope_ci(df: pd.DataFrame, y: str, x: str, resamples: int = RESAMPLES) -> Estimate:
    """OLS slope of y on x with a 95% game bootstrap (one row per game), seed 2026."""
    yv, xv = df[y].to_numpy(float), df[x].to_numpy(float)

    def fit(i):
        xi = xv[i]
        return np.polyfit(xi, yv[i], 1)[0] if np.ptp(xi) > 0 else np.nan

    rng = np.random.default_rng(SEED)
    boots = np.array([fit(rng.integers(0, len(df), len(df))) for _ in range(resamples)])
    lo, hi = np.nanquantile(boots, [0.025, 0.975])
    return Estimate(float(fit(np.arange(len(df)))), float(lo), float(hi), len(df))


def tag_news_window(cases: pd.DataFrame, games: pd.DataFrame, net: pd.Series) -> pd.Series:
    """True for S2 cases whose Pinnacle change falls inside the window of a game with N != 0 and moves
    with the news (toward home if N > 0, toward away if N < 0)."""
    deadline = {g.event_id: report_deadline(g.kickoff) for g in games.itertuples()}
    out = []
    for c in cases.itertuples():
        n = int(net.get(c.event_id, 0))
        r = deadline.get(c.event_id)
        inside = r is not None and r - BEFORE <= c.pin_t <= r + AFTER
        with_news = (n > 0 and c.side == "home") or (n < 0 and c.side == "away")
        out.append(bool(inside and with_news))
    return pd.Series(out, index=cases.index)


def diff_bootstrap(df: pd.DataFrame, value: str, flag: str, resamples: int = RESAMPLES) -> Estimate:
    """Mean(value | flag) - mean(value | not flag), with a 95% interval resampling games, seed 2026."""
    g = df.assign(_v=df[value].astype(float), _f=df[flag].astype(bool))
    per = g.groupby("event_id").apply(lambda d: pd.Series({
        "s1": d.loc[d["_f"], "_v"].sum(), "n1": d["_f"].sum(),
        "s0": d.loc[~d["_f"], "_v"].sum(), "n0": (~d["_f"]).sum()}), include_groups=False)
    a = per.to_numpy(float)
    rng = np.random.default_rng(SEED)
    idx = rng.integers(0, len(per), (resamples, len(per)))
    s = a[idx].sum(axis=1)
    boots = s[:, 0] / s[:, 1] - s[:, 2] / s[:, 3]
    lo, hi = np.nanquantile(boots, [0.025, 0.975])
    t = a.sum(axis=0)
    return Estimate(float(t[0] / t[1] - t[2] / t[3]), float(lo), float(hi), int(t[1]))


TIMELINE = (("6 days", pd.Timedelta(days=6)), ("5 days", pd.Timedelta(days=5)), ("4 days", pd.Timedelta(days=4)),
            ("3 days", pd.Timedelta(days=3)), ("2 days", pd.Timedelta(days=2)), ("1 day", pd.Timedelta(days=1)),
            ("6 hours", pd.Timedelta(hours=6)))


def news_timeline(tl: dict[str, dict[str, sm.Book]], games: pd.DataFrame, net: pd.Series) -> pd.DataFrame:
    """For games with N != 0: Pinnacle's cumulative move since 6 days out, oriented by the news
    (positive = toward the healthier side), at each point before kickoff and at the close."""
    rows = []
    for g in games.itertuples():
        n = int(net.get(g.event_id, 0))
        pin = tl.get(g.event_id, {}).get("pinnacle")
        if n == 0 or pin is None:
            continue
        start = pin.at(g.kickoff - TIMELINE[0][1])
        close = sm.close_line(pin, g.kickoff)
        if start is None or close is None:
            continue
        row = {"event_id": g.event_id, "n": n}
        for label, lead in TIMELINE[1:]:
            q = pin.at(g.kickoff - lead)
            row[label] = (start.point - q.point) * np.sign(n) if q is not None else np.nan
        row["close"] = (start.point - close) * np.sign(n)
        rows.append(row)
    return pd.DataFrame(rows)
