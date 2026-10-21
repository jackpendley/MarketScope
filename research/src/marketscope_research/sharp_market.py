"""MS-043 sharp-market study S1–S5, implementing research/PREREGISTRATION.md Addendum C (committed
before this code, dd570b1). Pure functions over a `line_moves` frame; loading is in run_sharp_market.py.

Conventions (Addendum C):
- A book's line at time d is its latest row with changed_at <= d; a row without prices means off the
  board. Lines are home spreads (or totals); "toward home" means the home line fell.
- The close is Pinnacle's latest available line before kickoff; a game whose Pinnacle line was off
  the board for the final 30 minutes has no close.
- CLV in points uses HOME lines throughout: a home bet at home line L scores L - C, an away bet
  C - L (C = Pinnacle's closing home line). Totals: over C - L, under L - C.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .football_studies import RESAMPLES, SEED, Estimate

REFERENCE = ("pinnacle", "circa", "bookmaker_eu")
RETAIL = ("draftkings", "fanduel", "williamhill_us", "hardrockbet")
DISCOVERY_END = pd.Timestamp("2026-10-21", tz="UTC")
CONFIRMATION_END = pd.Timestamp("2026-12-16", tz="UTC")

MATCH_WINDOW = pd.Timedelta(minutes=60)
SAME_SECOND = pd.Timedelta(seconds=1)
DECISION_DELAY = pd.Timedelta(seconds=60)
CLOSE_OFF_LIMIT = pd.Timedelta(minutes=30)
WORST_PRICE = -125
STEAM_BOOKS, STEAM_WINDOW, STEAM_MERGE = 3, pd.Timedelta(minutes=10), pd.Timedelta(minutes=60)
S1_MIN_PAIRS, S2_MIN_EVENTS, S2_MIN_GAMES, S3_MIN_EPISODES = 200, 100, 30, 50
KEY_NUMBERS = (3.0, 7.0)


# --- timelines ---------------------------------------------------------------------------------

@dataclass(frozen=True)
class Quote:
    point: float
    price1: int
    price2: int
    limit1: float | None


class Book:
    """One book's rows for one game and market, in time order."""

    def __init__(self, rows: pd.DataFrame):
        rows = rows.sort_values("changed_at")
        utc = pd.to_datetime(rows["changed_at"], utc=True)
        self.stamps: list[pd.Timestamp] = list(utc)
        self.times = utc.dt.tz_localize(None).to_numpy("datetime64[ns]")
        self.quotes: list[Quote | None] = [
            None if pd.isna(r.price1) else
            Quote(float(r.point), int(r.price1), int(r.price2), None if pd.isna(r.limit1) else float(r.limit1))
            for r in rows.itertuples()
        ]

    def index_at(self, t: pd.Timestamp) -> int:
        """Index of the row in effect at t (-1 before the first row). Never looks past t."""
        naive = t.tz_convert("UTC").tz_localize(None).to_datetime64()
        return int(np.searchsorted(self.times, naive, side="right")) - 1

    def at(self, t: pd.Timestamp) -> Quote | None:
        i = self.index_at(t)
        return self.quotes[i] if i >= 0 else None

    def changes(self) -> list[tuple[pd.Timestamp, float, float, Quote]]:
        """Line (point) changes against the last available line; suspensions in between don't count."""
        out, last = [], None
        for t, q in zip(self.stamps, self.quotes):
            if q is None:
                continue
            if last is not None and q.point != last:
                out.append((t, last, q.point, q))
            last = q.point
        return out


def timelines(moves: pd.DataFrame) -> dict[str, dict[str, Book]]:
    """event_id -> bookmaker_key -> Book, for one market's rows."""
    return {e: {b: Book(r) for b, r in g.groupby("bookmaker_key")} for e, g in moves.groupby("event_id")}


def close_line(pinnacle: Book | None, kickoff: pd.Timestamp) -> float | None:
    """Pinnacle's latest available line before kickoff, or None if it was off for the final 30 min."""
    if pinnacle is None:
        return None
    before = kickoff - pd.Timedelta(microseconds=1)
    i = pinnacle.index_at(before)
    if i < 0:
        return None
    if pinnacle.quotes[i] is not None:
        return pinnacle.quotes[i].point
    off_since = pinnacle.stamps[i]
    if kickoff - off_since >= CLOSE_OFF_LIMIT:
        return None
    for q in reversed(pinnacle.quotes[:i]):
        if q is not None:
            return q.point
    return None


