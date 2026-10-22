#!/usr/bin/env bash
# Prove a backup restores: load it into a throwaway local database and compare every table's row count with
# the backup's manifest (ADR-075). Local only; the scratch database is dropped afterwards.
#
#   scripts/db-restore-check.sh backups/marketscope-<UTC>.dump
set -euo pipefail
dump="${1:?usage: scripts/db-restore-check.sh backups/<file>.dump}"
manifest="${dump%.dump}.manifest.json"
db=marketscope_restore_check
url="postgres://localhost:5432/$db"
[ "$(shasum -a 256 "$dump" | cut -d' ' -f1)" = "$(python3 -c "import json,sys;print(json.load(open(sys.argv[1]))['sha256'])" "$manifest")" ] \
  || { echo "dump does not match its manifest hash"; exit 1; }
dropdb --if-exists "$db" && createdb "$db"
trap 'dropdb --if-exists "$db"' EXIT
# The dump recreates the public schema; drop the fresh database's empty one (scratch database only).
psql "$url" -q -c "DROP SCHEMA public CASCADE"
start=$(date +%s)
pg_restore --no-owner --no-privileges --exit-on-error --dbname "$url" "$dump" 2>&1 | grep -v "^$" || true
counts=$(psql "$url" -At -c "
  SELECT string_agg(format('%s=%s', relname, cnt), ',' ORDER BY relname) FROM (
    SELECT c.relname, (xpath('/row/n/text()', query_to_xml(format('SELECT count(*) AS n FROM public.%I', c.relname), false, true, '')))[1]::text::bigint AS cnt
    FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public' AND c.relkind = 'r') t")
python3 - "$manifest" "$counts" "$(( $(date +%s) - start ))" <<'PY'
import json, sys
m, got, secs = json.load(open(sys.argv[1])), dict(p.split("=") for p in sys.argv[2].split(",") if p), sys.argv[3]
bad = [t for t in m["counts_before"] if not (min(m["counts_before"][t], m["counts_after"].get(t, 0))
       <= int(got.get(t, -1)) <= max(m["counts_before"][t], m["counts_after"].get(t, 0)))]
rows = sum(int(v) for v in got.values())
if bad:
    sys.exit(f"restore check FAILED for {len(bad)} tables: {bad[:5]}")
print(f"restore check passed: {len(got)} tables, {rows} rows, every count matches the manifest ({secs}s)")
PY
