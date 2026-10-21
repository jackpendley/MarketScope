"""MS-051: exchanges, price-aware with fees (research/PREREGISTRATION.md Addendum K, committed before
this code). Pure functions; loading and reporting live in run_exchanges.py.
"""

from __future__ import annotations

import pandas as pd

from . import market_ml as ml
from . import openers_totals as ot
from . import sharp_market as sm
from .backtest import profit

EXCHANGES = ("novig", "prophetx", "kalshi")
MIN_SIZE = 100.0
PROPHETX_FEE = 0.02
KALSHI_RATE = 0.07


def win_profit(book: str, price: int, prophetx_fee: float = PROPHETX_FEE) -> float:
    """Profit per unit staked on a win, after fees; a loss costs 1 unit (Addendum K)."""
    d = 1 + profit(price)
    if book == "prophetx":
        return (d - 1) * (1 - prophetx_fee)
    if book == "kalshi":
        p = 1 / d
        cost = p + KALSHI_RATE * p * (1 - p)
        return (1 - cost) / cost
    return d - 1  # novig: no pregame fee


def position_value(books: dict[str, sm.Book], kickoff: pd.Timestamp, market: str, side: str, line: float,
                   price: int, exchange: str, spread_tables, total_tables,
                   prophetx_fee: float = PROPHETX_FEE) -> float | None:
    """Expected profit per unit at Pinnacle's no-vig close, after the exchange's fee."""
    cq = ml.close_quote(books["pinnacle"], kickoff) if "pinnacle" in books else None
    if cq is None:
        return None
    p_nv = ml.no_vig_home(cq.price1, cq.price2)
    if market == "totals":
        w, _pu, lo = ot.total_side_probabilities(total_tables[ot.total_bucket(cq.point)], cq.point, p_nv, side, line)
    else:
        w, _pu, lo = ml.side_probabilities(spread_tables[ml.bucket_of(cq.point)], cq.point, p_nv, side, line)
    return w * win_profit(exchange, price, prophetx_fee) - lo


def stale_exchange_cases(tl: dict[str, dict[str, sm.Book]], kickoffs: pd.Series, market: str,
                         min_size: float = MIN_SIZE) -> pd.DataFrame:
    """Addendum C's S2 rule with an exchange as the lagging book, plus the size floor (K1)."""
    closes = {e: x for e, b in tl.items() if (x := sm.close_line(b.get("pinnacle"), kickoffs[e])) is not None}
    cases = sm.s2_events(tl, kickoffs, closes, market=market, books=EXCHANGES, min_size=min_size)
    return cases.assign(market=market)


def horizon_exchange_positions(tl: dict[str, dict[str, sm.Book]], kickoffs: pd.Series, market: str,
                               horizons=ml.HORIZONS, min_size: float = MIN_SIZE) -> pd.DataFrame:
    """K2: exchange sides whose line beats Pinnacle's at each horizon, at -125 or better."""
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
            for x in EXCHANGES:
                q = books[x].at(d) if x in books else None
                if q is None:
                    continue
                if market == "totals":
                    sides = (("over", q.point < pq.point, q.price1, q.limit1),
                             ("under", q.point > pq.point, q.price2, q.limit2))
                else:
                    sides = (("home", q.point > pq.point, q.price1, q.limit1),
                             ("away", -q.point > -pq.point, q.price2, q.limit2))
                for side, better, price, size in sides:
                    if better and sm.price_ok(price) and size is not None and size >= min_size:
                        line = q.point if side in ("home", "over", "under") else -q.point
                        rows.append({"event_id": event, "exchange": x, "market": market, "h": h, "side": side,
                                     "line": line, "price": price, "size": size})
    return pd.DataFrame(rows, columns=["event_id", "exchange", "market", "h", "side", "line", "price", "size"])


def add_values(df: pd.DataFrame, tl, kickoffs: pd.Series, spread_tables, total_tables, book_col: str,
               prophetx_fee: float = PROPHETX_FEE) -> pd.Series:
    """Value per row. Spread lines are from the side (S2 cases store the home line: converted here)."""
    out = []
    for r in df.itertuples():
        line = r.line
        if r.market == "spreads" and r.side == "away" and book_col == "retail":
            line = -r.line  # S2 cases carry the home line
        out.append(position_value(tl[r.event_id], kickoffs[r.event_id], r.market, r.side, line, r.price,
                                  getattr(r, book_col), spread_tables, total_tables, prophetx_fee))
    return pd.Series(out, index=df.index, dtype=float)
