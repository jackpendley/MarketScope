import { MARKET_LABELS, formatAmericanOdds, formatPoint, type Market } from "@marketscope/shared";
import type { BoardCell, EventBoard } from "@/lib/odds-board";
import { formatKickoff, formatTimestamp } from "@/lib/time";

export function EventOddsTable({ board }: { board: EventBoard }) {
  return (
    <section
      aria-labelledby={`evt-${board.providerEventId}`}
      className="overflow-hidden rounded-lg border border-line bg-surface"
    >
      <header className="flex flex-wrap items-baseline justify-between gap-2 border-b border-line px-4 py-3">
        <h3 id={`evt-${board.providerEventId}`} className="font-medium">
          {board.awayTeam} <span className="text-muted">@</span> {board.homeTeam}
        </h3>
        <div className="flex items-center gap-3 text-sm text-muted">
          {board.isLive && (
            <span className="rounded bg-warn/15 px-2 py-0.5 text-xs font-medium text-warn">
              Started: in-play prices, not compared
            </span>
          )}
          <time dateTime={board.commenceTime}>{formatKickoff(board.commenceTime)}</time>
        </div>
      </header>

      <div className="overflow-x-auto">
        <table className="w-full min-w-[720px] border-collapse text-sm">
          <thead>
            <tr className="text-left text-xs text-muted">
              <th scope="col" className="w-56 px-4 py-2 font-medium">
                Market
              </th>
              {board.columns.map((col) => (
                <th key={col.book.key} scope="col" className="px-3 py-2 text-right font-medium">
                  <div className="text-fg">{col.book.displayName}</div>
                  <div className="font-normal text-subtle">
                    {col.inFeed
                      ? col.latestUpdate
                        ? `upd ${formatTimestamp(col.latestUpdate)}`
                        : "update time unknown"
                      : "not in feed"}
                  </div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {board.rows.map((row, i) => (
              <tr
                key={`${row.market}-${row.selection}`}
                className={i % 2 === 0 ? "border-t border-line" : "border-t border-line/40"}
              >
                <th scope="row" className="px-4 py-2 text-left font-normal">
                  {i % 2 === 0 && (
                    <span className="mr-2 inline-block w-20 text-xs uppercase tracking-wide text-subtle">
                      {MARKET_LABELS[row.market]}
                    </span>
                  )}
                  {i % 2 !== 0 && <span className="mr-2 inline-block w-20" />}
                  {row.label}
                </th>
                {board.columns.map((col) => (
                  <td key={col.book.key} className="px-3 py-2 text-right font-mono tabular-nums">
                    <Cell cell={row.cells[col.book.key]!} market={row.market} />
                  </td>
                ))}
              </tr>
            ))}
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

function Cell({ cell, market }: { cell: BoardCell; market: Market }) {
  switch (cell.kind) {
    case "quote": {
      const point = formatPoint(cell.point, market);
      return (
        <span className={cell.isBest ? "font-semibold text-best" : undefined}>
          {point && <span className="mr-2">{point}</span>}
          <span className={point ? "text-muted" : undefined}>
            {formatAmericanOdds(cell.americanPrice)}
          </span>
          {cell.isBest && <span className="sr-only"> (best price at this line)</span>}
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
