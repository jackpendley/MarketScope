import type { Metadata } from "next";
import {
  TARGET_BOOKMAKERS,
  TARGET_BOOKMAKER_KEYS,
  normalizeEventOdds,
  parseOddsResponse,
} from "@marketscope/shared";
import { SYNTHETIC_NFL_ODDS, SYNTHETIC_OBSERVED_AT } from "@marketscope/shared/fixtures";
import { EventOddsTable } from "@/components/event-odds-table";
import { buildEventBoard, type EventBoard } from "@/lib/odds-board";
import { formatDateHeading, formatTimestamp } from "@/lib/time";

export const metadata: Metadata = { title: "NFL Odds Board" };

// Temporary data source (MS-003): the synthetic fixture, normalized on the server.
// Phase 2 replaces this with a query against PostgreSQL.
function loadBoards(): EventBoard[] {
  const { events } = parseOddsResponse(SYNTHETIC_NFL_ODDS);
  return events
    .map((raw) =>
      buildEventBoard(
        normalizeEventOdds(raw, {
          observedAt: SYNTHETIC_OBSERVED_AT,
          targetBookmakers: TARGET_BOOKMAKER_KEYS,
        }),
        TARGET_BOOKMAKERS,
      ),
    )
    .sort((a, b) => a.commenceTime.localeCompare(b.commenceTime));
}

function groupByDate(boards: EventBoard[]): [string, EventBoard[]][] {
  const groups = new Map<string, EventBoard[]>();
  for (const board of boards) {
    const heading = formatDateHeading(board.commenceTime);
    groups.set(heading, [...(groups.get(heading) ?? []), board]);
  }
  return [...groups];
}

export default function NflOddsBoardPage() {
  const boards = loadBoards();

  return (
    <div className="space-y-6">
      <div
        role="note"
        className="rounded-lg border border-warn/40 bg-warn/10 px-4 py-3 text-sm text-warn"
      >
        <strong className="font-semibold">Synthetic fixture: not real odds.</strong>{" "}
        <span className="text-fg/80">
          Every matchup, line, and price below is hand-written test data that exercises edge cases.
          Real data arrives once provider verification (MS-002) and the database collector (Phase 1)
          are done.
        </span>
      </div>

      <div className="flex flex-wrap items-end justify-between gap-2">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">NFL Odds Board</h1>
          <p className="text-sm text-muted">
            Snapshot observed {formatTimestamp(SYNTHETIC_OBSERVED_AT)}. This is a timestamped
            snapshot, not live odds.
          </p>
        </div>
        <p className="max-w-md text-xs text-muted">
          <span className="font-semibold text-best">Green</span> = best price among books offering
          the <em>identical</em> line. Different spreads or totals are never ranked against each
          other.
        </p>
      </div>

      {boards.length === 0 ? (
        <p className="text-muted">No games in this snapshot.</p>
      ) : (
        groupByDate(boards).map(([heading, group]) => (
          <section key={heading} className="space-y-3">
            <h2 className="text-sm font-medium uppercase tracking-wide text-muted">{heading}</h2>
            {group.map((board) => (
              <EventOddsTable key={board.providerEventId} board={board} />
            ))}
          </section>
        ))
      )}
    </div>
  );
}
