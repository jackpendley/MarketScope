"""Postgres access for the football pipeline, with the same claim/idempotency pattern as the
odds collector (apps/collector/src/collect.ts): a job key is claimed once; a completed key is
never re-run; a failed or stale `started` key may be reclaimed."""

from __future__ import annotations

import os
from dataclasses import dataclass

import psycopg

STALE_MINUTES = 30


def connect(dsn: str | None = None) -> psycopg.Connection:
    dsn = dsn or os.environ.get("DATABASE_URL")
    if not dsn:
        raise SystemExit("Set DATABASE_URL (never printed).")
    # prepare_threshold=None: safe behind Supabase's poolers.
    return psycopg.connect(dsn, connect_timeout=15, prepare_threshold=None)


@dataclass
class Claim:
    run_id: str | None
    status: str  # "claimed", "already-completed", "in-progress"


def claim_run(conn: psycopg.Connection, job_key: str, dataset: str) -> Claim:
    with conn.transaction():
        row = conn.execute(
            """INSERT INTO nfl_ingest_runs (job_key, dataset) VALUES (%s, %s)
               ON CONFLICT (job_key) DO NOTHING RETURNING id::text""",
            (job_key, dataset),
        ).fetchone()
        if row:
            return Claim(row[0], "claimed")
        existing = conn.execute(
            "SELECT id::text, status FROM nfl_ingest_runs WHERE job_key = %s", (job_key,)
        ).fetchone()
        if existing and existing[1] == "completed":
            return Claim(None, "already-completed")
        reclaimed = conn.execute(
            f"""UPDATE nfl_ingest_runs
                SET status = 'started', attempt = attempt + 1, started_at = now(), finished_at = NULL,
                    error_message = NULL
                WHERE job_key = %s AND (status = 'failed'
                      OR (status = 'started' AND started_at < now() - interval '{STALE_MINUTES} minutes'))
                RETURNING id::text""",
            (job_key,),
        ).fetchone()
        return Claim(reclaimed[0], "claimed") if reclaimed else Claim(None, "in-progress")


def finish_run(conn: psycopg.Connection, run_id: str, rows: int, source_version: str | None) -> None:
    conn.execute(
        """UPDATE nfl_ingest_runs SET status = 'completed', finished_at = now(), rows_upserted = %s,
           source_version = %s WHERE id = %s""",
        (rows, source_version, run_id),
    )


def fail_run(conn: psycopg.Connection, run_id: str, message: str) -> None:
    # Messages are our own exception text; never include connection strings.
    conn.execute(
        "UPDATE nfl_ingest_runs SET status = 'failed', finished_at = now(), error_message = %s WHERE id = %s",
        (message[:500], run_id),
    )
