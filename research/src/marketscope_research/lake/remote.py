"""Durable private copy of the research lake in Supabase Storage (ADR-073).

The bucket `lake-snapshots` is private: no storage policies, so only a secret key can read or write it.
Free-tier objects are limited to 50 MB, so a snapshot is not one archive. Every file is stored once
under its content hash, and a small manifest names the files of each dataset:

    objects/<sha256>               a fixture file, catalog or manifest, by content
    snapshots/<dataset id>.json    {"dataset_id", "created_at", "files": {path: sha256}}

A new snapshot uploads only files the bucket does not have yet. Pulling verifies every file's hash, then
the dataset ID and `store.verify`, before anything is trusted. The key goes in a request header, never in
a URL, and is never logged.
"""

from __future__ import annotations

import hashlib
import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from . import store

BUCKET = "lake-snapshots"


class StorageClient:
    """The three Storage REST calls we need, over urllib (Supabase stays managed Postgres plus this)."""

    def __init__(self, project_url: str, key: str, bucket: str = BUCKET, timeout: int = 120):
        self.base = project_url.rstrip("/") + "/storage/v1"
        self.headers = {"Authorization": f"Bearer {key}", "apikey": key}
        self.bucket, self.timeout = bucket, timeout

    def _request(self, method: str, path: str, body: bytes | None = None, headers: dict | None = None) -> bytes:
        req = urllib.request.Request(f"{self.base}{path}", data=body, method=method,
                                     headers={**self.headers, **(headers or {})})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:  # the path holds no secret; the key is only in headers
            raise RuntimeError(f"storage {method} {path} failed: HTTP {e.code}") from None

    def list(self, prefix: str) -> set[str]:
        names, offset = set(), 0
        while True:
            body = json.dumps({"prefix": prefix, "limit": 1000, "offset": offset}).encode()
            page = json.loads(self._request("POST", f"/object/list/{self.bucket}", body,
                                            {"Content-Type": "application/json"}))
            names |= {f"{prefix.rstrip('/')}/{o['name']}" for o in page if o.get("id")}
            if len(page) < 1000:
                return names
            offset += 1000

    def put(self, path: str, data: bytes, upsert: bool = False) -> None:
        self._request("POST", f"/object/{self.bucket}/{urllib.parse.quote(path)}", data,
                      {"Content-Type": "application/octet-stream", "x-upsert": "true" if upsert else "false"})

    def get(self, path: str) -> bytes:
        return self._request("GET", f"/object/authenticated/{self.bucket}/{urllib.parse.quote(path)}")


def _files(root: Path) -> list[Path]:
    return sorted([*(root / "entries").glob("fixture=*.parquet"), *(root / "catalogs").glob("*.parquet"),
                   root / "manifest.parquet"])


def push(client, root: Path | None = None) -> dict:
    """Upload the lake as a snapshot. Refuses a lake that does not verify. Returns what was sent."""
    root = root or store.lake_dir()
    problems = store.verify(root)
    if problems:
        raise ValueError(f"lake does not verify: {problems[:3]}")
    did = store.dataset_id(store.read_manifest(root))
    files = {str(f.relative_to(root)): store.sha256_file(f) for f in _files(root)}
    have = client.list("objects")
    sent = 0
    for rel, sha in files.items():
        if f"objects/{sha}" not in have:
            client.put(f"objects/{sha}", (root / rel).read_bytes())
            sent += 1
    snapshot = {"dataset_id": did, "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "schema_version": store.SCHEMA_VERSION, "files": files}
    client.put(f"snapshots/{did}.json", json.dumps(snapshot, indent=2, sort_keys=True).encode(), upsert=True)
    return {"dataset_id": did, "files": len(files), "uploaded": sent, "already_stored": len(files) - sent}


def snapshots(client) -> list[str]:
    return sorted(n.removeprefix("snapshots/").removesuffix(".json") for n in client.list("snapshots"))


def pull(client, dataset_id: str, dest: Path) -> str:
    """Download one snapshot into `dest` and verify every hash, the dataset ID and the manifest."""
    snap = json.loads(client.get(f"snapshots/{dataset_id}.json"))
    for rel, sha in snap["files"].items():
        data = client.get(f"objects/{sha}")
        if hashlib.sha256(data).hexdigest() != sha:
            raise ValueError(f"downloaded file differs from its hash: {rel}")
        path = dest / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f".{path.name}.tmp")
        tmp.write_bytes(data)
        tmp.replace(path)
    did = store.dataset_id(store.read_manifest(dest))
    if did != snap["dataset_id"] or store.verify(dest):
        raise ValueError("pulled dataset does not verify")
    return did
