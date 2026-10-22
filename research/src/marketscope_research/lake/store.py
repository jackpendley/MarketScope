"""Lake storage: one Parquet file per fixture, a markets table, a manifest, and DuckDB views.

Layout (under LAKE_DIR, default fixtures/oddspapi/local/lake):
  entries/fixture=<id>.parquet   book, market_id, outcome_id, created_at (UTC ms), price (decimal),
                                 active, limit
  markets.parquet                market_id, market_type (spreads/totals/moneyline), handicap,
                                 outcome_id, outcome_name
  catalogs/<sha256>.parquet      every market catalog a fixture was interpreted with, by content hash
  manifest.parquet               fixture_id, event_id, kickoff, home, away, rows, books, version, built_at, and
                                 (manifest v2) schema_version, transform_version, request_groups, books_missing,
                                 first_entry, last_entry, file_sha256, catalog_sha256

Identity is separate from build time: the dataset ID hashes each fixture's file hash, schema and
transform versions and catalog hash, so rebuilding the same inputs gives the same ID and `built_at` only
records when. Files and the manifest are written to a temporary name and renamed, so an interrupted build
never leaves a half-written file and resumes by skipping what is recorded (ADR-070).
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import tarfile
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from .parse import Entry

REPO = Path(__file__).resolve().parents[4]
LAKE_VERSION = 1
SCHEMA_VERSION = 1     # columns of entries/fixture=*.parquet
TRANSFORM_VERSION = 2  # parse rules: 1 = text comparison (before ADR-067); 2 = instants, order check, seq ties
MANIFEST_COLUMNS = ["fixture_id", "event_id", "kickoff", "home", "away", "rows", "books", "version", "built_at",
                    "schema_version", "transform_version", "request_groups", "books_missing", "first_entry",
                    "last_entry", "file_sha256", "catalog_sha256"]


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


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def catalog_sha256(markets: pd.DataFrame) -> str:
    """Content hash of the main-market table, independent of row order and Parquet encoding."""
    cols = ["market_id", "market_type", "handicap", "outcome_id", "outcome_name"]
    canon = markets[cols].sort_values(["market_id", "outcome_id"]).to_csv(index=False, float_format="%.4f")
    return hashlib.sha256(canon.encode()).hexdigest()


def _atomic_parquet(df: pd.DataFrame, path: Path) -> None:
    tmp = path.with_name(f".{path.name}.tmp")
    df.to_parquet(tmp, index=False)
    tmp.replace(path)


def write_markets(markets: pd.DataFrame, root: Path | None = None) -> str:
    """The current catalog (markets.parquet) plus a copy kept under its content hash. Returns the hash."""
    root = root or lake_dir()
    (root / "catalogs").mkdir(parents=True, exist_ok=True)
    sha = catalog_sha256(markets)
    _atomic_parquet(markets, root / "markets.parquet")
    if not (root / "catalogs" / f"{sha}.parquet").exists():
        _atomic_parquet(markets, root / "catalogs" / f"{sha}.parquet")
    return sha


BATCH_ROWS = 50_000


def _batch(entries: list[Entry]) -> pa.Table:
    created = pd.to_datetime(pd.Series([e.created_at for e in entries], dtype="string"), utc=True,
                             format="ISO8601")
    if created.isna().any():
        raise ValueError("unparseable timestamps")
    return pa.table({
        "book": [e.book for e in entries],
        "market_id": pa.array([e.market_id for e in entries], pa.int64()),
        "outcome_id": pa.array([e.outcome_id for e in entries], pa.int64()),
        "created_at": pa.array(created.dt.as_unit("ms"), pa.timestamp("ms", tz="UTC")),
        "price": pa.array([e.price for e in entries], pa.float64()),
        "active": pa.array([e.active for e in entries], pa.bool_()),
        "limit": pa.array([e.limit for e in entries], pa.float64()),
        "seq": pa.array([e.seq for e in entries], pa.int64()),
    })


def write_fixture(fixture_id: str, entries: Iterable[Entry], root: Path | None = None) -> int:
    """Write one fixture's entries (sorted by book, market, outcome, time, then response order). Entries
    can be a generator: they are buffered as Arrow column batches, not Python objects, so memory grows by
    tens of bytes per kept entry instead of hundreds (ADR-070). Returns the row count."""
    root = root or lake_dir()
    (root / "entries").mkdir(parents=True, exist_ok=True)
    batches, buf = [], []
    for e in entries:
        buf.append(e)
        if len(buf) >= BATCH_ROWS:
            batches.append(_batch(buf))
            buf = []
    if buf or not batches:
        batches.append(_batch(buf))
    # seq breaks timestamp ties in provider order, so point-in-time lookups are deterministic. Sorting
    # makes the bytes canonical: the same content gives the same file hash and dataset ID.
    table = pa.concat_tables(batches).sort_by([("book", "ascending"), ("market_id", "ascending"),
                                               ("outcome_id", "ascending"), ("created_at", "ascending"),
                                               ("seq", "ascending")]).drop_columns(["seq"])
    tmp = root / "entries" / f".fixture={fixture_id}.parquet.tmp"
    pq.write_table(table, tmp, compression="zstd")
    tmp.replace(root / "entries" / f"fixture={fixture_id}.parquet")  # atomic: never a half-written file
    return table.num_rows


def read_manifest(root: Path | None = None) -> pd.DataFrame:
    path = (root or lake_dir()) / "manifest.parquet"
    m = pd.read_parquet(path) if path.exists() else pd.DataFrame(columns=MANIFEST_COLUMNS)
    for c in MANIFEST_COLUMNS:  # a v1 manifest lacks the v2 columns until `lake manifest-upgrade`
        if c not in m:
            m[c] = None
    return m


def fixture_facts(fixture_id: str, root: Path | None = None) -> dict:
    """What the stored file holds: rows, books, first and last entry, and its byte hash."""
    path = (root or lake_dir()) / "entries" / f"fixture={fixture_id}.parquet"
    t = pq.read_table(path, columns=["book", "created_at"]).to_pandas()
    return {"rows": len(t), "books": ",".join(sorted(t["book"].unique())),
            "first_entry": t["created_at"].min().isoformat() if len(t) else None,
            "last_entry": t["created_at"].max().isoformat() if len(t) else None,
            "file_sha256": sha256_file(path)}


def record_fixture(row: dict, root: Path | None = None) -> None:
    """Upsert one fixture's manifest row (atomically: a crash leaves the previous manifest intact)."""
    root = root or lake_dir()
    m = read_manifest(root)
    m = m[m["fixture_id"] != row["fixture_id"]]
    row = {"schema_version": SCHEMA_VERSION, "transform_version": TRANSFORM_VERSION, **row,
           "version": LAKE_VERSION, "built_at": datetime.now(timezone.utc).isoformat()}
    new = pd.DataFrame([row]).reindex(columns=MANIFEST_COLUMNS)
    m = pd.concat([m, new], ignore_index=True) if len(m) else new
    _atomic_parquet(m, root / "manifest.parquet")


