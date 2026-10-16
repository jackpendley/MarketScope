export type FreshnessLabel = "recent" | "snapshot";

export interface Freshness {
  ageMinutes: number;
  /** "recent" only within `recentMinutes`; everything older is an explicitly timestamped snapshot. */
  label: FreshnessLabel;
}

/**
 * How old an observation is relative to `now`. MarketScope polls periodically, so most
 * data is a "snapshot". The UI must never imply real-time odds.
 */
export function calculateFreshness(
  observedAt: string,
  now: Date,
  recentMinutes: number,
): Freshness {
  const observedMs = Date.parse(observedAt);
  if (Number.isNaN(observedMs)) throw new RangeError(`invalid timestamp: ${observedAt}`);
  const ageMinutes = Math.max(0, (now.getTime() - observedMs) / 60_000);
  return { ageMinutes, label: ageMinutes <= recentMinutes ? "recent" : "snapshot" };
}

/** 0.4 → "just now", 12 → "12m", 185 → "3h 5m", 3000 → "2d 2h". */
export function formatAge(minutes: number): string {
  if (minutes < 1) return "just now";
  const m = Math.floor(minutes);
  if (m < 60) return `${m}m`;
  const h = Math.floor(m / 60);
  if (h < 48) return m % 60 === 0 ? `${h}h` : `${h}h ${m % 60}m`;
  const d = Math.floor(h / 24);
  return h % 24 === 0 ? `${d}d` : `${d}d ${h % 24}h`;
}