def clv(side: str, line: float, close: float) -> float:
    """Points of CLV for a bet at `line` (home line or total) against the closing line."""
    return {"home": line - close, "away": close - line, "over": close - line, "under": line - close}[side]


def price_ok(price: int) -> bool:
    return price >= WORST_PRICE


def crosses_key(a: float, b: float) -> bool:
    """The move crosses or lands on 3 or 7 (in absolute value)."""
    lo, hi = sorted((abs(a), abs(b)))
    return any(lo < k < hi or abs(b) == k for k in KEY_NUMBERS)


# --- inference ----------------------------------------------------------------------------------

def ratio_bootstrap(df: pd.DataFrame, num: str, den: str | None = None,
                    resamples: int = RESAMPLES) -> Estimate:
    """sum(num) / sum(den) (den None = row count, i.e. a mean or share) with a 95% interval from
    resampling games (event_id) with replacement, 5,000 draws, seed 2026."""
    g = df.assign(_den=1.0 if den is None else df[den]).groupby("event_id")[[num, "_den"]].sum()
    n, d = g[num].to_numpy(float), g["_den"].to_numpy(float)
    rng = np.random.default_rng(SEED)
    idx = rng.integers(0, len(g), (resamples, len(g)))
    boots = n[idx].sum(axis=1) / d[idx].sum(axis=1)
    lo, hi = np.nanquantile(boots, [0.025, 0.975])
    return Estimate(float(n.sum() / d.sum()), float(lo), float(hi), len(df))


# --- S1: lead-lag ------------------------------------------------------------------------------

def match_pairs(ref: list, retail: list) -> list[tuple]:
    """One-to-one matching of identical changes (a -> b) within 60 min, nearest first (ties: earlier)."""
    cands = []
    for i, (tr, a, b, _) in enumerate(ref):
        for j, (tk, a2, b2, _) in enumerate(retail):
            if a == a2 and b == b2 and abs(tk - tr) <= MATCH_WINDOW:
                cands.append((abs(tk - tr), min(tr, tk), i, j))
    cands.sort(key=lambda c: (c[0], c[1]))
    used_i, used_j, out = set(), set(), []
    for _, _, i, j in cands:
        if i in used_i or j in used_j:
            continue
        used_i.add(i)
        used_j.add(j)
        out.append((ref[i], retail[j]))
    return out


def s1_pairs(tl: dict[str, dict[str, Book]], kickoffs: pd.Series) -> pd.DataFrame:
    rows = []
    for event, books in tl.items():
        for r in REFERENCE:
            if r not in books:
                continue
            rc = books[r].changes()
            for k in RETAIL:
                if k not in books:
                    continue
                for (tr, a, b, q), (tk, *_rest) in match_pairs(rc, books[k].changes()):
                    gap = tk - tr
                    lead = "tie" if abs(gap) < SAME_SECOND else ("ref" if gap > pd.Timedelta(0) else "retail")
                    rows.append({"event_id": event, "ref": r, "retail": k, "lead": lead,
                                 "lag_min": gap / pd.Timedelta(minutes=1), "a": a, "b": b,
                                 "hours_out": (kickoffs[event] - min(tr, tk)) / pd.Timedelta(hours=1)})
    return pd.DataFrame(rows, columns=["event_id", "ref", "retail", "lead", "lag_min", "a", "b", "hours_out"])


def ref_first_share(pairs: pd.DataFrame) -> float:
    decided = pairs[pairs["lead"] != "tie"]
    return float((decided["lead"] == "ref").mean()) if len(decided) else float("nan")


def s1(pairs: pd.DataFrame, resamples: int = RESAMPLES) -> dict:
    out = {}
    for r in REFERENCE:
        p = pairs[pairs["ref"] == r]
        decided = p[p["lead"] != "tie"].assign(first=lambda d: (d["lead"] == "ref").astype(float))
        out[r] = {"pairs": len(decided), "ties": int((p["lead"] == "tie").sum()),
                  "share": ratio_bootstrap(decided, "first", resamples=resamples) if len(decided) else None}
    pin = pairs[pairs["ref"] == "pinnacle"]
    out["gate"] = out["pinnacle"]["pairs"] >= S1_MIN_PAIRS
    out["by_hours"] = {
        label: ref_first_share(pin[(pin["hours_out"] > lo) & (pin["hours_out"] <= hi)])
        for label, lo, hi in (("> 48 h", 48, np.inf), ("6–48 h", 6, 48), ("< 6 h", 0, 6))
    }
    size = (pin["b"] - pin["a"]).abs()
    out["by_size"] = {"0.5": ref_first_share(pin[size == 0.5]), "≥ 1": ref_first_share(pin[size >= 1])}
    return out


