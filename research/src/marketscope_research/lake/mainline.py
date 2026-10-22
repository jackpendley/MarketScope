"""Main-line derivation from lake ladders: a Python port of apps/collector's line-moves.ts
(pickMain + the settle, suspension and window rules, ADR-052), so the lake can be cross-checked
against `line_moves` and studies can ask "what was this book's main line at time t?".

The main line at t is the market whose two sides are both active and priced closest to even (ties
go to the smaller |handicap|). Prices are converted with JavaScript's rounding (half up) to match
the TypeScript exactly.
"""

from __future__ import annotations

import math
from bisect import bisect_right
from dataclasses import dataclass

import pandas as pd

MARKET_OF = {"spreads": "spreads", "totals": "totals", "moneyline": "h2h"}
SIDE1 = {"spreads": "1", "totals": "Over", "moneyline": "1"}
SIDE2 = {"spreads": "2", "totals": "Under", "moneyline": "2"}


def js_round(x: float) -> int:
    return math.floor(x + 0.5)


def to_american(decimal: float) -> int:
    return js_round((decimal - 1) * 100) if decimal >= 2 else js_round(-100 / (decimal - 1))


def cents(american: int) -> int:
    return american + 100 if american < 0 else american - 100


@dataclass
class Series:
    times: list[pd.Timestamp]
    prices: list[float]
    active: list[bool]
    limits: list[float | None]

    def at(self, t: pd.Timestamp) -> int:
        """Index of the entry in effect at t (-1 before the first)."""
        return bisect_right(self.times, t) - 1


@dataclass
class Candidate:
    handicap: float
    side1: Series
    side2: Series


def candidates(rows: pd.DataFrame, market_type: str) -> list[Candidate]:
    """One book's markets of one type (ladder rows: market_id, handicap, outcome_name, created_at,
    price, active, limit), each with both sides present."""
    out = []
    for _, g in rows[rows["market_type"] == market_type].groupby("market_id"):
        sides = []
        for name in (SIDE1[market_type], SIDE2[market_type]):
            s = g[(g["outcome_name"] == name) & (g["price"] > 1)].sort_values("created_at")
            sides.append(Series(list(s["created_at"]), list(s["price"]), list(s["active"]), list(s["limit"])))
        if sides[0].times and sides[1].times:
            out.append(Candidate(float(g["handicap"].iloc[0]), sides[0], sides[1]))
    return out


def pick_main(cands: list[Candidate], t: pd.Timestamp):
    best = None
    for c in cands:
        i, j = c.side1.at(t), c.side2.at(t)
        if i < 0 or j < 0 or not c.side1.active[i] or not c.side2.active[j]:
            continue
        gap = abs(cents(to_american(c.side1.prices[i])) - cents(to_american(c.side2.prices[j])))
        if best is None or gap < best[0] or (gap == best[0] and abs(c.handicap) < abs(best[1].handicap)):
            best = (gap, c, i, j)
    return best


def coherent(cands: list[Candidate], t: pd.Timestamp, market_type: str) -> list[Candidate]:
    """Drop ghost markets (Addendum R): markets the feed still shows as active after the book stopped
    updating them. Freshest first, a market is kept only if its no-vig price is monotone with every
    market already kept: P(home covers) rises with the home handicap; P(over) falls with the total.
    Ties are allowed. For sportsbooks only; an exchange's resting orders could be traded."""
    if market_type == "moneyline":
        return cands
    sign = 1 if market_type == "spreads" else -1
    live = []
    for c in cands:
        i, j = c.side1.at(t), c.side2.at(t)
        if i < 0 or j < 0 or not c.side1.active[i] or not c.side2.active[j]:
            continue
        q1, q2 = 1 / c.side1.prices[i], 1 / c.side2.prices[j]
        live.append((max(c.side1.times[i], c.side2.times[j]), q1 / (q1 + q2), c))
    live.sort(key=lambda x: x[0], reverse=True)
    kept: list[tuple[float, Candidate]] = []
    for _, p, c in live:
        if all(sign * (c.handicap - kc.handicap) * (p - kp) >= 0 for kp, kc in kept):
            kept.append((p, c))
    return [c for _, c in kept]


