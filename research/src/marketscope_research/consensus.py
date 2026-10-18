"""Point-in-time consensus over snapshots, re-implemented independently of the TypeScript
code as a cross-check. Pure functions over pandas DataFrames.

Rules (match docs/SIGNAL_DEFINITIONS.md):
- A snapshot is all observations sharing one observed_at.
- One feed per board book per snapshot: Hard Rock AZ preferred over the IN feed.
- Consensus = median home spread of the board books in that snapshot, needing >= 3.
"""

from __future__ import annotations

import pandas as pd

# Board book -> feeds in preference order (mirrors BOARD_BOOKS in packages/shared).
BOARD_FEEDS: dict[str, list[str]] = {
    "draftkings": ["draftkings"],
    "fanduel": ["fanduel"],
    "betmgm": ["betmgm"],
    "caesars": ["williamhill_us"],
    "hardrock": ["hardrockbet_az", "hardrockbet"],
}
FEED_TO_BOOK = {feed: book for book, feeds in BOARD_FEEDS.items() for feed in feeds}
FEED_RANK = {feed: rank for feeds in BOARD_FEEDS.values() for rank, feed in enumerate(feeds)}
MIN_CONSENSUS_BOOKS = 3


def board_quotes(home_spreads: pd.DataFrame) -> pd.DataFrame:
    """Keep one row per (event, snapshot, board book): the preferred feed present.

    Expects columns: event_id, observed_at, bookmaker_key, point.
    """
    df = home_spreads[home_spreads["bookmaker_key"].isin(FEED_TO_BOOK)].copy()
    df["board_book"] = df["bookmaker_key"].map(FEED_TO_BOOK)
    df["feed_rank"] = df["bookmaker_key"].map(FEED_RANK)
    df = df.sort_values(["event_id", "observed_at", "board_book", "feed_rank"])
    return df.drop_duplicates(["event_id", "observed_at", "board_book"], keep="first").drop(columns="feed_rank")


def consensus_series(home_spreads: pd.DataFrame) -> pd.DataFrame:
    """Per (event, snapshot): median home spread and book count, where >= 3 books reported."""
    q = board_quotes(home_spreads)
    grouped = q.groupby(["event_id", "observed_at"])["point"].agg(consensus="median", books="count").reset_index()
    return grouped[grouped["books"] >= MIN_CONSENSUS_BOOKS].reset_index(drop=True)
