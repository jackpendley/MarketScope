"""Run records: what exactly a report was computed from (Phase 14, ADR-070).

A report names its git commit; that is not enough to reproduce it. Each runner also writes
`<report>.run.json` beside the report with:

- the input dataset: the lake's dataset ID for the selected fixtures (lake/store.py), or a content hash of
  the database rows it read;
- the parameter files' hashes (e.g. fair_value_params.json);
- the git commit and whether the working tree had uncommitted changes;
- Python and package versions;
- the corrections and exclusions applied (ghost rule, coherence rule, engine version).
"""

from __future__ import annotations

import hashlib
import json
import platform
import subprocess
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path

import pandas as pd

from .lake import store

PACKAGES = ("numpy", "pandas", "pyarrow", "duckdb", "scipy", "ijson")


def git_state(repo: Path = store.REPO) -> tuple[str, bool]:
    """(commit, dirty). Dirty means tracked files differ from the commit; untracked files are ignored."""
    sha = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
    dirty = bool(subprocess.check_output(["git", "-C", str(repo), "status", "--porcelain", "--untracked-files=no"],
                                         text=True).strip())
    return sha, dirty


def file_sha256(path: Path) -> str:
    return store.sha256_file(path)


def frame_sha256(df: pd.DataFrame) -> str:
    """Content hash of a table, independent of row order (rows are hashed, then sorted)."""
    rows = pd.util.hash_pandas_object(df, index=False).sort_values().to_numpy()
    cols = ",".join(map(str, df.columns))
    return hashlib.sha256(cols.encode() + rows.tobytes()).hexdigest()


def lake_dataset(fixture_ids) -> dict:
    """The lake dataset behind a set of fixtures: its ID and coverage, from manifest v2."""
    m = store.read_manifest()
    m = m[m["fixture_id"].isin(set(fixture_ids))]
    complete = bool(len(m)) and m["file_sha256"].notna().all()
    return {"kind": "lake", "dataset_id": store.dataset_id(m) if complete else None,
            "fixtures": int(len(m)), "rows": int(m["rows"].sum()) if len(m) else 0,
            "transform_versions": sorted({int(v) for v in m["transform_version"].dropna()}),
            "catalogs": sorted({c for c in m["catalog_sha256"].dropna()}),
            "books_missing": {r.fixture_id: r.books_missing for r in m.itertuples() if r.books_missing}}


def run_record(study: str, inputs: list[dict], params: list[Path] = (), corrections: list[str] = (),
               extra: dict | None = None) -> dict:
    sha, dirty = git_state()
    versions = {}
    for p in PACKAGES:
        try:
            versions[p] = metadata.version(p)
        except metadata.PackageNotFoundError:
            versions[p] = None
    return {"study": study, "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "git_commit": sha, "git_dirty": dirty, "python": platform.python_version(), "packages": versions,
            "inputs": inputs, "params": {p.name: file_sha256(p) for p in params},
            "corrections": list(corrections), **(extra or {})}


def write_run_record(report_path: str | Path, record: dict) -> Path:
    path = Path(report_path).with_suffix(".run.json")
    path.write_text(json.dumps(record, indent=2, sort_keys=True, default=str) + "\n")
    return path
