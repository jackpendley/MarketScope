"""MS-054: cross-market value on main markets (research/PREREGISTRATION.md Addendum P, committed before
this code). Pure functions over one fixture's lake ladder; the runner is run_cross_market.py.

A: is a retail book's moneyline worth more than its own spread implies?
B: is a retail main-line price worth more than the sharp-consensus fair probability at that line?
Both are scored at the sharp-consensus close. Sharp sources devig their own main line (Shin) and are
converted to the requested line with the fair-value engine; moneyline targets use the sources' own
moneylines.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from . import fair_value as fv
from . import market_ml as ml
from . import openers_totals as ot
from .lake import mainline

KEYS = (3.0, 7.0)


def spans_key(main: float, alt: float) -> bool:
    """3 or 7 lies between the main line and the alternate, inclusive (Addendum Q)."""
    lo, hi = sorted((abs(main), abs(alt)))
    return lo != hi and any(lo <= k <= hi for k in KEYS)

RETAIL = ("draftkings", "fanduel", "caesars", "hardrockbet")
SHARP = ("pinnacle", "circasports", "bookmaker.eu", "novig.us")
HORIZONS = (48, 24, 6, 1)
PRICE_BAND = (-200, 200)
MARKETS = ("spreads", "totals", "moneyline")


@dataclass(frozen=True)
class Line:
    point: float           # home spread, total, or 0 for moneylines
    d1: float              # decimal price, side 1 (home / over)
    d2: float              # decimal price, side 2 (away / under)


def book_candidates(ladder: pd.DataFrame) -> dict[tuple[str, str], list[mainline.Candidate]]:
    """(book, market) -> main-line candidates, built once per fixture."""
    out = {}
    for book, rows in ladder.groupby("book"):
        for market in MARKETS:
            out[(book, market)] = mainline.candidates(rows, market)
    return out


def line_at(cands: dict, book: str, market: str, t: pd.Timestamp) -> Line | None:
    best = mainline.pick_main(cands.get((book, market), []), t)
    if best is None:
        return None
    _, c, i, j = best
    return Line(0.0 if market == "moneyline" else c.handicap, c.side1.prices[i], c.side2.prices[j])


def shin(line: Line) -> float:
    """Fair probability of side 1 (Shin devig)."""
    return fv.devig(1 / line.d1, 1 / line.d2, "shin")


def american(decimal: float) -> int:
    return mainline.to_american(decimal)


def in_band(decimal: float) -> bool:
    a = american(decimal)
    return PRICE_BAND[0] <= a <= PRICE_BAND[1]


def side_win_loss(engine: fv.Engine, market: str, src: Line, side: str, target: float,
                  total_hint: float, spread_hint: float) -> tuple[float, float]:
    """(win, loss) probability for `side` at `target`, from a source line's devigged probability."""
    p1 = shin(src)
    if market == "spreads":
        pmf = engine.margin_pmf(src.point, total_hint)
        line = target if side == "home" else -target
        w, _pu, lo = ml.side_probabilities(pmf, src.point, p1, side, line)
        return w, lo
    if market == "totals":
        pmf = engine.total_pmf(src.point, spread_hint)
        w, _pu, lo = ot.total_side_probabilities(pmf, src.point, p1, side, target)
        return w, lo
    # moneyline from a moneyline source: its own devigged probability (ties excluded)
    return (p1, 1 - p1) if side == "home" else (1 - p1, p1)


def consensus(engine, cands, market: str, side: str, target: float, t: pd.Timestamp,
              total_hint: float, spread_hint: float) -> tuple[float, float] | None:
    probs = []
    for src_book in SHARP:
        src = line_at(cands, src_book, market, t)
        if src is not None:
            probs.append(side_win_loss(engine, market, src, side, target, total_hint, spread_hint))
    if not probs:
        return None
    return sum(p[0] for p in probs) / len(probs), sum(p[1] for p in probs) / len(probs)


def value(win: float, loss: float, decimal: float) -> float:
    return win * (decimal - 1) - loss


def hints(cands, t: pd.Timestamp) -> tuple[float, float]:
    """A total for the margin model (ignored by the adopted model) and a spread for the totals model."""
    tot = line_at(cands, "pinnacle", "totals", t)
    spr = line_at(cands, "pinnacle", "spreads", t)
    return (tot.point if tot else 44.0), (spr.point if spr else 0.0)


