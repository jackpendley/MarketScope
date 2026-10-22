"""Stream-parse an OddsPapi historical-odds response file into ladder entries (no size limit).

Path inside the JSON: bookmakers.<book>.markets.<market>.outcomes.<outcome>.players.0[*]. Book slugs
can contain dots (bookmaker.eu, novig.us), so the path is split on the fixed keys, not on dots.
Only full-game spread, total and moneyline markets are kept, only entries before kickoff, and only
entries whose price or active flag changed for that outcome (lossless for prices). For `limit_books`
(the market makers, whose limits mean something) a limit change is kept too.

Timestamps are compared as UTC instants, never as text: `2026-10-11T17:30:00+01:00` is before a
17:00Z kickoff. A timestamp without a zone is an error, not local time. Dropping repeated states while
streaming is lossless only if each outcome's entries arrive in time order, which every response seen so
far does (ADR-067); an entry earlier than its predecessor fails the fixture instead of being silently
mis-deduplicated. Entries with the same timestamp keep their file order (`seq`).
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timezone
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
    seq: int = 0  # position in the response, to keep ties in provider order


def parse_utc(value: str) -> datetime:
    """An ISO 8601 timestamp with a zone (Z or an offset) as an aware UTC datetime. Raises ValueError
    for anything else, including a timestamp with no zone."""
    try:
        t = datetime.fromisoformat(value.replace("Z", "+00:00") if value.endswith("Z") else value)
    except (TypeError, ValueError) as err:
        raise ValueError(f"unparseable timestamp {value!r}") from err
    if t.tzinfo is None or t.utcoffset() is None:
        raise ValueError(f"timestamp without a time zone {value!r}")
    return t.astimezone(timezone.utc)


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
    """Yield kept entries in file order. `kickoff` is an ISO string with a zone; entries at or after
    that instant are in-play and dropped. Raises ValueError on a timestamp without a zone or an
    outcome whose entries go back in time."""
    kick = parse_utc(kickoff)
    last: dict[tuple[str, int, int], tuple] = {}
    seen: dict[tuple[str, int, int], datetime] = {}
    seq = 0
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
            if created is None or price is None:
                continue
            t = parse_utc(created)
            if key in seen and t < seen[key]:
                raise ValueError(f"entries out of time order for {key}: {created} after {seen[key].isoformat()}")
            seen[key] = t
            seq += 1
            if t >= kick:
                continue
            state = (price, bool(cur.get("active", True)),
                     cur.get("limit") if key[0] in limit_books else None)
            if last.get(key) == state:
                continue
            last[key] = state
            yield Entry(key[0], key[1], key[2], created, float(price), state[1],
                        None if cur.get("limit") is None else float(cur["limit"]), seq)
        elif prefix.startswith("bookmakers.") and prefix.endswith(ITEM + ".createdAt"):
            cur["createdAt"] = value
        elif prefix.endswith(ITEM + ".price"):
            cur["price"] = value
        elif prefix.endswith(ITEM + ".active"):
            cur["active"] = value
        elif prefix.endswith(ITEM + ".limit"):
            cur["limit"] = value
