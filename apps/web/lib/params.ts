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

export const HISTORY_RANGES = { "24h": 24, "3d": 72, "7d": 168, all: null } as const;
export type HistoryRange = keyof typeof HISTORY_RANGES;

const MARKET_VALUES = ["h2h", "spreads", "totals"] as const;
const SELECTION_VALUES = ["HOME", "AWAY", "OVER", "UNDER"] as const;
const VALID_SELECTIONS: Record<(typeof MARKET_VALUES)[number], readonly string[]> = {
  h2h: ["HOME", "AWAY"],
  spreads: ["HOME", "AWAY"],
  totals: ["OVER", "UNDER"],
};

/** Default side: the home team for spreads/moneylines (consistent orientation), Over for totals. */
export function defaultSelection(market: (typeof MARKET_VALUES)[number]) {
  return market === "totals" ? ("OVER" as const) : ("HOME" as const);
}

export const historyQuerySchema = z
  .object({
    market: z.enum(MARKET_VALUES).default("spreads"),
    selection: z.enum(SELECTION_VALUES).optional(),
    books: z
      .string()
      .transform((s) =>
        s
          .split(",")
          .map((b) => b.trim())
          .filter(Boolean),
      )
      .optional(),
    from: isoDateTime.optional(),
    to: isoDateTime.optional(),
    resolution: z.enum(["changes", "all"]).default("changes"),
    gapMinutes: z.coerce
      .number()
      .int()
      .min(30)
      .max(7 * 24 * 60)
      .default(12 * 60),
    includeLive: z
      .enum(["true", "false"])
      .default("false")
      .transform((v) => v === "true"),
  })
  .strict()
  .transform((q) => ({ ...q, selection: q.selection ?? defaultSelection(q.market) }))
  .refine((q) => VALID_SELECTIONS[q.market].includes(q.selection), {
    message: "selection is not valid for this market",
    path: ["selection"],
  })
  .refine((q) => !q.from || !q.to || Date.parse(q.to) > Date.parse(q.from), {
    message: "`to` must be after `from`",
    path: ["to"],
  });

export type HistoryParams = z.infer<typeof historyQuerySchema>;

/** Start of a history range relative to `now` (undefined = all history). */
export function historyRangeStart(range: HistoryRange, now: Date): string | undefined {
  const hours = HISTORY_RANGES[range];
  return hours === null ? undefined : new Date(now.getTime() - hours * 3_600_000).toISOString();
}
