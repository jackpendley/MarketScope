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
        # 44.0: the adopted margin model ignores the total
        w, _pu, lo = engine.spread_side(cq.point, 44.0, ml.no_vig_home(cq.price1, cq.price2), side, line)
        rows.append({"event_id": r.event_id, "side": side, "line": line, "price": price,
                     "value": ml.expected_value(w, lo, price)})
    return pd.DataFrame(rows, columns=["event_id", "side", "line", "price", "value"])


# --- Addendum V: the shared early line and a market-only baseline ---------------------------------
#
# y = close - L and x = model - L share L (Pinnacle's line at d). If L carries noise that later
# reverses, the slope is positive for any reasonable estimate, informative or not. The baseline B is
# what the market itself implied before d: team ratings fitted to Pinnacle's closing home spreads of
# 2026 games already final at d.

RIDGE = 1.0
FINAL_AFTER = pd.Timedelta(hours=4)  # a game counts as final this long after kickoff


def closes_frame(schedule: pd.DataFrame, tl: dict[str, dict[str, sm.Book]]) -> pd.DataFrame:
    """Pinnacle's closing home spread for every game with one (Addendum C's close rule)."""
    rows = []
    for g in schedule.itertuples():
        pin = tl.get(g.event_id, {}).get("pinnacle") if isinstance(g.event_id, str) else None
        close = sm.close_line(pin, g.kickoff) if pin is not None else None
        if close is not None:
            rows.append({"home": g.home, "away": g.away, "neutral": bool(g.neutral), "kickoff": g.kickoff,
                         "close": close})
    return pd.DataFrame(rows, columns=["home", "away", "neutral", "kickoff", "close"])


def market_ratings(closes: pd.DataFrame, t: pd.Timestamp) -> tuple[dict[str, float], float] | None:
    """Ridge least squares of -(closing home spread) = r_home - r_away + h over games final before t.
    The ratings are shrunk toward 0 (λ = 1 game); the home advantage h is not shrunk."""
    past = closes[closes["kickoff"] + FINAL_AFTER <= t]
    if not len(past):
        return None
    teams = sorted(set(past["home"]) | set(past["away"]))
    col = {k: i for i, k in enumerate(teams)}
    X = np.zeros((len(past), len(teams) + 1))
    for i, r in enumerate(past.itertuples()):
        X[i, col[r.home]], X[i, col[r.away]] = 1.0, -1.0
        X[i, -1] = 0.0 if r.neutral else 1.0
    y = -past["close"].to_numpy(float)
    penalty = np.diag([RIDGE] * len(teams) + [0.0])
    beta = np.linalg.solve(X.T @ X + penalty, X.T @ y)
    return dict(zip(teams, beta[:-1])), float(beta[-1])


def add_baseline(frame: pd.DataFrame, schedule: pd.DataFrame, closes: pd.DataFrame) -> pd.DataFrame:
    """frame (model_frame output) plus the baseline line B at d and xb = B - L (NaN when either team has no
    earlier closing line)."""
    games = schedule.set_index("event_id")
    lines = []
    for r in frame.itertuples():
        g = games.loc[r.event_id]
        fit = market_ratings(closes, g.kickoff - LEAD)
        if fit is None or g.home not in fit[0] or g.away not in fit[0]:
            lines.append(np.nan)
            continue
        ratings, h = fit
        lines.append(-(ratings[g.home] - ratings[g.away] + (0.0 if g.neutral else h)))
    out = frame.assign(baseline_line=lines)
    return out.assign(xb=out["baseline_line"] - out["pin_d"])


def permutation_slopes(frame: pd.DataFrame, n: int = 1000, seed: int = 2026) -> np.ndarray:
    """The primary slope with model lines shuffled across games within each week: what the shared early
    line alone produces."""
    rng = np.random.default_rng(seed)
    y = frame["y"].to_numpy(float)
    out = np.empty(n)
    for i in range(n):
        shuffled = frame.groupby("week")["model_line"].transform(lambda s: rng.permutation(s.to_numpy()))
        x = shuffled.to_numpy(float) - frame["pin_d"].to_numpy(float)
        out[i] = np.polyfit(x, y, 1)[0] if np.ptp(x) > 0 else np.nan
    return out


def joint_permutation(frame: pd.DataFrame, n: int = 1000, seed: int = 2026) -> np.ndarray:
    """Addendum W: the joint regression's model coefficient (y on x and xb) with model lines shuffled
    within each week. With a noisy baseline, x still carries the early line's leftover noise, so a model
    with no information gets a positive coefficient; this is that coefficient's null distribution."""
    rng = np.random.default_rng(seed)
    y, xb, early = frame["y"].to_numpy(float), frame["xb"].to_numpy(float), frame["pin_d"].to_numpy(float)
    out = np.empty(n)
    for i in range(n):
        shuffled = frame.groupby("week")["model_line"].transform(lambda s: rng.permutation(s.to_numpy()))
        X = np.column_stack([np.ones(len(frame)), shuffled.to_numpy(float) - early, xb])
        out[i] = np.linalg.lstsq(X, y, rcond=None)[0][1]
    return out
