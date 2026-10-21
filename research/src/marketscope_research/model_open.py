"""MS-057: does the market move toward the ratings model from early in the week? (research/
PREREGISTRATION.md Addendum O, committed before this code). Pure functions; runner run_model_open.py.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import market_ml as ml
from . import sharp_market as sm
from .ml.football_features import rating_available_at, rating_margin

LEAD = pd.Timedelta(days=6)
MIN_DISAGREEMENT = 1.5


def model_frame(schedule: pd.DataFrame, ratings: pd.DataFrame, tl: dict[str, dict[str, sm.Book]]) -> pd.DataFrame:
    """Per game: Pinnacle's line at d = kickoff - 6 days, the ratings-only model line at d, the
    disagreement (model - Pinnacle) and Pinnacle's move to the close (close - line at d)."""
    avail = rating_available_at(schedule)
    rows = []
    for g in schedule.itertuples():
        pin = tl.get(g.event_id, {}).get("pinnacle") if isinstance(g.event_id, str) else None
        if pin is None:
            continue
        d = g.kickoff - LEAD
        q, close = pin.at(d), sm.close_line(pin, g.kickoff)
        if q is None or close is None:
            continue
        margin = rating_margin(g, d, ratings, avail)
        if np.isnan(margin):
            continue
        model_line = -margin
        rows.append({"event_id": g.event_id, "week": g.week, "pin_d": q.point, "price1": q.price1,
                     "price2": q.price2, "model_line": model_line, "x": model_line - q.point,
                     "y": close - q.point, "close": close})
    return pd.DataFrame(rows, columns=["event_id", "week", "pin_d", "price1", "price2", "model_line", "x", "y",
                                       "close"])


def model_side_values(frame: pd.DataFrame, tl, kickoffs: pd.Series, engine) -> pd.DataFrame:
    """Secondary: take the side the model prefers at Pinnacle's line at d when |x| >= 1.5; value at
    Pinnacle's no-vig close with the engine's margin distribution."""
    rows = []
    for r in frame[frame["x"].abs() >= MIN_DISAGREEMENT].itertuples():
        cq = ml.close_quote(tl[r.event_id]["pinnacle"], kickoffs[r.event_id])
        if cq is None:
            continue
        side = "away" if r.x > 0 else "home"  # model's home line higher = home weaker = take away
        line = r.pin_d if side == "home" else -r.pin_d
        price = r.price1 if side == "home" else r.price2
        pmf = engine.margin_pmf(cq.point, 44.0)  # the adopted margin model ignores the total
        w, _pu, lo = ml.side_probabilities(pmf, cq.point, ml.no_vig_home(cq.price1, cq.price2), side, line)
        rows.append({"event_id": r.event_id, "side": side, "line": line, "price": price,
                     "value": ml.expected_value(w, lo, price)})
    return pd.DataFrame(rows, columns=["event_id", "side", "line", "price", "value"])
