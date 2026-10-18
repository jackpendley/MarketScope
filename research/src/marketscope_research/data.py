"""Read-only data access for studies. Never writes: the session is set read-only."""

from __future__ import annotations

import pandas as pd
import psycopg


def connect(dsn: str) -> psycopg.Connection:
    conn = psycopg.connect(dsn, connect_timeout=15, prepare_threshold=None)
    conn.execute("SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY")
    return conn


def _frame(conn: psycopg.Connection, query: str, params: tuple = ()) -> pd.DataFrame:
    with conn.cursor() as cur:
        cur.execute(query, params)
        cols = [c.name for c in cur.description]
        return pd.DataFrame(cur.fetchall(), columns=cols)


def load_home_spreads(conn: psycopg.Connection, sources: list[str]) -> pd.DataFrame:
    """Pregame home spreads from the given sources. Each game comes from exactly one source
    (the OddsPapi importer refuses games collected live), so snapshots never mix sources."""
    df = _frame(
        conn,
        """
        SELECT event_id::text, observed_at, bookmaker_key, point::float8 AS point, source,
               bookmaker_updated_at
        FROM odds_observations
        WHERE market_type = 'spreads' AND selection = 'HOME' AND NOT is_live AND source = ANY(%s)
        """,
        (sources,),
    )
    df["observed_at"] = pd.to_datetime(df["observed_at"], utc=True)
    df["bookmaker_updated_at"] = pd.to_datetime(df["bookmaker_updated_at"], utc=True)
    return df


def load_totals(conn: psycopg.Connection, sources: list[str]) -> pd.DataFrame:
    """Pregame OVER totals (the line is the same for both sides) from the given sources."""
    df = _frame(
        conn,
        """
        SELECT event_id::text, observed_at, bookmaker_key, point::float8 AS point, source
        FROM odds_observations
        WHERE market_type = 'totals' AND selection = 'OVER' AND NOT is_live AND source = ANY(%s)
        """,
        (sources,),
    )
    df["observed_at"] = pd.to_datetime(df["observed_at"], utc=True)
    return df


def load_divergence_events(conn: psycopg.Connection, event_ids: list[str]) -> pd.DataFrame:
    df = _frame(
        conn,
        """
        SELECT event_id::text, bookmaker_key, detected_at, value,
               (details->>'consensus')::float8 AS consensus
        FROM market_signals
        WHERE signal_type = 'book_divergence' AND algorithm_version = 1 AND event_id::text = ANY(%s)
        """,
        (event_ids,),
    )
    df["detected_at"] = pd.to_datetime(df["detected_at"], utc=True)
    return df


def load_kickoffs(conn: psycopg.Connection) -> pd.Series:
    df = _frame(conn, "SELECT id::text AS event_id, commence_time_utc FROM events")
    # Keep the UTC timezone (``.values`` would drop it and break tz-aware comparisons).
    kickoffs = pd.to_datetime(df["commence_time_utc"], utc=True)
    kickoffs.index = df["event_id"]
    return kickoffs