def follow_times(tl: dict[str, dict[str, Book]], kickoffs: pd.Series) -> pd.DataFrame:
    """After each Pinnacle change a -> b: for each retail book at a, minutes until it posts b."""
    rows = []
    for event, books in tl.items():
        if "pinnacle" not in books:
            continue
        kick = kickoffs[event]
        for t, a, b, _ in books["pinnacle"].changes():
            for k in RETAIL:
                if k not in books:
                    continue
                q = books[k].at(t)
                if q is None or q.point != a:
                    continue
                later = [tc for tc, _a, b2, _q in books[k].changes() if tc > t and b2 == b and tc < kick]
                rows.append({"event_id": event, "retail": k, "key": crosses_key(a, b),
                             "minutes": (later[0] - t) / pd.Timedelta(minutes=1) if later else np.nan})
    return pd.DataFrame(rows, columns=["event_id", "retail", "key", "minutes"])


# --- S2: stale retail lines --------------------------------------------------------------------

def s2_events(tl: dict[str, dict[str, Book]], kickoffs: pd.Series, closes: dict[str, float],
              delay: pd.Timedelta = DECISION_DELAY, market: str = "spreads") -> pd.DataFrame:
    rows = []
    for event, books in tl.items():
        if "pinnacle" not in books or event not in closes:
            continue
        kick, close = kickoffs[event], closes[event]
        for t, a, b, _ in books["pinnacle"].changes():
            if t >= kick - DECISION_DELAY:
                continue
            d = t + delay
            if market == "totals":
                side, use = ("over", "price1") if b > a else ("under", "price2")
            else:
                side, use = ("home", "price1") if b < a else ("away", "price2")
            for k in RETAIL:
                if k not in books:
                    continue
                q = books[k].at(d)
                if q is None or q.point != a or not price_ok(getattr(q, use)):
                    continue
                stale_until = next((tc for tc, qq in zip(books[k].stamps, books[k].quotes)
                                    if tc > d and (qq is None or qq.point != a)), kick)
                end = min(stale_until, kick)
                rows.append({"event_id": event, "retail": k, "side": side, "line": a, "pin_to": b, "pin_t": t,
                             "price": getattr(q, use), "clv": clv(side, a, close),
                             "key": crosses_key(a, b), "stale_min": (end - d) / pd.Timedelta(minutes=1)})
    return pd.DataFrame(rows, columns=["event_id", "retail", "side", "line", "pin_to", "pin_t", "price", "clv",
                                       "key", "stale_min"])


def s2(events: pd.DataFrame, resamples: int = RESAMPLES) -> dict:
    return {"events": len(events), "games": events["event_id"].nunique(),
            "gate": len(events) >= S2_MIN_EVENTS and events["event_id"].nunique() >= S2_MIN_GAMES,
            "clv": ratio_bootstrap(events, "clv", resamples=resamples) if len(events) else None}


def implied(price: int) -> float:
    return -price / (-price + 100) if price < 0 else 100 / (price + 100)


def hypothetical_cover(events: pd.DataFrame, margins: pd.Series) -> dict:
    """Cover rate of S2 bets against the actual margin (home - away), pushes excluded. Hypothetical."""
    e = events[events["event_id"].isin(margins.index)].copy()
    m = e["event_id"].map(margins)
    result = np.where(e["side"] == "home", m + e["line"], -(m + e["line"]))
    decided = result != 0
    return {"bets": int(decided.sum()), "cover_rate": float((result[decided] > 0).mean()) if decided.any() else np.nan,
            "break_even": float(e.loc[decided, "price"].map(implied).mean()) if decided.any() else np.nan}


def s2b_edges(events: pd.DataFrame, margins: pd.Series) -> pd.DataFrame:
    """Addendum D: S2 events at -110 or better, each decided bet's (cover - break-even). Hypothetical."""
    e = events[(events["price"] >= -110) & events["event_id"].isin(margins.index)].copy()
    m = e["event_id"].map(margins)
    result = np.where(e["side"] == "home", m + e["line"], -(m + e["line"]))
    e = e[result != 0].assign(edge=(result[result != 0] > 0).astype(float) - e.loc[result != 0, "price"].map(implied))
    return e


