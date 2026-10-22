"""MS-056: do totals lag a public weather-forecast revision? (research/PREREGISTRATION.md Addendum U,
committed before this code). Pure functions over one game's archived model runs (weather_runs.py) and
its lake ladder; the runner is run_weather_timing.py.

A run r becomes available at r + 6 h. Its revision is the change in game-window wind from the run
6 hours earlier. An event is a revision of at least 4 mph, where either run has at least 12 mph, made
available between 72 h and 1 h before kickoff. At each event we take the forecast's side of each
book's main total (more wind: under) 10 minutes after availability and score it at the
sharp-consensus close, with engine v3's totals conversion and the MS-058 ghost rule.
"""

from __future__ import annotations

import pandas as pd

from . import cross_market as cm
from . import fair_value as fv
from . import ladder_fit as lf

MODEL = "ecmwf_ifs"
AVAILABLE = pd.Timedelta(hours=6)
RUN_STEP = pd.Timedelta(hours=6)
MIN_REVISION, MIN_WIND = 4.0, 12.0
EARLIEST, LATEST = pd.Timedelta(hours=72), pd.Timedelta(hours=1)
DECISION_DELAY = pd.Timedelta(minutes=10)
PLACEBO = -pd.Timedelta(hours=3)
REACTION = pd.Timedelta(hours=6)
BOOKS = ("pinnacle", "draftkings", "fanduel", "caesars", "hardrockbet")
PRICE_BAND = (-200, 200)
REV_COLUMNS = ["run", "available", "wind", "prev_wind", "dw", "in_window", "event"]


def revisions(runs: pd.DataFrame, kickoff: pd.Timestamp, column: str = "wind_mph",
              min_revision: float = MIN_REVISION, min_level: float = MIN_WIND,
              earliest: pd.Timedelta = EARLIEST) -> pd.DataFrame:
    """One row per run that has a predecessor 6 h earlier. runs: one game's rows (run, wind_mph, ...)."""
    r = runs.sort_values("run").set_index("run")[column]
    rows = []
    for run, w in r.items():
        prev = r.get(run - RUN_STEP)
        if prev is None or pd.isna(prev):
            continue
        avail = run + AVAILABLE
        in_window = kickoff - earliest <= avail <= kickoff - LATEST
        dw = float(w - prev)
        rows.append({"run": run, "available": avail, "wind": float(w), "prev_wind": float(prev), "dw": dw,
                     "in_window": in_window,
                     "event": in_window and abs(dw) >= min_revision and max(w, prev) >= min_level})
    return pd.DataFrame(rows, columns=REV_COLUMNS)


def spread_hint(cands: dict, t: pd.Timestamp) -> float:
    spr = lf.main_line(cands, "pinnacle", "spreads", t)
    return spr.point if spr else 0.0


def fair_total(engine: fv.Engine, cands: dict, side: str, line: float, t: pd.Timestamp) -> tuple[float, float] | None:
    """Sharp-consensus (win, loss) for over/under at `line` at time t (Addendum P sources, Shin devig,
    the engine's totals conversion)."""
    hint = spread_hint(cands, t)
    probs = []
    for src_book in cm.SHARP:
        src = lf.main_line(cands, src_book, "totals", t)
        if src is not None:
            w, _pu, lo = engine.total_side(src.point, hint, cm.shin(src), side, line)
            probs.append((w, lo))
    if not probs:
        return None
    return sum(p[0] for p in probs) / len(probs), sum(p[1] for p in probs) / len(probs)


def positions(ladder: pd.DataFrame, kickoff: pd.Timestamp, revs: pd.DataFrame, engine: fv.Engine,
              offset: pd.Timedelta = DECISION_DELAY, cands: dict | None = None) -> pd.DataFrame:
    """The forecast's side of each book's main total at each event's availability + offset, valued at
    the sharp-consensus close. `cands`: cm.book_candidates(ladder), if already built."""
    cands = cands if cands is not None else cm.book_candidates(ladder)
    close_t = kickoff - pd.Timedelta(microseconds=1)
    rows = []
    for e in revs[revs["event"]].itertuples():
        d = e.available + offset
        if d >= close_t:
            continue
        side = "under" if e.dw > 0 else "over"
        for book in BOOKS:
            q = lf.main_line(cands, book, "totals", d)
            if q is None:
                continue
            dec = q.d1 if side == "over" else q.d2
            price = cm.american(dec)
            if not PRICE_BAND[0] <= price <= PRICE_BAND[1]:
                continue
            close = fair_total(engine, cands, side, q.point, close_t)
            if close is None:
                continue
            rows.append({"run": e.run, "dw": e.dw, "book": book, "side": side, "line": q.point, "price": price,
                         "value": cm.value(*close, dec)})
    return pd.DataFrame(rows, columns=["run", "dw", "book", "side", "line", "price", "value"])


def reaction(ladder: pd.DataFrame, kickoff: pd.Timestamp, revs: pd.DataFrame,
             cands: dict | None = None) -> pd.DataFrame:
    """Pinnacle's main-total change from each in-window run's availability to 6 h later (capped at the
    close) and to the close."""
    cands = cands if cands is not None else cm.book_candidates(ladder)
    close_t = kickoff - pd.Timedelta(microseconds=1)
    rows = []
    for e in revs[revs["in_window"]].itertuples():
        at = lf.main_line(cands, "pinnacle", "totals", e.available)
        later = lf.main_line(cands, "pinnacle", "totals", min(e.available + REACTION, close_t))
        close = lf.main_line(cands, "pinnacle", "totals", close_t)
        if at is None or later is None or close is None:
            continue
        rows.append({"run": e.run, "dw": e.dw, "event": e.event, "move_6h": later.point - at.point,
                     "move_close": close.point - at.point})
    return pd.DataFrame(rows, columns=["run", "dw", "event", "move_6h", "move_close"])


def minutes_to_first_move(ladder: pd.DataFrame, kickoff: pd.Timestamp, revs: pd.DataFrame,
                          cands: dict | None = None) -> pd.DataFrame:
    """Exploratory: minutes from each in-window run's availability to Pinnacle's next main-total point
    change (NaN if none before the close)."""
    cands = cands if cands is not None else cm.book_candidates(ladder)
    close_t = kickoff - pd.Timedelta(microseconds=1)
    cs = cands.get(("pinnacle", "totals"), [])
    times = sorted({t for c in cs for s in (c.side1, c.side2) for t in s.times if t < close_t})
    rows = []
    for e in revs[revs["in_window"]].itertuples():
        start = lf.main_line(cands, "pinnacle", "totals", e.available)
        if start is None:
            continue
        mins = float("nan")
        for t in times:
            if t <= e.available:
                continue
            now = lf.main_line(cands, "pinnacle", "totals", t)
            if now is not None and now.point != start.point:
                mins = (t - e.available).total_seconds() / 60
                break
        rows.append({"run": e.run, "event": e.event, "minutes": mins})
    return pd.DataFrame(rows, columns=["run", "event", "minutes"])
