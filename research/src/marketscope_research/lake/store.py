"""Lake storage: one Parquet file per fixture, a markets table, a manifest, and DuckDB views.

Layout (under LAKE_DIR, default fixtures/oddspapi/local/lake):
  entries/fixture=<id>.parquet   book, market_id, outcome_id, created_at (UTC ms), price (decimal),
                                 active, limit
  markets.parquet                market_id, market_type (spreads/totals/moneyline), handicap,
                                 outcome_id, outcome_name
  manifest.parquet               fixture_id, event_id, kickoff, home, away, rows, books, version, built_at
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from .parse import Entry

REPO = Path(__file__).resolve().parents[4]
LAKE_VERSION = 1


def lake_dir() -> Path:
    return Path(os.environ.get("LAKE_DIR", REPO / "fixtures/oddspapi/local/lake"))


def main_market_rows(catalog: list[dict]) -> pd.DataFrame:
    """Full-game spread, total and moneyline markets (American football) from the market catalog."""
    rows = []
    for m in catalog:
        if m.get("sportId") not in (None, 14) or m.get("period") != "result" or m.get("playerProp"):
            continue
        if m.get("marketType") not in ("spreads", "totals", "moneyline"):
            continue
        for o in m["outcomes"]:
            rows.append({"market_id": int(m["marketId"]), "market_type": m["marketType"],
                         "handicap": float(m.get("handicap") or 0), "outcome_id": int(o["outcomeId"]),
                         "outcome_name": o["outcomeName"]})
    return pd.DataFrame(rows)


def write_markets(markets: pd.DataFrame, root: Path | None = None) -> None:
    root = root or lake_dir()
    root.mkdir(parents=True, exist_ok=True)
    markets.to_parquet(root / "markets.parquet", index=False)


def write_fixture(fixture_id: str, entries: list[Entry], root: Path | None = None) -> int:
    """Write one fixture's entries (sorted by book, market, outcome, time). Returns the row count."""
    root = root or lake_dir()
    (root / "entries").mkdir(parents=True, exist_ok=True)
    created = pd.to_datetime(pd.Series([e.created_at for e in entries], dtype="string"), utc=True,
                             format="ISO8601")
    if created.isna().any():
        raise ValueError(f"unparseable timestamps in fixture {fixture_id}")
    table = pa.table({
        "book": [e.book for e in entries],
        "market_id": pa.array([e.market_id for e in entries], pa.int64()),
        "outcome_id": pa.array([e.outcome_id for e in entries], pa.int64()),
        "created_at": pa.array(created.dt.as_unit("ms"), pa.timestamp("ms", tz="UTC")),
        "price": pa.array([e.price for e in entries], pa.float64()),
        "active": pa.array([e.active for e in entries], pa.bool_()),
        "limit": pa.array([e.limit for e in entries], pa.float64()),
    })
    # seq breaks timestamp ties in provider order, so point-in-time lookups are deterministic.
    table = table.append_column("seq", pa.array([e.seq for e in entries], pa.int64()))
    table = table.sort_by([("book", "ascending"), ("market_id", "ascending"), ("outcome_id", "ascending"),
                           ("created_at", "ascending"), ("seq", "ascending")]).drop_columns(["seq"])
    tmp = root / "entries" / f".fixture={fixture_id}.parquet.tmp"
    pq.write_table(table, tmp, compression="zstd")
    tmp.replace(root / "entries" / f"fixture={fixture_id}.parquet")  # atomic: never a half-written file
    return table.num_rows


def read_manifest(root: Path | None = None) -> pd.DataFrame:
    path = (root or lake_dir()) / "manifest.parquet"
    cols = ["fixture_id", "event_id", "kickoff", "home", "away", "rows", "books", "version", "built_at"]
    return pd.read_parquet(path) if path.exists() else pd.DataFrame(columns=cols)


def record_fixture(row: dict, root: Path | None = None) -> None:
    """Upsert one fixture's manifest row."""
    root = root or lake_dir()
    m = read_manifest(root)
    m = m[m["fixture_id"] != row["fixture_id"]]
    row = {**row, "version": LAKE_VERSION, "built_at": datetime.now(timezone.utc).isoformat()}
    m = pd.concat([m, pd.DataFrame([row])], ignore_index=True) if len(m) else pd.DataFrame([row])
    m.to_parquet(root / "manifest.parquet", index=False)


def connect(root: Path | None = None) -> duckdb.DuckDBPyConnection:
    """DuckDB with views: entries (all fixtures, with fixture_id), markets, manifest, ladder
    (entries joined to their market and outcome)."""
    root = root or lake_dir()
    con = duckdb.connect()
    con.execute("SET TimeZone = 'UTC'")  # results in UTC regardless of the machine's zone
    glob = str(root / "entries" / "fixture=*.parquet")
    con.execute(f"""CREATE VIEW entries AS
        SELECT regexp_extract(filename, 'fixture=([^/]+)\\.parquet', 1) AS fixture_id, * EXCLUDE (filename)
        FROM read_parquet('{glob}', filename = true)""")
    con.execute(f"CREATE VIEW markets AS SELECT * FROM read_parquet('{root / 'markets.parquet'}')")
    con.execute(f"CREATE VIEW manifest AS SELECT * FROM read_parquet('{root / 'manifest.parquet'}')")
    con.execute("""CREATE VIEW ladder AS
        SELECT e.*, m.market_type, m.handicap, m.outcome_name
        FROM entries e JOIN markets m USING (market_id, outcome_id)""")
    return con
