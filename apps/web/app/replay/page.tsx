import type { Metadata } from "next";
import Link from "next/link";
import { connection } from "next/server";
import { listGames, observationSummaries } from "@marketscope/db";
import { DataUnavailable, Notice } from "@/components/data-states";
import { isConnectionError } from "@/lib/server/api";
import { DatabaseNotConfiguredError, getDb } from "@/lib/server/db";
import { formatDateHeading, formatKickoff, formatTimestamp } from "@/lib/time";

export const metadata: Metadata = { title: "Market Replay" };

const DAY = 24 * 3_600_000;

export default async function ReplayIndexPage() {
  await connection();
  const now = new Date();
  let rows;
  try {
    const db = getDb();
    const games = await listGames(db, {
      from: new Date(now.getTime() - 14 * DAY).toISOString(),
      to: new Date(now.getTime() + 14 * DAY).toISOString(),
      limit: 100,
    });
    const summaries = await observationSummaries(
      db,
      games.map((g) => g.id),
    );
    rows = games
      .map((game) => ({ game, stats: summaries.get(game.id) }))
      .filter((r) => r.stats && r.stats.observations > 0);
  } catch (err) {
    if (err instanceof DatabaseNotConfiguredError || isConnectionError(err))
      return <DataUnavailable />;
    throw err;
  }

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">Market Replay</h1>
        <p className="text-sm text-muted">
          Step through every stored snapshot of a game&apos;s market: what each book showed, how the
          consensus moved, and when lines crossed key numbers. Games from the last and next two
          weeks with stored history.
        </p>
      </div>

      {rows.length === 0 ? (
        <Notice title="No stored history yet.">
          Snapshots appear here after the collector runs.
        </Notice>
      ) : (
        <div className="relative overflow-x-auto rounded-lg border border-line bg-surface">
          <table className="w-full min-w-[640px] text-sm">
            <thead>
              <tr className="text-left text-xs text-muted">
                <th scope="col" className="px-4 py-2 font-medium">
                  Game
                </th>
                <th scope="col" className="px-3 py-2 font-medium">
                  Kickoff
                </th>
                <th scope="col" className="px-3 py-2 text-right font-medium">
                  Snapshots
                </th>
                <th scope="col" className="px-3 py-2 font-medium">
                  First observed
                </th>
                <th scope="col" className="px-3 py-2 font-medium">
                  Last observed
                </th>
                <th scope="col" className="px-3 py-2" />
              </tr>
            </thead>
            <tbody>
              {rows.map(({ game, stats }) => (
                <tr key={game.id} className="border-t border-line/60">
                  <td className="px-4 py-2">
                    {game.awayTeam} <span className="text-muted">@</span> {game.homeTeam}
                  </td>
                  <td className="whitespace-nowrap px-3 py-2 text-muted">
                    {formatDateHeading(game.commenceTime).split(",")[0]},{" "}
                    {formatKickoff(game.commenceTime)}
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums">{stats!.snapshots}</td>
                  <td className="whitespace-nowrap px-3 py-2 text-xs text-muted">
                    {stats!.firstObservedAt && formatTimestamp(stats!.firstObservedAt)}
                  </td>
                  <td className="whitespace-nowrap px-3 py-2 text-xs text-muted">
                    {stats!.lastObservedAt && formatTimestamp(stats!.lastObservedAt)}
                  </td>
                  <td className="px-3 py-2 text-right">
                    <Link
                      href={`/nfl/games/${game.id}/history`}
                      className="text-accent hover:underline"
                    >
                      Replay →
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
