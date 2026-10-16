import Link from "next/link";
import { MARKET_LABELS, formatAmericanOdds, formatPoint, type Market } from "@marketscope/shared";
import type { BoardCell, EventBoard } from "@/lib/odds-board";
import { formatKickoff, formatTimestamp } from "@/lib/time";

export interface EventOddsTableProps {
  board: EventBoard;
  /** Board-book ids to show (default: all). */
  visibleBookIds?: ReadonlySet<string>;
  /** Restrict rows to one market (default: all). */
  market?: Market;
  /** Link the matchup title to the game detail page. */
  linkToDetail?: boolean;
}

export function EventOddsTable({
  board,
  visibleBookIds,
  market,
  linkToDetail,
}: EventOddsTableProps) {
  const columns = board.columns.filter((c) => !visibleBookIds || visibleBookIds.has(c.book.id));
  const rows = board.rows.filter((r) => !market || r.market === market);
  const titleId = `evt-${board.providerEventId}`;
  const title = (
    <>
      {board.awayTeam} <span className="text-muted">@</span> {board.homeTeam}
    </>
  );

  return (
    <section
      aria-labelledby={titleId}
      className="overflow-hidden rounded-lg border border-line bg-surface"
    >
      <header className="flex flex-wrap items-baseline justify-between gap-2 border-b border-line px-4 py-3">
        <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
          <h3 id={titleId} className="font-medium">
            {linkToDetail && board.gameId ? (
              <Link href={`/nfl/games/${board.gameId}`} className="hover:text-accent">
                {title}
              </Link>
            ) : (
              title
            )}
          </h3>
          <ConsensusBadge board={board} />
        </div>
        <div className="flex items-center gap-3 text-sm text-muted">
          {board.isLive && (
            <span className="rounded bg-warn/15 px-2 py-0.5 text-xs font-medium text-warn">
              Started: in-play prices, not compared
            </span>
          )}
          <time dateTime={board.commenceTime}>{formatKickoff(board.commenceTime)}</time>
        </div>
      </header>

      <div className="relative overflow-x-auto">
        <table className="w-full min-w-[640px] border-collapse text-sm">
          <thead>
            <tr className="text-left text-xs text-muted">
              <th scope="col" className="px-4 py-2 font-medium">
                Market
              </th>
              {columns.map((col) => (
                <th key={col.book.id} scope="col" className="px-3 py-2 text-right font-medium">
                  <div className="text-fg">{col.book.displayName}</div>
                  {col.fallbackLabel && (
                    <div
                      className="font-normal text-warn"
                      title={`Preferred feed unavailable for this game; showing the ${col.fallbackLabel}`}
                    >
                      {col.fallbackLabel}
                    </div>
                  )}
                  <div className="font-normal text-subtle">
                    {!col.feedKey
                      ? "not in feed"
                      : col.stale
                        ? "not in latest snapshot"
                        : col.latestUpdate
                          ? `upd ${formatTimestamp(col.latestUpdate)}`
                          : "update time unknown"}
                  </div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => {
              const firstOfMarket = i === 0 || rows[i - 1]!.market !== row.market;
              return (
                <tr
                  key={`${row.market}-${row.selection}`}
                  className={firstOfMarket ? "border-t border-line" : "border-t border-line/40"}
                >
                  <th scope="row" className="whitespace-nowrap px-4 py-2 text-left font-normal">
                    <span className="mr-2 inline-block w-20 text-xs uppercase tracking-wide text-subtle">
                      {firstOfMarket ? MARKET_LABELS[row.market] : ""}
                    </span>
                    {row.label}
                  </th>
                  {columns.map((col) => (
                    <td key={col.book.id} className="px-3 py-2 text-right font-mono tabular-nums">
                      <Cell cell={row.cells[col.book.id]!} market={row.market} />
                    </td>
                  ))}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {board.issues.length > 0 && (
        <details className="border-t border-line px-4 py-2 text-xs text-muted">
          <summary className="cursor-pointer select-none">
            Data quality: {board.issues.length} issue{board.issues.length === 1 ? "" : "s"} in this
            feed
          </summary>
          <ul className="mt-2 space-y-1 pb-1">
            {board.issues.map((issue, idx) => (
              <li key={idx}>
                <code className="text-warn">{issue.code}</code>
                {issue.bookmakerKey && <span className="text-subtle"> · {issue.bookmakerKey}</span>}
                {issue.market && <span className="text-subtle"> · {issue.market}</span>}
                <span>: {issue.detail}</span>
              </li>
            ))}
          </ul>
        </details>
      )}
    </section>
  );
}

export function ConsensusBadge({ board }: { board: EventBoard }) {
  const { consensus } = board;
  if (consensus.homePoint === null) {
    return (
      <span className="text-xs text-subtle" title={`No consensus: ${consensus.reason}`}>
        consensus n/a
      </span>
    );
  }
  return (
    <span
      className="text-xs text-muted"
      title={`Median home spread across ${consensus.bookmakerKeys.join(", ")} (current snapshot only)`}
    >
      consensus{" "}
      <span className="font-mono tabular-nums text-fg">
        {board.homeTeam.split(" ").at(-1)} {formatPoint(consensus.homePoint, "spreads")}
      </span>{" "}
      · {consensus.bookmakerKeys.length} books
    </span>
  );
}

function Cell({ cell, market }: { cell: BoardCell; market: Market }) {
  switch (cell.kind) {
    case "quote": {
      const point = formatPoint(cell.point, market);
      const tone = cell.stale
        ? "text-subtle italic"
        : cell.isBest
          ? "font-semibold text-best"
          : undefined;
      return (
        <span
          className={tone}
          title={
            cell.stale
              ? `Last seen ${formatTimestamp(cell.observedAt)}; not in the latest snapshot`
              : undefined
          }
        >
          {point && <span className="mr-2">{point}</span>}
          <span className={point && !cell.isBest && !cell.stale ? "text-muted" : undefined}>
            {formatAmericanOdds(cell.americanPrice)}
          </span>
          {cell.isBest && <span className="sr-only"> (best price at this line)</span>}
          {cell.stale && <span className="sr-only"> (stale: not in the latest snapshot)</span>}
        </span>
      );
    }
    case "book-missing":
      return (
        <span
          className="text-subtle"
          title="This sportsbook is not in the provider feed for this game"
        >
          —
        </span>
      );
    case "market-missing":
      return (
        <span
          className="font-sans text-xs text-subtle"
          title="This sportsbook does not list this market in the feed"
        >
          not offered
        </span>
      );
    case "selection-missing":
      return (
        <span
          className="font-sans text-xs text-warn"
          title="Missing or rejected by validation; see data quality"
        >
          unavailable
        </span>
      );
  }
}
