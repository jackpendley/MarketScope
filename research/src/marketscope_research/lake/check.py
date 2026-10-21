"""Cross-check: main lines derived from the lake must reproduce `line_moves` (ADR-052) for every game
and book. Compared as the line in effect (point and both prices, or off the board) on a 15-minute grid
over the 14 days before kickoff, so tiny differences in when a burst settles don't count as misses."""

from __future__ import annotations

import pandas as pd

from ..data import _frame, connect as db_connect
from . import mainline, store

BOOK_KEYS = {"pinnacle": "pinnacle", "circasports": "circa", "bookmaker.eu": "bookmaker_eu",
             "draftkings": "draftkings", "fanduel": "fanduel", "caesars": "williamhill_us",
             "hardrockbet": "hardrockbet", "novig.us": "novig", "prophetx": "prophetx", "kalshi": "kalshi"}
GRID = pd.Timedelta(minutes=15)


def state_at(rows: pd.DataFrame, t: pd.Timestamp):
    r = rows[rows["changed_at"] <= t]
    if r.empty:
        return None
    last = r.iloc[-1]
    if pd.isna(last["price1"]):
        return "off"
    point = None if pd.isna(last["point"]) else float(last["point"])
    return (point, int(last["price1"]), int(last["price2"]))


def compare(lake_rows: pd.DataFrame, db_rows: pd.DataFrame, kickoff: pd.Timestamp) -> tuple[int, int]:
    """(matched, compared) grid points where both sources have a state."""
    matched = compared = 0
    start = kickoff - pd.Timedelta(days=14)
    t = start
    while t < kickoff - pd.Timedelta(minutes=1):
        a, b = state_at(lake_rows, t), state_at(db_rows, t)
        if a is not None and b is not None:
            compared += 1
            matched += a == b
        t += GRID
    return matched, compared


def report(dsn: str) -> str:
    con = store.connect()
    manifest = con.execute("SELECT * FROM manifest WHERE event_id IS NOT NULL").df()
    with db_connect(dsn) as conn:
        db = _frame(conn, """
            SELECT event_id::text, bookmaker_key, market_type AS market, changed_at, point::float8 AS point,
                   price1, price2 FROM line_moves WHERE event_id = ANY(%s::uuid[])""",
                    (list(manifest["event_id"]),))
    db["changed_at"] = pd.to_datetime(db["changed_at"], utc=True)
    totals: dict[str, list[int]] = {}
    for f in manifest.itertuples():
        kick = pd.Timestamp(f.kickoff)
        ladder = con.execute("SELECT * FROM ladder WHERE fixture_id = ?", [f.fixture_id]).df()
        ladder["created_at"] = pd.to_datetime(ladder["created_at"], utc=True)
        for slug, key in BOOK_KEYS.items():
            book_db = db[(db["event_id"] == f.event_id) & (db["bookmaker_key"] == key)]
            if book_db.empty:
                continue
            derived = mainline.derive(ladder[ladder["book"] == slug], kick)
            for market, d in book_db.groupby("market"):
                lm = derived[derived["market"] == market].sort_values("changed_at")
                m, c = compare(lm, d.sort_values("changed_at"), kick)
                agg = totals.setdefault(key, [0, 0])
                agg[0] += m
                agg[1] += c
    lines = ["Lake vs line_moves (15-minute grid, line in effect):", ""]
    for key, (m, c) in sorted(totals.items()):
        lines.append(f"  {key:<16} {m}/{c} = {m / c:.2%}" if c else f"  {key:<16} no overlap")
    return "\n".join(lines)
