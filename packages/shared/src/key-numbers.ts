// NFL key numbers: the most common margins of victory (3 and 7, then 6, 10, 14).
// A spread moving across or onto a key number changes its value far more than a
// half-point elsewhere. Detection here is purely descriptive: it says nothing about
// whether a line has betting value.

export const NFL_KEY_NUMBERS: readonly number[] = [3, 7];

export type KeyNumberEventKind = "crossed" | "landed-on" | "left";

export interface KeyNumberEvent {
  /** The key number as a margin (always positive), e.g. 3. */
  key: number;
  /** The signed spread value involved, e.g. -3 (favorite side) or +3 (underdog side). */
  signedKey: number;
  kind: KeyNumberEventKind;
}

/**
 * Key-number events for a spread moving from `from` to `to` (same team's spread, as
 * posted). Signed keys are used so a favorite flipping from −3.5 to +3.5 correctly
 * crosses both −3 and +3, while −1.5 → +1.5 crosses none.
 *
 * - crossed: the key lies strictly between the two lines (−2.5 → −3.5 crosses −3)
 * - landed-on: the new line equals the key (−2.5 → −3)
 * - left: the old line equalled the key (−3 → −3.5)
 */
export function detectKeyNumberCrossings(
  from: number,
  to: number,
  keyNumbers: readonly number[] = NFL_KEY_NUMBERS,
): KeyNumberEvent[] {
  if (!Number.isFinite(from) || !Number.isFinite(to)) {
    throw new RangeError("spread points must be finite numbers");
  }
  if (from === to) return [];
  const lo = Math.min(from, to);
  const hi = Math.max(from, to);
  const events: KeyNumberEvent[] = [];
  const signedKeys = keyNumbers.flatMap((k) => [-k, k]).sort((a, b) => a - b);
  // Order events in the direction of travel.
  const ordered = from < to ? signedKeys : [...signedKeys].reverse();

  for (const signedKey of ordered) {
    const key = Math.abs(signedKey);
    if (signedKey === from) events.push({ key, signedKey, kind: "left" });
    else if (signedKey === to) events.push({ key, signedKey, kind: "landed-on" });
    else if (signedKey > lo && signedKey < hi) events.push({ key, signedKey, kind: "crossed" });
  }
  return events;
}