GHOST_NEAR_EVEN, GHOST_MAX_OVERROUND, GHOST_MIN_GAP, GHOST_MIN_SLOPE = 0.3, 1.12, 2, 0.005


def without_ghosts(cands: list[Candidate], t: pd.Timestamp) -> list[Candidate]:
    """The collector's ghost rule (MS-058, ADR-065; transform.ts withoutGhosts): a main line is near
    even with a normal margin, and of two near-even lines at least 2 points apart whose probabilities
    differ by less than 0.005 per point, the one updated less recently is a ghost."""
    live = []
    for c in cands:
        i, j = c.side1.at(t), c.side2.at(t)
        if i < 0 or j < 0 or not c.side1.active[i] or not c.side2.active[j]:
            continue
        over = 1 / c.side1.prices[i] + 1 / c.side2.prices[j]
        p = 1 / c.side1.prices[i] / over
        if over > GHOST_MAX_OVERROUND or not GHOST_NEAR_EVEN <= p <= 1 - GHOST_NEAR_EVEN:
            continue
        live.append((c, p, max(c.side1.times[i], c.side2.times[j])))
    return [c for c, p, last in live
            if not any(abs(c2.handicap - c.handicap) >= GHOST_MIN_GAP
                       and abs(p2 - p) / abs(c2.handicap - c.handicap) < GHOST_MIN_SLOPE and last < l2
                       for c2, p2, l2 in live)]


def timeline(cands: list[Candidate], market: str, kickoff: pd.Timestamp, keep_limits: bool,
             window_days: float = 14, settle_ms: int = 1000, min_suspension_ms: int = 60_000,
             ghost_rule: bool = False) -> list[dict]:
    times = sorted({t for c in cands for t in c.side1.times + c.side2.times if t < kickoff})
    rows, last_key, off_since = [], None, None
    settle, min_off = pd.Timedelta(milliseconds=settle_ms), pd.Timedelta(milliseconds=min_suspension_ms)

    def suspend(at):
        nonlocal last_key
        if last_key is None or last_key == "off":
            return
        rows.append({"market": market, "changed_at": at, "point": None, "price1": None, "price2": None,
                     "limit1": None, "limit2": None})
        last_key = "off"

    for k, t in enumerate(times):
        if k + 1 < len(times) and times[k + 1] - t < settle:
            continue
        best = pick_main(without_ghosts(cands, t) if ghost_rule and market != "h2h" else cands, t)
        if best is None:
            off_since = off_since or t
            continue
        if off_since is not None and t - off_since >= min_off:
            suspend(off_since)
        off_since = None
        _, c, i, j = best
        l1 = c.side1.limits[i] if keep_limits else None
        l2 = c.side2.limits[j] if keep_limits else None
        row = {"market": market, "changed_at": t, "point": None if market == "h2h" else c.handicap,
               "price1": to_american(c.side1.prices[i]), "price2": to_american(c.side2.prices[j]),
               "limit1": None if l1 is None or pd.isna(l1) else js_round(l1),
               "limit2": None if l2 is None or pd.isna(l2) else js_round(l2)}
        key = (row["point"], row["price1"], row["price2"], row["limit1"], row["limit2"])
        if key != last_key:
            rows.append(row)
            last_key = key
    if off_since is not None and kickoff - off_since >= min_off:
        suspend(off_since)
    start = kickoff - pd.Timedelta(days=window_days)
    first = next((n for n, r in enumerate(rows) if r["changed_at"] >= start), None)
    return rows[-1:] if first is None else rows[max(0, first - 1):]


def derive(book_rows: pd.DataFrame, kickoff: pd.Timestamp, keep_limits: bool = False,
           ghost_rule: bool = False) -> pd.DataFrame:
    """All three markets for one book's ladder rows."""
    out = []
    for mt, market in MARKET_OF.items():
        out += timeline(candidates(book_rows, mt), market, kickoff, keep_limits, ghost_rule=ghost_rule)
    return pd.DataFrame(out, columns=["market", "changed_at", "point", "price1", "price2", "limit1", "limit2"])