def fixture_positions(ladder: pd.DataFrame, kickoff: pd.Timestamp, engine: fv.Engine,
                      horizons=HORIZONS) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(A positions, B positions) for one fixture, each with value at d and at the consensus close."""
    cands = book_candidates(ladder)
    close_t = kickoff - pd.Timedelta(microseconds=1)
    c_tot, c_spr = hints(cands, close_t)
    a_rows, b_rows = [], []
    for h in horizons:
        d = kickoff - pd.Timedelta(hours=h)
        tot_h, spr_h = hints(cands, d)
        for book in RETAIL:
            # A: moneyline against the book's own spread
            spr, mlq = line_at(cands, book, "spreads", d), line_at(cands, book, "moneyline", d)
            if spr is not None and mlq is not None:
                pmf = engine.margin_pmf(spr.point, tot_h)
                w, _pu, lo = ml.side_probabilities(pmf, spr.point, shin(spr), "home", 0.0)
                p_home = w / (w + lo) if w + lo > 0 else 0.5
                for side, dec, p in (("home", mlq.d1, p_home), ("away", mlq.d2, 1 - p_home)):
                    if not in_band(dec) or value(p, 1 - p, dec) <= 0:
                        continue
                    close = consensus(engine, cands, "moneyline", side, 0.0, close_t, c_tot, c_spr)
                    if close is not None:
                        a_rows.append({"h": h, "book": book, "side": side, "price": american(dec),
                                       "spread": spr.point, "value_d": value(p, 1 - p, dec),
                                       "value": value(*close, dec)})
            # B: same-line value against the sharp consensus
            for market, sides in (("spreads", ("home", "away")), ("totals", ("over", "under")),
                                  ("moneyline", ("home", "away"))):
                q = line_at(cands, book, market, d)
                if q is None:
                    continue
                for side in sides:
                    dec = q.d1 if side in ("home", "over") else q.d2
                    if not in_band(dec):
                        continue
                    fair = consensus(engine, cands, market, side, q.point, d, tot_h, spr_h)
                    if fair is None or value(*fair, dec) <= 0:
                        continue
                    close = consensus(engine, cands, market, side, q.point, close_t, c_tot, c_spr)
                    if close is not None:
                        b_rows.append({"h": h, "book": book, "market": market, "side": side, "line": q.point,
                                       "price": american(dec), "value_d": value(*fair, dec),
                                       "value": value(*close, dec)})
    cols_a = ["h", "book", "side", "price", "spread", "value_d", "value"]
    cols_b = ["h", "book", "market", "side", "line", "price", "value_d", "value"]
    return pd.DataFrame(a_rows, columns=cols_a), pd.DataFrame(b_rows, columns=cols_b)


ALT_BAND = (-300, 300)


def alt_positions(ladder: pd.DataFrame, kickoff: pd.Timestamp, engine: fv.Engine,
                  horizons=HORIZONS) -> pd.DataFrame:
    """MS-055b (Addendum Q): retail alternate spreads and totals worth more than the sharp-consensus fair
    probability at their exact line, scored at the consensus close."""
    cands = book_candidates(ladder)
    close_t = kickoff - pd.Timedelta(microseconds=1)
    c_tot, c_spr = hints(cands, close_t)
    rows = []
    for h in horizons:
        d = kickoff - pd.Timedelta(hours=h)
        tot_h, spr_h = hints(cands, d)
        for book in RETAIL:
            for market, sides in (("spreads", ("home", "away")), ("totals", ("over", "under"))):
                main = line_at(cands, book, market, d)
                if main is None:
                    continue
                for c in cands.get((book, market), []):
                    if c.handicap == main.point:
                        continue
                    i, j = c.side1.at(d), c.side2.at(d)
                    if i < 0 or j < 0 or not c.side1.active[i] or not c.side2.active[j]:
                        continue
                    for side, dec in ((sides[0], c.side1.prices[i]), (sides[1], c.side2.prices[j])):
                        a = american(dec)
                        if not ALT_BAND[0] <= a <= ALT_BAND[1]:
                            continue
                        fair = consensus(engine, cands, market, side, c.handicap, d, tot_h, spr_h)
                        if fair is None or value(*fair, dec) <= 0:
                            continue
                        close = consensus(engine, cands, market, side, c.handicap, close_t, c_tot, c_spr)
                        if close is None:
                            continue
                        rows.append({"h": h, "book": book, "market": market, "side": side, "line": c.handicap,
                                     "main": main.point, "distance": abs(c.handicap - main.point),
                                     "key": market == "spreads" and spans_key(main.point, c.handicap),
                                     "price": a, "value_d": value(*fair, dec), "value": value(*close, dec)})
    return pd.DataFrame(rows, columns=["h", "book", "market", "side", "line", "main", "distance", "key", "price",
                                       "value_d", "value"])
