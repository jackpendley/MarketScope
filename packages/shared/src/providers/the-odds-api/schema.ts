// Zod schemas for The Odds API v4 responses (shape per docs, verified 2026-10-15).
//
// These validate STRUCTURE only. Value-level problems (bad prices, unknown outcome
// names, malformed timestamps) are deliberately left to the normalizer so one bad
// price produces a reported issue instead of discarding a whole event.

import { z } from "zod";

export const sportSchema = z.object({
  key: z.string(),
  group: z.string(),
  title: z.string(),
  description: z.string(),
  active: z.boolean(),
  has_outrights: z.boolean(),
});
export type ProviderSport = z.infer<typeof sportSchema>;

export const eventSchema = z.object({
  id: z.string().min(1),
  sport_key: z.string(),
  sport_title: z.string().optional(),
  commence_time: z.iso.datetime({ offset: true }),
  home_team: z.string().min(1),
  away_team: z.string().min(1),
});
export type ProviderEvent = z.infer<typeof eventSchema>;

export const outcomeSchema = z.object({
  name: z.string(),
  price: z.number(),
  point: z.number().optional(),
});

export const marketSchema = z.object({
  key: z.string(),
  /** Market-level update time. Use this, not the deprecated bookmaker-level field. */
  last_update: z.string().optional(),
  outcomes: z.array(outcomeSchema),
});

export const bookmakerSchema = z.object({
  key: z.string(),
  title: z.string(),
  /** Deprecated by the provider; kept only so parsing doesn't depend on its absence. */
  last_update: z.string().optional(),
  markets: z.array(marketSchema),
});

export const eventOddsSchema = eventSchema.extend({
  bookmakers: z.array(bookmakerSchema),
});
export type ProviderEventOdds = z.infer<typeof eventOddsSchema>;

export interface ParsedOddsResponse {
  events: ProviderEventOdds[];
  /** Events that failed structural validation, with a reason. Reported, not thrown. */
  rejected: { index: number; providerEventId: string | null; reason: string }[];
}

/**
 * Parse an /odds response event-by-event so one malformed event doesn't sink the batch.
 * Throws only if the payload isn't an array at all.
 */
export function parseOddsResponse(payload: unknown): ParsedOddsResponse {
  const items = z.array(z.unknown()).parse(payload);
  const result: ParsedOddsResponse = { events: [], rejected: [] };

  items.forEach((item, index) => {
    const parsed = eventOddsSchema.safeParse(item);
    if (parsed.success) {
      result.events.push(parsed.data);
    } else {
      const id =
        typeof item === "object" && item !== null && "id" in item && typeof item.id === "string"
          ? item.id
          : null;
      result.rejected.push({ index, providerEventId: id, reason: z.prettifyError(parsed.error) });
    }
  });

  return result;
}
