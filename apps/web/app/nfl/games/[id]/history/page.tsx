import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { connection } from "next/server";
import {
  formatAmericanOdds,
  formatPoint,
  isMarket,
  MARKET_LABELS,
  type LineChange,
  type Market,
  type Selection,
} from "@marketscope/shared";
import { DataUnavailable, Notice } from "@/components/data-states";
import { HistoryCharts } from "@/components/history-charts";
import {
  defaultSelection,
  gameIdSchema,
  HISTORY_RANGES,
  historyRangeStart,
  type HistoryRange,
} from "@/lib/params";
import { isConnectionError } from "@/lib/server/api";
import { DatabaseNotConfiguredError, getDb } from "@/lib/server/db";
import { loadGameHistory, type GameHistory } from "@/lib/server/history";
import { formatKickoff, formatTimestamp } from "@/lib/time";

export const metadata: Metadata = { title: "Line history" };

const first = (v: string | string[] | undefined) => (Array.isArray(v) ? v[0] : v);
const VALID: Record<Market, Selection[]> = {
  spreads: ["HOME", "AWAY"],
  h2h: ["HOME", "AWAY"],
  totals: ["OVER", "UNDER"],
};

function sideLabel(selection: Selection, home: string, away: string) {
  return selection === "HOME"
    ? home
    : selection === "AWAY"
      ? away
      : selection === "OVER"
        ? "Over"
        : "Under";
}