def s2b(events: pd.DataFrame, margins: pd.Series, resamples: int = RESAMPLES) -> dict:
    std = events[events["price"] >= -110]
    edges = s2b_edges(events, margins)
    return {"events": len(std),
            "clv": ratio_bootstrap(std, "clv", resamples=resamples) if len(std) else None,
            "edge": ratio_bootstrap(edges, "edge", resamples=resamples) if len(edges) else None}


# --- S3: steam ---------------------------------------------------------------------------------

def steam_episodes(tl: dict[str, dict[str, Book]], kickoffs: pd.Series) -> pd.DataFrame:
    rows = []
    for event, books in tl.items():
        changes = sorted((t, k, -1 if b < a else 1) for k, bk in books.items() for t, a, b, _ in bk.changes())
        last = {}
        for i, (t, _k, direction) in enumerate(changes):
            if t >= kickoffs[event]:
                continue
            window = [(tt, kk) for tt, kk, dd in changes[: i + 1] if dd == direction and tt > t - STEAM_WINDOW]
            movers = list(dict.fromkeys(kk for _tt, kk in sorted(window)))
            if len(movers) < STEAM_BOOKS:
                continue
            if direction in last and t - last[direction] < STEAM_MERGE:
                continue
            last[direction] = t
            rows.append({"event_id": event, "t": t, "toward": "home" if direction < 0 else "away",
                         "first_three": movers[:STEAM_BOOKS], "movers": movers})
    return pd.DataFrame(rows, columns=["event_id", "t", "toward", "first_three", "movers"])


def s3_outcomes(episodes: pd.DataFrame, tl: dict[str, dict[str, Book]], closes: dict[str, float],
                market: str = "spreads") -> pd.DataFrame:
    rows = []
    for e in episodes.itertuples():
        books = tl[e.event_id]
        if e.event_id not in closes or "pinnacle" not in books:
            continue
        d = e.t + DECISION_DELAY
        q = books["pinnacle"].at(d)
        if q is None:
            continue
        close = closes[e.event_id]
        if market == "totals":
            side = "over" if e.toward == "away" else "under"  # a rising line = toward the over
        else:
            side = e.toward
        continuation = clv(side, q.point, close)
        # Exploratory: the best line among retail books that had not moved in the episode window.
        best = None
        for k in RETAIL:
            if k not in books or k in e.movers:
                continue
            rq = books[k].at(d)
            use = "price1" if side in ("home", "over") else "price2"
            if rq is None or not price_ok(getattr(rq, use)):
                continue
            v = clv(side, rq.point, close)
            best = v if best is None else max(best, v)
        rows.append({"event_id": e.event_id, "continuation": continuation, "retail_clv": best,
                     "reference_in_first_three": any(b in REFERENCE for b in e.first_three)})
    return pd.DataFrame(rows, columns=["event_id", "continuation", "retail_clv", "reference_in_first_three"])


def s3(outcomes: pd.DataFrame, resamples: int = RESAMPLES) -> dict:
    return {"episodes": len(outcomes), "gate": len(outcomes) >= S3_MIN_EPISODES,
            "continuation": ratio_bootstrap(outcomes, "continuation", resamples=resamples)
            if len(outcomes) else None}


# --- S4 / S5: limits and key numbers (exploratory) ---------------------------------------------

def pinnacle_changes(tl: dict[str, dict[str, Book]], closes: dict[str, float]) -> pd.DataFrame:
    rows = []
    for event, books in tl.items():
        if "pinnacle" not in books or event not in closes:
            continue
        pin = books["pinnacle"]
        limits = [q.limit1 for q in pin.quotes if q is not None and q.limit1 is not None]
        median = float(np.median(limits)) if limits else np.nan
        close = closes[event]
        for t, a, b, q in pin.changes():
            reversed_ = close >= a if b < a else close <= a
            rows.append({"event_id": event, "a": a, "b": b, "key": crosses_key(a, b),
                         "high_limit": (q.limit1 or 0) > median if limits else None, "reversed": reversed_})
    return pd.DataFrame(rows, columns=["event_id", "a", "b", "key", "high_limit", "reversed"])
