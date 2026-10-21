"""MS-050: openers and totals, price-aware (research/PREREGISTRATION.md Addendum J, committed before
this code). Pure functions; loading and reporting live in run_openers_totals.py.

Value is expected profit per unit at Pinnacle's no-vig close (Addendum G). Spreads use
market_ml's margin model; totals use the total-points model below, built the same way.
"""

from __future__ import annotations

import pandas as pd

from . import market_ml as ml
from . import sharp_market as sm


# --- totals value model -----------------------------------------------------------------------

def total_bucket(total: float) -> int:
    return 0 if total <= 40.5 else 1 if total <= 44.5 else 2 if total <= 48.5 else 3


def total_tables(history: pd.DataFrame) -> list[pd.Series]:
    """Per closing-total bucket, P(total points = k) from final games (columns total, points)."""
    b = history["total"].map(total_bucket)
    return [history.loc[b == i, "points"].value_counts(normalize=True).sort_index() for i in range(4)]


def total_side_probabilities(table: pd.Series, close_total: float, p_over_nv: float, side: str,
                             line: float) -> tuple[float, float, float]:
    """(win, push, loss) for 'over'/'under' at `line`, calibrated so the no-push over probability at
    Pinnacle's closing total equals its no-vig over probability."""
    k, pk = table.index.to_numpy(float), table.to_numpy(float)

    def over(x: float) -> tuple[float, float]:
        return float(pk[k > x].sum()), float(pk[k == x].sum())

    w_c, pu_c = over(close_total)
    delta = p_over_nv - (w_c / (1 - pu_c) if pu_c < 1 else 0.5)
    w, pu = over(line)
    w = min(max(w + delta * (1 - pu), 0.0), 1 - pu)
    return (w, pu, 1 - w - pu) if side == "over" else (1 - w - pu, pu, w)


def total_value(books: dict[str, sm.Book], kickoff: pd.Timestamp, tables: list[pd.Series], side: str,
                line: float, price: int) -> float | None:
    cq = ml.close_quote(books["pinnacle"], kickoff) if "pinnacle" in books else None
    if cq is None:
        return None
    w, _pu, lo = total_side_probabilities(tables[total_bucket(cq.point)], cq.point,
                                          ml.no_vig_home(cq.price1, cq.price2), side, line)
    return ml.expected_value(w, lo, price)


def spread_value(books: dict[str, sm.Book], kickoff: pd.Timestamp, tables: list[pd.Series], side: str,
                 line: float, price: int) -> float | None:
    cq = ml.close_quote(books["pinnacle"], kickoff) if "pinnacle" in books else None
    if cq is None:
        return None
    w, _pu, lo = ml.side_probabilities(tables[ml.bucket_of(cq.point)], cq.point,
                                       ml.no_vig_home(cq.price1, cq.price2), side, line)
    return ml.expected_value(w, lo, price)


# --- J1: openers --------------------------------------------------------------------------------

def opener_positions(tl: dict[str, dict[str, sm.Book]], kickoffs: pd.Series, tables: list[pd.Series]) -> pd.DataFrame:
    """Each retail book's first available spread row; a position on each side whose line beats
    Pinnacle's line at that moment, at -125 or better. Value at Pinnacle's no-vig close."""
    rows = []
    for event, books in tl.items():
        pin = books.get("pinnacle")
        if pin is None or event not in kickoffs.index:
            continue
        kick = kickoffs[event]
        for k in sm.RETAIL:
            b = books.get(k)
            if b is None:
                continue
            first = next(((t, q) for t, q in zip(b.stamps, b.quotes) if q is not None and t < kick), None)
            if first is None:
                continue
            t0, q0 = first
            pq = pin.at(t0)
            if pq is None:
                continue
            for side, line, pin_line, price in (("home", q0.point, pq.point, q0.price1),
                                                ("away", -q0.point, -pq.point, q0.price2)):
                if line <= pin_line or not sm.price_ok(price):
                    continue
                v = spread_value(books, kick, tables, side, line, price)
                if v is not None:
                    rows.append({"event_id": event, "book": k, "side": side, "t0": t0, "line": line,
                                 "pin_line": pin_line, "price": price,
                                 "hours_out": (kick - t0) / pd.Timedelta(hours=1), "value": v})
    return pd.DataFrame(rows, columns=["event_id", "book", "side", "t0", "line", "pin_line", "price",
                                       "hours_out", "value"])


# --- J3: totals at fixed horizons ---------------------------------------------------------------

def horizon_totals(tl: dict[str, dict[str, sm.Book]], kickoffs: pd.Series, tables: list[pd.Series],
                   horizons=ml.HORIZONS) -> pd.DataFrame:
    """At each horizon, retail totals better than Pinnacle's for the over (lower) or the under
    (higher), at -125 or better."""
    rows = []
    for event, books in tl.items():
        pin = books.get("pinnacle")
        if pin is None or event not in kickoffs.index:
            continue
        kick = kickoffs[event]
        for h in horizons:
            d = kick - pd.Timedelta(hours=h)
            pq = pin.at(d)
            if pq is None:
                continue
            for k in sm.RETAIL:
                q = books[k].at(d) if k in books else None
                if q is None:
                    continue
                for side, better, price in (("over", q.point < pq.point, q.price1),
                                            ("under", q.point > pq.point, q.price2)):
                    if not better or not sm.price_ok(price):
                        continue
                    v = total_value(books, kick, tables, side, q.point, price)
                    if v is not None:
                        rows.append({"event_id": event, "h": h, "book": k, "side": side, "line": q.point,
                                     "pin_line": pq.point, "price": price, "value": v})
    return pd.DataFrame(rows, columns=["event_id", "h", "book", "side", "line", "pin_line", "price", "value"])


def stale_total_values(cases: pd.DataFrame, tl: dict[str, dict[str, sm.Book]], kickoffs: pd.Series,
                       tables: list[pd.Series]) -> pd.Series:
    """Totals value of S2 totals cases (side over/under, line = the old total, price)."""
    return pd.Series([total_value(tl[c.event_id], kickoffs[c.event_id], tables, c.side, c.line, c.price)
                      for c in cases.itertuples()], index=cases.index, dtype=float)