def dataset_id(manifest: pd.DataFrame) -> str:
    """Identity of a set of fixtures: their file hashes, schema and transform versions and catalog hashes,
    in fixture order. Independent of build time and manifest row order."""
    lines = sorted(f"{r.fixture_id}|{r.file_sha256}|{r.schema_version}|{r.transform_version}|{r.catalog_sha256}"
                   for r in manifest.itertuples())
    return "lake-" + hashlib.sha256("\n".join(lines).encode()).hexdigest()[:16]


def upgrade_manifest(request_groups: list[list[str]], root: Path | None = None) -> int:
    """Fill the v2 columns of fixtures recorded before manifest v2, from their files. They were parsed
    with transform 1 and interpreted with the current catalog (the cached one, never refreshed)."""
    root = root or lake_dir()
    m = read_manifest(root)
    todo = m["file_sha256"].isna()
    if not todo.any():
        return 0
    catalog = write_markets(pd.read_parquet(root / "markets.parquet"), root)
    expected = sorted({b for g in request_groups for b in g})
    for i in m.index[todo]:
        facts = fixture_facts(m.at[i, "fixture_id"], root)
        present = set(facts["books"].split(",")) if facts["books"] else set()
        m.loc[i, list(facts)] = list(facts.values())
        m.at[i, "schema_version"], m.at[i, "transform_version"] = SCHEMA_VERSION, 1
        m.at[i, "request_groups"] = json.dumps(request_groups)
        m.at[i, "books_missing"] = ",".join(b for b in expected if b not in present)
        m.at[i, "catalog_sha256"] = catalog
    _atomic_parquet(m, root / "manifest.parquet")
    return int(todo.sum())


