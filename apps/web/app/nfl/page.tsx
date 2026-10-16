import type { Metadata } from "next";
import { connection } from "next/server";
import { latestCompletedRun } from "@marketscope/db";
import { BoardFilters } from "@/components/board-filters";
import { DataUnavailable, Notice, SnapshotMeta } from "@/components/data-states";
import { EventOddsTable } from "@/components/event-odds-table";
import { matchesTeamSearch, parseBoardFilters } from "@/lib/board-filters";
import type { EventBoard } from "@/lib/odds-board";
import { MAX_GAMES } from "@/lib/params";
import { isConnectionError } from "@/lib/server/api";
import { DatabaseNotConfiguredError, getDb, quoteFreshnessMinutes } from "@/lib/server/db";
import { hasSyntheticData, loadGamesWithQuotes, toBoard } from "@/lib/server/games";
import { formatDateHeading } from "@/lib/time";

export const metadata: Metadata = { title: "NFL Odds Board" };

const HOUR = 3_600_000;

async function loadBoard(days: number, now: Date) {
  const db = getDb();
  const [games, latestRun] = await Promise.all([
    loadGamesWithQuotes(db, {
      from: new Date(now.getTime() - 4 * HOUR).toISOString(),
      to: new Date(now.getTime() + days * 24 * HOUR).toISOString(),
      limit: MAX_GAMES,
    }),
    latestCompletedRun(db),
  ]);
  return { boards: games.map(toBoard), latestRun, synthetic: hasSyntheticData(games) };
}

function groupByDate(boards: EventBoard[]): [string, EventBoard[]][] {
  const groups = new Map<string, EventBoard[]>();
  for (const board of boards) {
    const heading = formatDateHeading(board.commenceTime);
    groups.set(heading, [...(groups.get(heading) ?? []), board]);
  }
  return [...groups];
}

export default async function NflOddsBoardPage(props: PageProps<"/nfl">) {
  await connection(); // always render per request: odds come from the live database
  const filters = parseBoardFilters(await props.searchParams);
  const now = new Date();

  let data: Awaited<ReturnType<typeof loadBoard>>;
  try {
    data = await loadBoard(filters.days, now);
  } catch (err) {
    if (err instanceof DatabaseNotConfiguredError || isConnectionError(err)) {
      return <DataUnavailable />;
    }
    throw err;
  }

  const visible = data.boards.filter((b) => matchesTeamSearch(b, filters.q));

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">NFL Odds Board</h1>
          <p className="text-sm text-muted">
            {data.latestRun ? (
              <SnapshotMeta
                observedAt={data.latestRun.startedAt}
                recentMinutes={quoteFreshnessMinutes()}
                now={now}
              />
            ) : (
              "No snapshots collected yet"
            )}
            {" · "}Source: The Odds API, collected periodically (not live odds)
          </p>
        </div>
        <p className="max-w-md text-xs text-muted">
          <span className="font-semibold text-best">Green</span> = best price among books offering
          the <em>identical</em> line in the latest snapshot. <span className="italic">Italic</span>{" "}
          = last-seen price from a book missing from the latest snapshot.
        </p>
      </div>

      {data.synthetic && (
        <Notice tone="warn" title="Synthetic data: not real odds.">
          This database contains generated demo history for development and testing.
        </Notice>
      )}

      <BoardFilters values={filters} />

      {!data.latestRun ? (
        <Notice title="No odds collected yet.">
          Run <code>pnpm collect:nfl</code> to store the first snapshot.
        </Notice>
      ) : data.boards.length === 0 ? (
        <Notice title={`No games kicking off in the next ${filters.days} day(s).`} />
      ) : visible.length === 0 ? (
        <Notice title={`No games match “${filters.q}”.`} />
      ) : (
        groupByDate(visible).map(([heading, group]) => (
          <section key={heading} className="space-y-3">
            <h2 className="text-sm font-medium uppercase tracking-wide text-muted">{heading}</h2>
            {group.map((board) => (
              <EventOddsTable
                key={board.providerEventId}
                board={board}
                visibleBookIds={filters.books}
                market={filters.market ?? undefined}
                linkToDetail
              />
            ))}
          </section>
        ))
      )}
    </div>
  );
}
