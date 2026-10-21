"""Stream-parse an OddsPapi historical-odds response file into ladder entries (no size limit).

Path inside the JSON: bookmakers.<book>.markets.<market>.outcomes.<outcome>.players.0[*]. Book slugs
can contain dots (bookmaker.eu, novig.us), so the path is split on the fixed keys, not on dots.
Only full-game spread, total and moneyline markets are kept, only entries before kickoff, and only
entries whose price or active flag changed for that outcome (lossless for prices). For `limit_books`
(the market makers, whose limits mean something) a limit change is kept too.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import BinaryIO

import ijson

ITEM = ".players.0.item"


@dataclass(frozen=True)
class Entry:
    book: str
    market_id: int
    outcome_id: int
    created_at: str
    price: float
    active: bool
    limit: float | None


def split_path(prefix: str) -> tuple[str, str, str]:
    """(book, market id, outcome id) from 'bookmakers.<b>.markets.<m>.outcomes.<o>.players.0.item'."""
    rest = prefix[len("bookmakers."):]
    book, tail = rest.split(".markets.", 1)
    market, tail = tail.split(".outcomes.", 1)
    outcome = tail.split(".players.", 1)[0]
    return book, market, outcome


LIMIT_BOOKS = frozenset({"pinnacle", "circasports", "bookmaker.eu"})


def stream_entries(fh: BinaryIO, main_markets: set[int], kickoff: str,
                   limit_books: frozenset[str] = LIMIT_BOOKS) -> Iterator[Entry]:
    """Yield kept entries in file order. `kickoff` is an ISO string; entries at or after it are
    in-play and dropped (ISO strings in the same format compare correctly as text)."""
    last: dict[tuple[str, int, int], tuple] = {}
    cur: dict = {}
    key: tuple[str, int, int] | None = None
    for prefix, event, value in ijson.parse(fh, use_float=True):
        if event == "start_map" and prefix.endswith(ITEM):
            book, market, outcome = split_path(prefix)
            key = (book, int(market), int(outcome)) if int(market) in main_markets else None
            cur = {}
        elif key is None:
            continue
        elif event == "end_map" and prefix.endswith(ITEM):
            created = cur.get("createdAt")
            price = cur.get("price")
            if created is None or price is None or created >= kickoff:
                continue
            state = (price, bool(cur.get("active", True)),
                     cur.get("limit") if key[0] in limit_books else None)
            if last.get(key) == state:
                continue
            last[key] = state
            yield Entry(key[0], key[1], key[2], created, float(price), state[1],
                        None if cur.get("limit") is None else float(cur["limit"]))
        elif prefix.startswith("bookmakers.") and prefix.endswith(ITEM + ".createdAt"):
            cur["createdAt"] = value
        elif prefix.endswith(ITEM + ".price"):
            cur["price"] = value
        elif prefix.endswith(ITEM + ".active"):
            cur["active"] = value
        elif prefix.endswith(ITEM + ".limit"):
            cur["limit"] = value
