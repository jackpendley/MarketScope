"""MS-059: engine v3 line conversion fitted to the sharp books' own ladders (research/PREREGISTRATION.md
Addendum T, committed before this code). Pure functions over one fixture's lake ladder; the runner is
run_ladder_fit.py. Uses no game outcomes: the target is each sharp book's devigged price at its own
alternate lines (and its own moneyline), predicted from the same book's main line.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import cross_market as cm
from . import fair_value as fv
from .lake import mainline

BOOKS = ("pinnacle", "circasports", "bookmaker.eu")
HORIZONS = (48, 24, 6, 1, 0)  # hours before kickoff; 0 = the close (kickoff - 1 µs)
MAX_DISTANCE = 10.0
P_BAND = (0.10, 0.90)
TARGETS = ("spreads", "totals", "moneyline")
COLUMNS = ["h", "book", "market", "main", "p_main", "line", "distance", "key", "p_star", "hint"]


def decision_time(kickoff: pd.Timestamp, h: int) -> pd.Timestamp:
    return kickoff - (pd.Timedelta(hours=h) if h else pd.Timedelta(microseconds=1))


def main_line(cands: dict, book: str, market: str, t: pd.Timestamp) -> cm.Line | None:
    """The book's main line under the MS-058 rule (ghost markets removed before pickMain; exchanges and
    moneylines exempt)."""
    cs = cands.get((book, market), [])
    ghosts = market != "moneyline" and book not in cm.EXCHANGES
    best = mainline.pick_main(mainline.without_ghosts(cs, t) if ghosts else cs, t)
    if best is None:
        return None
    _, c, i, j = best
    return cm.Line(0.0 if market == "moneyline" else c.handicap, c.side1.prices[i], c.side2.prices[j])


def fixture_observations(ladder: pd.DataFrame, kickoff: pd.Timestamp) -> pd.DataFrame:
    """One row per (time, book, target): spread and total alternates, and the moneyline. p_main is the
    book's devigged main-line probability of side 1 (home covers / over), p_star the target's.
    `hint` is the other market's input to the engine: the main total for spreads and moneylines
    (ignored by the adopted margin model), the main spread for totals."""
    cands = cm.book_candidates(ladder)
    rows = []
    for h in HORIZONS:
        d = decision_time(kickoff, h)
        pin_spread = main_line(cands, "pinnacle", "spreads", d)
        for book in BOOKS:
            spr, tot = main_line(cands, book, "spreads", d), main_line(cands, book, "totals", d)
            spread_hint = spr.point if spr else pin_spread.point if pin_spread else 0.0
            total_hint = tot.point if tot else 44.0
            for market, main, hint in (("spreads", spr, total_hint), ("totals", tot, spread_hint)):
                if main is None:
                    continue
                p_main = cm.shin(main)
                for c in mainline.coherent(cands.get((book, market), []), d, market):
                    if c.handicap == main.point or c.handicap % 1 == 0:
                        continue
                    if abs(c.handicap - main.point) > MAX_DISTANCE:
                        continue
                    i, j = c.side1.at(d), c.side2.at(d)
                    p_star = cm.shin(cm.Line(c.handicap, c.side1.prices[i], c.side2.prices[j]))
                    if not P_BAND[0] <= p_star <= P_BAND[1]:
                        continue
                    rows.append({"h": h, "book": book, "market": market, "main": main.point, "p_main": p_main,
                                 "line": c.handicap, "distance": abs(c.handicap - main.point),
                                 "key": market == "spreads" and cm.spans_key(main.point, c.handicap),
                                 "p_star": p_star, "hint": hint})
            ml = main_line(cands, book, "moneyline", d)
            if ml is not None and spr is not None:
                rows.append({"h": h, "book": book, "market": "moneyline", "main": spr.point, "p_main": cm.shin(spr),
                             "line": 0.0, "distance": abs(spr.point), "key": False, "p_star": cm.shin(ml),
                             "hint": total_hint})
    return pd.DataFrame(rows, columns=COLUMNS)


def _pmf_and_thresholds(engine: fv.Engine, market: str, main: float, hint: float):
    """(pmf over x, threshold at the main line, threshold function for a target line)."""
    if market == "totals":
        return engine.total_pmf(main, hint), main, lambda line: line
    pmf = fv.home_margin_pmf(engine.margin_pmf(main, hint), main)
    if market == "moneyline":
        return pmf, -main, lambda _line: 0.0
    return pmf, -main, lambda line: -line


def predict(obs: pd.DataFrame, engine: fv.Engine, method: str, beta: float = 1.0) -> np.ndarray:
    """Each row's predicted no-push probability of side 1 at its target line (ties excluded for
    moneylines). One calibration per main line, shared by its alternates."""
    q = np.empty(len(obs))
    keys = ["market", "main", "p_main", "hint"]
    for (market, main, p_main, hint), idx in obs.groupby(keys, sort=False).indices.items():
        pmf, t_main, threshold = _pmf_and_thresholds(engine, market, main, hint)
        conv = fv.calibrate(pmf, t_main, p_main, method, beta)
        for k in idx:
            w, pu = conv(threshold(obs["line"].iat[k]))
            q[k] = w / (1 - pu) if pu < 1 else 0.5
    return q


def kl(p: np.ndarray, q: np.ndarray) -> np.ndarray:
    """Binary KL divergence KL(p ‖ q) in nats."""
    q = np.clip(q, 1e-9, 1 - 1e-9)
    p = np.clip(p, 1e-12, 1 - 1e-12)
    return p * np.log(p / q) + (1 - p) * np.log((1 - p) / (1 - q))


def score(obs: pd.DataFrame, engine: fv.Engine, method: str, beta: float = 1.0) -> pd.DataFrame:
    q = predict(obs, engine, method, beta)
    return obs.assign(q=q, kl=kl(obs["p_star"].to_numpy(float), q), abs_err=np.abs(obs["p_star"] - q))


def choose_beta(obs: pd.DataFrame, engine: fv.Engine) -> tuple[float, dict[float, float]]:
    """S's single β for one target: the lowest mean KL over the grid (Addendum T)."""
    losses = {b: float(score(obs, engine, "scale", b)["kl"].mean()) for b in fv.BETAS}
    return min(losses, key=losses.get), losses


def select(obs: pd.DataFrame, engine: fv.Engine, beta: float) -> tuple[str, dict[str, float]]:
    """The candidate with the lowest mean KL on the selection games (S at the given β)."""
    losses = {m: float(score(obs, engine, m, beta if m == "scale" else 1.0)["kl"].mean())
              for m in fv.CONVERSIONS}
    return min(losses, key=losses.get), losses