def verify(root: Path | None = None) -> list[str]:
    """Problems with the stored dataset: recorded files missing or changed, files not in the manifest,
    catalogs missing. Empty means every byte matches the manifest."""
    root = root or lake_dir()
    m = read_manifest(root)
    problems = []
    for r in m.itertuples():
        path = root / "entries" / f"fixture={r.fixture_id}.parquet"
        if not path.exists():
            problems.append(f"missing file for {r.fixture_id}")
        elif r.file_sha256 is None or pd.isna(r.file_sha256):
            problems.append(f"no hash recorded for {r.fixture_id} (run manifest-upgrade)")
        elif sha256_file(path) != r.file_sha256:
            problems.append(f"file changed for {r.fixture_id}")
        if isinstance(r.catalog_sha256, str) and not (root / "catalogs" / f"{r.catalog_sha256}.parquet").exists():
            problems.append(f"catalog {r.catalog_sha256[:12]} missing for {r.fixture_id}")
    recorded = set(m["fixture_id"])
    for p in (root / "entries").glob("fixture=*.parquet"):
        if p.stem.removeprefix("fixture=") not in recorded:
            problems.append(f"unrecorded file {p.name}")
    return problems


def snapshot(dest: Path, root: Path | None = None) -> Path:
    """A self-describing archive of the dataset: entries, catalogs, manifest and SNAPSHOT.json (dataset ID
    and every file's hash). Refuses a dataset that does not verify."""
    root = root or lake_dir()
    problems = verify(root)
    if problems:
        raise ValueError(f"lake does not verify: {problems[:3]}")
    m = read_manifest(root)
    did = dataset_id(m)
    files = sorted([*(root / "entries").glob("fixture=*.parquet"), *(root / "catalogs").glob("*.parquet"),
                    root / "manifest.parquet"])
    meta = {"dataset_id": did, "created_at": datetime.now(timezone.utc).isoformat(), "fixtures": len(m),
            "schema_version": SCHEMA_VERSION,
            "files": {str(f.relative_to(root)): sha256_file(f) for f in files}}
    dest.mkdir(parents=True, exist_ok=True)
    out = dest / f"{did}.tar"
    tmp = out.with_name(f".{out.name}.tmp")
    with tarfile.open(tmp, "w") as tar:
        for f in files:
            tar.add(f, arcname=str(f.relative_to(root)))
        blob = json.dumps(meta, indent=2).encode()
        info = tarfile.TarInfo("SNAPSHOT.json")
        info.size = len(blob)
        tar.addfile(info, io.BytesIO(blob))
    tmp.replace(out)
    return out


def restore(archive: Path, dest: Path) -> str:
    """Unpack a snapshot into `dest` and verify every file hash and the dataset ID. Returns the ID."""
    with tarfile.open(archive) as tar:
        tar.extractall(dest, filter="data")
    meta = json.loads((dest / "SNAPSHOT.json").read_text())
    for rel, sha in meta["files"].items():
        if sha256_file(dest / rel) != sha:
            raise ValueError(f"restored file differs: {rel}")
    did = dataset_id(read_manifest(dest))
    if did != meta["dataset_id"] or verify(dest):
        raise ValueError("restored dataset does not verify")
    return did


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
