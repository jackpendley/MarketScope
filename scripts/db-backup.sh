#!/usr/bin/env bash
# Back up the serving database's public schema (all app tables, auth included) to backups/ (gitignored).
#
#   SOURCE_URL=... scripts/db-backup.sh            # e.g. SOURCE_URL from apps/collector/.env.local
#
# Writes backups/marketscope-<UTC>.dump (pg_dump custom format, compressed) and a .manifest.json with the
# dump's SHA-256 and every table's row count just before and just after the dump (ADR-075). The URL is
# never printed. Restore-check with scripts/db-restore-check.sh.
set -euo pipefail
: "${SOURCE_URL:?set SOURCE_URL (never printed)}"
cd "$(dirname "$0")/.."
mkdir -p backups
stamp=$(date -u +%Y%m%dT%H%M%SZ)
dump="backups/marketscope-$stamp.dump"

counts() {
  psql "$SOURCE_URL" -At -v ON_ERROR_STOP=1 -c "
    SELECT string_agg(format('%s=%s', relname, cnt), ',' ORDER BY relname) FROM (
      SELECT c.relname, (xpath('/row/n/text()', query_to_xml(format('SELECT count(*) AS n FROM public.%I', c.relname), false, true, '')))[1]::text::bigint AS cnt
      FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
      WHERE n.nspname = 'public' AND c.relkind = 'r') t"
}

before=$(counts)
pg_dump "$SOURCE_URL" --format=custom --no-owner --no-privileges --schema=public --schema=drizzle --file "$dump"
after=$(counts)
sha=$(shasum -a 256 "$dump" | cut -d' ' -f1)
python3 - "$dump" "$sha" "$before" "$after" <<'PY'
import json, os, sys
dump, sha, before, after = sys.argv[1:5]
parse = lambda s: {k: int(v) for k, v in (p.split("=") for p in s.split(",") if p)}
b, a = parse(before), parse(after)
manifest = {"dump": os.path.basename(dump), "sha256": sha, "bytes": os.path.getsize(dump),
            "schemas": ["public", "drizzle"], "counts_before": b, "counts_after": a, "consistent": b == a}
open(dump.replace(".dump", ".manifest.json"), "w").write(json.dumps(manifest, indent=2) + "\n")
print(f"{manifest['dump']}: {manifest['bytes'] / 1e6:.1f} MB, {len(b)} tables, "
      f"{'no writes during the dump' if b == a else 'writes during the dump: counts are a range'}")
PY