export default async function HistoryPage(props: PageProps<"/nfl/games/[id]/history">) {
  await connection();
  const { id } = await props.params;
  if (!gameIdSchema.safeParse(id).success) notFound();

  const sp = await props.searchParams;
  const marketParam = first(sp.market) ?? "spreads";
  const market: Market = isMarket(marketParam) ? marketParam : "spreads";
  const selectionParam = first(sp.selection) as Selection | undefined;
  const selection =
    selectionParam && VALID[market].includes(selectionParam)
      ? selectionParam
      : defaultSelection(market);
  const rangeParam = (first(sp.range) ?? "all") as HistoryRange;
  const range: HistoryRange = rangeParam in HISTORY_RANGES ? rangeParam : "all";

  let history: GameHistory | null;
  try {
    history = await loadGameHistory(getDb(), id, {
      market,
      selection,
      from: historyRangeStart(range, new Date()),
      resolution: "changes",
      gapMinutes: 12 * 60,
      includeLive: false,
    });
  } catch (err) {
    if (err instanceof DatabaseNotConfiguredError || isConnectionError(err))
      return <DataUnavailable />;
    throw err;
  }
  if (!history) notFound();

  const { game, series, sources, observations, truncated } = history;
  const side = sideLabel(selection, game.homeTeam, game.awayTeam);
  const orientation =
    market === "spreads"
      ? `${side} spread (${selection === "HOME" ? "home" : "away"} team, as posted)`
      : market === "totals"
        ? "Total points line"
        : null;
  const changes = series
    .flatMap((s) => s.changes.map((c) => ({ ...c, displayName: s.displayName })))
    .sort((a, b) => b.intervalEnd.localeCompare(a.intervalEnd));
  const gaps = series.flatMap((s) => s.gaps.map((g) => ({ ...g, displayName: s.displayName })));

  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <Link href={`/nfl/games/${game.id}`} className="text-sm text-muted hover:text-accent">
          ← Game odds
        </Link>
        <h1 className="text-xl font-semibold tracking-tight">
          Line history: {game.awayTeam} <span className="text-muted">@</span> {game.homeTeam}
        </h1>
        <p className="text-sm text-muted">
          Kickoff <time dateTime={game.commenceTime}>{formatKickoff(game.commenceTime)}</time>
          {" · "}Pregame observations only · changes are detected between snapshots, so each change
          happened somewhere in the interval shown
        </p>
      </div>

      {sources.includes("synthetic") && (
        <Notice tone="warn" title="Synthetic data: not real odds.">
          This database contains generated demo history for development and testing.
        </Notice>
      )}

      <form
        method="get"
        className="flex flex-wrap items-end gap-x-5 gap-y-3 rounded-lg border border-line bg-surface px-4 py-3 text-sm"
      >
        <label className="flex flex-col gap-1">
          <span className="text-xs text-muted">Market</span>
          <select
            name="market"
            defaultValue={market}
            className="rounded border border-line bg-canvas px-2 py-1 text-fg"
          >
            {(["spreads", "h2h", "totals"] as const).map((m) => (
              <option key={m} value={m}>
                {MARKET_LABELS[m]}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-xs text-muted">Side</span>
          <select
            name="selection"
            defaultValue={selection}
            className="rounded border border-line bg-canvas px-2 py-1 text-fg"
          >
            {VALID[market].map((s) => (
              <option key={s} value={s}>
                {sideLabel(s, game.homeTeam, game.awayTeam)}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-xs text-muted">Range</span>
          <select
            name="range"
            defaultValue={range}
            className="rounded border border-line bg-canvas px-2 py-1 text-fg"
          >
            <option value="24h">Last 24 hours</option>
            <option value="3d">Last 3 days</option>
            <option value="7d">Last 7 days</option>
            <option value="all">All history</option>
          </select>
        </label>
        <button
          type="submit"
          className="rounded bg-accent px-3 py-1 font-medium text-canvas hover:bg-accent/90"
        >
          Apply
        </button>
      </form>

      {observations === 0 ? (
        <Notice title="No pregame observations for this selection in this range." />
      ) : (
        <>
          {truncated && (
            <Notice tone="warn" title="History truncated.">
              Too many observations to show at once; narrow the range.
            </Notice>
          )}
          <HistoryCharts
            series={series}
            market={market}
            pointLabel={orientation ?? ""}
            priceLabel={`${side} price (American odds)`}
          />
          <p className="text-xs text-subtle">
            Stepped lines hold each book&apos;s last observed value until its next observation.
            Lines break where a book went more than 12 hours without being observed. Dots mark
            detected changes.
          </p>

          <section className="space-y-2">
            <h2 className="text-sm font-medium uppercase tracking-wide text-muted">
              By sportsbook
            </h2>
            <div className="relative overflow-x-auto rounded-lg border border-line bg-surface">
              <table className="w-full min-w-[640px] text-sm">
                <thead>
                  <tr className="text-left text-xs text-muted">
                    <th scope="col" className="px-4 py-2 font-medium">
                      Feed
                    </th>
                    <th scope="col" className="px-3 py-2 font-medium">
                      First observed
                    </th>
                    <th scope="col" className="px-3 py-2 font-medium">
                      Last observed
                    </th>
                    <th scope="col" className="px-3 py-2 text-right font-medium">
                      Snapshots
                    </th>
                    <th scope="col" className="px-3 py-2 text-right font-medium">
                      Changes
                    </th>
                    <th scope="col" className="px-3 py-2 text-right font-medium">
                      Gaps
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {series.map((s) => {
                    const firstPt = s.points[0];
                    const lastPt = s.points.at(-1);
                    return (
                      <tr key={s.bookmakerKey} className="border-t border-line/60">
                        <td className="px-4 py-2">{s.displayName}</td>
                        <td className="px-3 py-2 font-mono tabular-nums">
                          {firstPt && quote(firstPt.point, firstPt.americanPrice, market)}
                          <span className="ml-2 font-sans text-xs text-subtle">
                            {s.firstObservedAt && formatTimestamp(s.firstObservedAt)}
                          </span>
                        </td>
                        <td className="px-3 py-2 font-mono tabular-nums">
                          {lastPt && quote(lastPt.point, lastPt.americanPrice, market)}
                          <span className="ml-2 font-sans text-xs text-subtle">
                            {s.lastObservedAt && formatTimestamp(s.lastObservedAt)}
                          </span>
                        </td>
                        <td className="px-3 py-2 text-right tabular-nums">{s.observations}</td>
                        <td className="px-3 py-2 text-right tabular-nums">{s.changes.length}</td>
                        <td className="px-3 py-2 text-right tabular-nums">{s.gaps.length}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <p className="text-xs text-subtle">
              &ldquo;First observed&rdquo; is MarketScope&apos;s earliest snapshot, not necessarily
              the opening line. &ldquo;Last observed&rdquo; is not necessarily the closing line.
            </p>
          </section>

          <section className="space-y-2">
            <h2 className="text-sm font-medium uppercase tracking-wide text-muted">
              Detected changes ({changes.length})
            </h2>
            {changes.length === 0 ? (
              <p className="text-sm text-muted">No changes observed in this range.</p>
            ) : (
              <div className="relative overflow-x-auto rounded-lg border border-line bg-surface">
                <table className="w-full min-w-[720px] text-sm">
                  <thead>
                    <tr className="text-left text-xs text-muted">
                      <th scope="col" className="px-4 py-2 font-medium">
                        Feed
                      </th>
                      <th scope="col" className="px-3 py-2 font-medium">
                        Change
                      </th>
                      <th scope="col" className="px-3 py-2 font-medium">
                        From → to
                      </th>
                      <th scope="col" className="px-3 py-2 font-medium">
                        Happened between
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {changes.map((c, i) => (
                      <tr key={i} className="border-t border-line/60">
                        <td className="px-4 py-2">{c.displayName}</td>
                        <td className="px-3 py-2">
                          {changeLabel(c, market)}
                          {c.acrossGap && (
                            <span
                              className="ml-2 rounded bg-warn/15 px-1.5 py-0.5 text-xs text-warn"
                              title="The interval spans a data gap; timing is uncertain"
                            >
                              across gap
                            </span>
                          )}
                        </td>
                        <td className="px-3 py-2 font-mono tabular-nums">
                          {quote(c.fromPoint, c.fromPrice, market)}{" "}
                          <span className="text-subtle">→</span>{" "}
                          {quote(c.toPoint, c.toPrice, market)}
                        </td>
                        <td className="px-3 py-2 text-xs text-muted">
                          {formatTimestamp(c.intervalStart)} – {formatTimestamp(c.intervalEnd)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          {gaps.length > 0 && (
            <section className="space-y-1 text-sm">
              <h2 className="text-sm font-medium uppercase tracking-wide text-muted">Data gaps</h2>
              <ul className="space-y-0.5 text-muted">
                {gaps.map((g, i) => (
                  <li key={i}>
                    {g.displayName}: not observed for {Math.round(g.minutes / 60)} h (
                    {formatTimestamp(g.from)} – {formatTimestamp(g.to)})
                  </li>
                ))}
              </ul>
            </section>
          )}
        </>
      )}
    </div>
  );
}

function quote(point: number | null, price: number, market: Market) {
  const p = formatPoint(point, market);
  return (
    <>
      {p && <span className="mr-1.5">{p}</span>}
      <span>{formatAmericanOdds(price)}</span>
    </>
  );
}

function changeLabel(c: LineChange, market: Market): string {
  if (c.type === "price") return "Price";
  const delta = c.pointDelta ?? 0;
  const size = `${Math.abs(delta)} pt${Math.abs(delta) === 1 ? "" : "s"}`;
  const kind = c.type === "both" ? "Line + price" : "Line";
  if (market === "totals") return `${kind}: total ${delta > 0 ? "up" : "down"} ${size}`;
  return `${kind}: ${delta > 0 ? "+" : "−"}${size}`;
}
