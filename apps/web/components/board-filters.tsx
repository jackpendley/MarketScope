import { BOARD_BOOKS, MARKETS, MARKET_LABELS, type Market } from "@marketscope/shared";

export interface BoardFilterValues {
  q: string;
  market: Market | null;
  books: ReadonlySet<string>;
  days: number;
}

export const DAY_OPTIONS = [1, 3, 7, 14] as const;

/**
 * Plain GET form: filters live in the URL (shareable, back-button friendly) and the page
 * re-renders on the server. No client-side JavaScript required.
 */
export function BoardFilters({ values }: { values: BoardFilterValues }) {
  return (
    <form
      method="get"
      action="/nfl"
      className="flex flex-wrap items-end gap-x-5 gap-y-3 rounded-lg border border-line bg-surface px-4 py-3 text-sm"
    >
      <label className="flex flex-col gap-1">
        <span className="text-xs text-muted">Team</span>
        <input
          type="search"
          name="q"
          defaultValue={values.q}
          placeholder="e.g. Bills"
          className="w-44 rounded border border-line bg-canvas px-2 py-1 text-fg placeholder:text-subtle"
        />
      </label>

      <label className="flex flex-col gap-1">
        <span className="text-xs text-muted">Market</span>
        <select
          name="market"
          defaultValue={values.market ?? ""}
          className="rounded border border-line bg-canvas px-2 py-1 text-fg"
        >
          <option value="">All markets</option>
          {MARKETS.map((m) => (
            <option key={m} value={m}>
              {MARKET_LABELS[m]}
            </option>
          ))}
        </select>
      </label>

      <label className="flex flex-col gap-1">
        <span className="text-xs text-muted">Kickoff within</span>
        <select
          name="days"
          defaultValue={String(values.days)}
          className="rounded border border-line bg-canvas px-2 py-1 text-fg"
        >
          {DAY_OPTIONS.map((d) => (
            <option key={d} value={d}>
              {d === 1 ? "24 hours" : `${d} days`}
            </option>
          ))}
        </select>
      </label>

      <fieldset className="flex flex-col gap-1">
        <legend className="mb-1 text-xs text-muted">Sportsbooks</legend>
        <div className="flex flex-wrap gap-x-3 gap-y-1">
          {BOARD_BOOKS.map((b) => (
            <label key={b.id} className="flex items-center gap-1.5">
              <input
                type="checkbox"
                name="books"
                value={b.id}
                defaultChecked={values.books.has(b.id)}
                className="accent-accent"
              />
              {b.displayName}
            </label>
          ))}
        </div>
      </fieldset>

      <div className="flex gap-2">
        <button
          type="submit"
          className="rounded bg-accent px-3 py-1 font-medium text-canvas hover:bg-accent/90"
        >
          Apply
        </button>
        <a href="/nfl" className="rounded border border-line px-3 py-1 text-muted hover:text-fg">
          Reset
        </a>
      </div>
    </form>
  );
}
