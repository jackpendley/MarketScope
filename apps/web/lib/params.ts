// Query-parameter schemas shared by API routes and pages. Pure (no Next.js imports).
import { z } from "zod";

export const MAX_GAMES = 100;
export const MAX_WINDOW_DAYS = 31;
const HOUR = 3_600_000;
const DAY = 24 * HOUR;

/** Default window: games that kicked off up to 4h ago (so in-progress games stay visible) through 7 days out. */
export function defaultWindow(now: Date): { from: string; to: string } {
  return {
    from: new Date(now.getTime() - 4 * HOUR).toISOString(),
    to: new Date(now.getTime() + 7 * DAY).toISOString(),
  };
}

const isoDateTime = z.iso.datetime({ offset: true });

export function gamesQuerySchema(now: Date) {
  const defaults = defaultWindow(now);
  return z
    .object({
      from: isoDateTime.default(defaults.from),
      to: isoDateTime.default(defaults.to),
      limit: z.coerce.number().int().min(1).max(MAX_GAMES).default(50),
    })
    .strict()
    .refine((q) => Date.parse(q.to) > Date.parse(q.from), {
      message: "`to` must be after `from`",
      path: ["to"],
    })
    .refine((q) => Date.parse(q.to) - Date.parse(q.from) <= MAX_WINDOW_DAYS * DAY, {
      message: `window must be at most ${MAX_WINDOW_DAYS} days`,
      path: ["to"],
    })
    .transform((q) => ({
      ...q,
      from: new Date(q.from).toISOString(),
      to: new Date(q.to).toISOString(),
    }));
}

export const gameIdSchema = z.uuid();
