"""Lake commands (MS-052, ADR-061).

    ODDSPAPI_API_KEY=... STUDY_DATABASE_URL=... python -m marketscope_research.lake build [--from D] [--to D] [--limit N]
    STUDY_DATABASE_URL=... python -m marketscope_research.lake check     # lake main lines vs line_moves
    python -m marketscope_research.lake status            # fixtures, rows and the dataset ID
    python -m marketscope_research.lake verify            # every file's hash against the manifest
    python -m marketscope_research.lake manifest-upgrade  # fill manifest v2 fields for older fixtures
    python -m marketscope_research.lake snapshot --to DIR # self-describing archive (refuses if not verified)
    python -m marketscope_research.lake restore --from TAR --to DIR
    SUPABASE_URL=... SUPABASE_STORAGE_KEY=... python -m marketscope_research.lake push   # private bucket (ADR-073)
    SUPABASE_URL=... SUPABASE_STORAGE_KEY=... python -m marketscope_research.lake pull --dataset ID --to DIR
    SUPABASE_URL=... SUPABASE_STORAGE_KEY=... python -m marketscope_research.lake snapshots

build: 1 billable request (the fixture list; +1 for the market catalog if not cached). History calls are
free (6 per game, 5 s apart). Finished fixtures are skipped, so a rerun only fetches what is missing.
Raw responses are deleted once parsed.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from ..data import _frame, connect as db_connect
from . import check as lake_check
from . import remote as lake_remote
from . import store
from .oddspapi import Client, OddsPapiError
from .parse import stream_entries

REQUEST_GROUPS = [["pinnacle", "circasports", "bookmaker.eu"], ["draftkings", "fanduel", "caesars"],
                  ["hardrockbet"], ["novig.us"], ["prophetx"], ["kalshi"]]
MARKETS_CACHE = store.REPO / "fixtures/oddspapi/local/markets.json"


def load_catalog(client: Client | None) -> list[dict]:
    if MARKETS_CACHE.exists():
        return json.loads(MARKETS_CACHE.read_text())
    if client is None:
        raise SystemExit("No cached market catalog; run build with ODDSPAPI_API_KEY set.")
    catalog = client.markets()
    MARKETS_CACHE.parent.mkdir(parents=True, exist_ok=True)
    MARKETS_CACHE.write_text(json.dumps(catalog))
    return catalog


def event_map(dsn: str) -> pd.DataFrame:
    with db_connect(dsn) as conn:
        return _frame(conn, """SELECT id::text AS event_id, home_team, away_team, commence_time_utc
                               FROM events WHERE sport_key = 'americanfootball_nfl'""")


def match_event(events: pd.DataFrame, f: dict) -> str | None:
    kick = pd.Timestamp(f["startTime"])
    e = events[(events["home_team"] == f["participant1Name"]) & (events["away_team"] == f["participant2Name"])]
    e = e[(pd.to_datetime(e["commence_time_utc"], utc=True) - kick).abs() < pd.Timedelta(hours=6)]
    return e["event_id"].iloc[0] if len(e) else None


def log(event: str, **fields) -> None:
    print(json.dumps({"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), "event": event, **fields}),
          flush=True)


def build(args) -> int:
    key = os.environ.get("ODDSPAPI_API_KEY")
    dsn = os.environ.get("STUDY_DATABASE_URL")
    if not key or not dsn:
        raise SystemExit("Set ODDSPAPI_API_KEY and STUDY_DATABASE_URL.")
    client = Client(key)
    root = store.lake_dir()
    catalog = load_catalog(client)
    markets = store.main_market_rows(catalog)
    catalog_sha = store.write_markets(markets, root)
    main_ids = set(markets["market_id"])
    events = event_map(dsn)
    fixtures = sorted(client.fixtures(args.frm, args.to), key=lambda f: f["startTime"])[: args.limit]
    done = set(store.read_manifest(root).query(f"version == {store.LAKE_VERSION}")["fixture_id"])
    raw = root / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    failed = 0
    log("lake.fixtures", count=len(fixtures), already=len(done & {f["fixtureId"] for f in fixtures}))
    for f in fixtures:
        fid = f["fixtureId"]
        if fid in done:
            continue
        try:
            paths = [client.historical_to_file(fid, group, raw / f"{fid}-{'_'.join(group)}.json")
                     for group in REQUEST_GROUPS]

            def stream():  # parsed lazily, straight into the writer's column batches
                for path in paths:
                    with open(path, "rb") as fh:
                        yield from stream_entries(fh, main_ids, f["startTime"])

            rows = store.write_fixture(fid, stream(), root)
            for path in paths:
                path.unlink()
            facts = store.fixture_facts(fid, root)
            present = set(facts["books"].split(",")) if facts["books"] else set()
            store.record_fixture({"fixture_id": fid, "event_id": match_event(events, f), "kickoff": f["startTime"],
                                  "home": f["participant1Name"], "away": f["participant2Name"], **facts,
                                  "request_groups": json.dumps(REQUEST_GROUPS),
                                  "books_missing": ",".join(b for g in REQUEST_GROUPS for b in g if b not in present),
                                  "catalog_sha256": catalog_sha}, root)
            log("lake.fixture", fixture=fid, rows=rows)
        except (OddsPapiError, ValueError) as err:
            failed += 1
            log("lake.failed", fixture=fid, error=str(err)[:300])
    log("lake.summary", fixtures=len(fixtures), failed=failed)
    return 1 if failed else 0


def main() -> None:
    ap = argparse.ArgumentParser(prog="python -m marketscope_research.lake")
    sub = ap.add_subparsers(dest="command", required=True)
    b = sub.add_parser("build")
    b.add_argument("--from", dest="frm", default="2026-09-01T00:00:00Z")
    b.add_argument("--to", default=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
    b.add_argument("--limit", type=int)
    sub.add_parser("check")
    sub.add_parser("status")
    sub.add_parser("verify")
    sub.add_parser("manifest-upgrade")
    sn = sub.add_parser("snapshot")
    sn.add_argument("--to", required=True)
    rs = sub.add_parser("restore")
    rs.add_argument("--from", dest="frm", required=True)
    rs.add_argument("--to", required=True)
    sub.add_parser("push")
    sub.add_parser("snapshots")
    pl = sub.add_parser("pull")
    pl.add_argument("--dataset", required=True)
    pl.add_argument("--to", required=True)
    args = ap.parse_args()
    if args.command in ("push", "pull", "snapshots"):
        url, key = os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_STORAGE_KEY")
        if not url or not key:
            raise SystemExit("Set SUPABASE_URL and SUPABASE_STORAGE_KEY (a secret key; keep it in research/.env.local).")
        client = lake_remote.StorageClient(url, key)
        if args.command == "push":
            print(json.dumps(lake_remote.push(client)))
        elif args.command == "snapshots":
            print("\n".join(lake_remote.snapshots(client)) or "no snapshots")
        else:
            print(f"pulled and verified {lake_remote.pull(client, args.dataset, Path(args.to))}")
        return
    if args.command == "build":
        sys.exit(build(args))
    if args.command == "check":
        dsn = os.environ.get("STUDY_DATABASE_URL")
        if not dsn:
            raise SystemExit("Set STUDY_DATABASE_URL (read-only use).")
        print(lake_check.report(dsn))
        return
    if args.command == "verify":
        problems = store.verify()
        print("\n".join(problems) if problems else "ok: every file matches the manifest")
        sys.exit(1 if problems else 0)
    if args.command == "manifest-upgrade":
        print(f"upgraded {store.upgrade_manifest(REQUEST_GROUPS)} fixtures")
        return
    if args.command == "snapshot":
        print(store.snapshot(Path(args.to)))
        return
    if args.command == "restore":
        print(f"restored and verified {store.restore(Path(args.frm), Path(args.to))}")
        return
    m = store.read_manifest()
    did = store.dataset_id(m) if m["file_sha256"].notna().all() else "unknown (run manifest-upgrade)"
    print(f"{len(m)} fixtures, {int(m['rows'].sum()) if len(m) else 0} rows, dataset {did}, lake at {store.lake_dir()}")


if __name__ == "__main__":
    main()
