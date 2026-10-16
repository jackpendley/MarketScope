import { calculateFreshness, formatAge } from "@marketscope/shared";
import { formatTimestamp } from "@/lib/time";

export function Notice({
  tone = "muted",
  title,
  children,
}: {
  tone?: "muted" | "warn";
  title: string;
  children?: React.ReactNode;
}) {
  const styles =
    tone === "warn" ? "border-warn/40 bg-warn/10 text-warn" : "border-line bg-surface text-muted";
  return (
    <div role="status" className={`rounded-lg border px-4 py-3 text-sm ${styles}`}>
      <strong className="font-semibold">{title}</strong>
      {children && <div className="mt-1 text-fg/80">{children}</div>}
    </div>
  );
}

export function DataUnavailable() {
  return (
    <Notice tone="warn" title="The odds database is unavailable.">
      MarketScope reads only from its own database. Check that PostgreSQL is running and that{" "}
      <code>DATABASE_URL</code> is set in <code>apps/web/.env.local</code>.
    </Notice>
  );
}

/** "Snapshot collected Oct 15, 6:43 PM EDT · 3h 12m ago". Never implies live odds. */
export function SnapshotMeta({
  observedAt,
  recentMinutes,
  now,
}: {
  observedAt: string;
  recentMinutes: number;
  now: Date;
}) {
  const { ageMinutes, label } = calculateFreshness(observedAt, now, recentMinutes);
  return (
    <span>
      {label === "recent" ? "Recent snapshot" : "Snapshot"} collected{" "}
      <time dateTime={observedAt}>{formatTimestamp(observedAt)}</time> · {formatAge(ageMinutes)} ago
    </span>
  );
}
