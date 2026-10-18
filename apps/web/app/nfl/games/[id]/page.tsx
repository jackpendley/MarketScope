import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { connection } from "next/server";
import { MARKET_LABELS } from "@marketscope/shared";
import { DataUnavailable, Notice, SnapshotMeta } from "@/components/data-states";
import { EventOddsTable } from "@/components/event-odds-table";
import { feedCoverage } from "@/lib/game-data";
import { gameIdSchema } from "@/lib/params";
import { isConnectionError } from "@/lib/server/api";
import { DatabaseNotConfiguredError, getDb, quoteFreshnessMinutes } from "@/lib/server/db";
import { hasSyntheticData, loadGameDetail, type GameDetail } from "@/lib/server/games";
import { describeSignal, signalTitle } from "@/lib/signal-format";
import {
  listSignals,
  matchupForEvent,
  ratingVersion,
  type Matchup,
  type SignalRow,
} from "@marketscope/db";
import { ModelPanel } from "@/components/model-panel";
import { formatKickoff, formatTimestamp } from "@/lib/time";

export const metadata: Metadata = { title: "Game odds" };

export default async function GamePage(props: PageProps<"/nfl/games/[id]">) {
  await connection();
  const { id } = await props.params;
  if (!gameIdSchema.safeParse(id).success) notFound();

  let detail: GameDetail | null;
  let signals: SignalRow[] = [];
  let matchup: Matchup | null = null;
  let modelVersion: string | null = null;
  try {
    const db = getDb();
    detail = await loadGameDetail(db, id);
    if (detail) {
      [signals, modelVersion] = await Promise.all([
        listSignals(db, { eventId: id, limit: 8 }),
        ratingVersion(db),
      ]);
      if (modelVersion) matchup = await matchupForEvent(db, { version: modelVersion, eventId: id });
    }
  } catch (err) {
    if (err instanceof DatabaseNotConfiguredError || isConnectionError(err))
      return <DataUnavailable />;
    throw err;
  }
  if (!detail) notFound();

  const { game, board, stats, quotes } = detail;
  const now = new Date();
  const coverage = feedCoverage(quotes);

  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <Link href="/nfl" className="text-sm text-muted hover:text-accent">
          ← Odds board
        </Link>
        <h1 className="text-xl font-semibold tracking-tight">
          {game.awayTeam} <span className="text-muted">@</span> {game.homeTeam}
        </h1>
        <p className="text-sm text-muted">
          Kickoff <time dateTime={game.commenceTime}>{formatKickoff(game.commenceTime)}</time>
          {" · "}Season {game.season}
          {game.week !== null && ` · Week ${game.week}`}
          {board.latestObservedAt && (
            <>
              {" · "}
              <SnapshotMeta
                observedAt={board.latestObservedAt}
                recentMinutes={quoteFreshnessMinutes()}
                now={now}
              />
            </>
          )}
        </p>
      </div>

      {hasSyntheticData([detail]) && (
        <Notice tone="warn" title="Synthetic data: not real odds.">
          This database contains generated demo history for development and testing.
        </Notice>
      )}

      {quotes.length === 0 ? (
        <p className="text-sm text-muted">No odds have been collected for this game.</p>
      ) : (
        <EventOddsTable board={board} />
      )}

      {matchup && modelVersion && (
        <ModelPanel matchup={matchup} consensus={board.consensus} version={modelVersion} />
      )}

      <section className="space-y-2">
        <h2 className="text-sm font-medium uppercase tracking-wide text-muted">Feed coverage</h2>
        <div className="relative overflow-x-auto rounded-lg border border-line bg-surface">
          <table className="w-full min-w-[640px] text-sm">
            <thead>
              <tr className="text-left text-xs text-muted">
                <th scope="col" className="px-4 py-2 font-medium">
                  Feed
                </th>
                <th scope="col" className="px-3 py-2 font-medium">
                  Status
                </th>
                <th scope="col" className="px-3 py-2 font-medium">
                  Markets
                </th>
                <th scope="col" className="px-3 py-2 font-medium">
                  Last observed by us
                </th>
                <th scope="col" className="px-3 py-2 font-medium">
                  Last book update
                </th>
              </tr>
            </thead>
            <tbody>
              {coverage.map((f) => (
                <tr key={f.bookmakerKey} className="border-t border-line/60">
                  <td className="px-4 py-2">
                    {f.displayName} <code className="text-xs text-subtle">{f.bookmakerKey}</code>
                  </td>
                  <td className="px-3 py-2">
                    <span
                      className={
                        f.status === "current"
                          ? "text-best"
                          : f.status === "stale"
                            ? "text-warn"
                            : "text-subtle"
                      }
                    >
                      {f.status === "current"
                        ? "in latest snapshot"
                        : f.status === "stale"
                          ? "missing from latest snapshot"
                          : "never returned"}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-muted">
                    {f.markets.length > 0 ? f.markets.map((m) => MARKET_LABELS[m]).join(", ") : "—"}
                  </td>
                  <td className="px-3 py-2 font-mono text-xs tabular-nums text-muted">
                    {f.lastObservedAt ? formatTimestamp(f.lastObservedAt) : "—"}
                  </td>
                  <td className="px-3 py-2 font-mono text-xs tabular-nums text-muted">
                    {f.lastBookUpdateAt ? formatTimestamp(f.lastBookUpdateAt) : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="text-xs text-subtle">
          A feed missing from a snapshot means the provider didn&apos;t return it, not necessarily
          that the sportsbook stopped offering the market. Caesars requires a paid data plan.
        </p>
      </section>

      <section className="space-y-2">
        <div className="flex items-baseline justify-between">
          <h2 className="text-sm font-medium uppercase tracking-wide text-muted">Recent signals</h2>
          <Link
            href={`/signals?event=${game.id}&window=30d`}
            className="text-sm text-accent hover:underline"
          >
            All signals for this game →
          </Link>
        </div>
        {signals.length === 0 ? (
          <p className="text-sm text-muted">No signals detected yet.</p>
        ) : (
          <ul className="divide-y divide-line/60 rounded-lg border border-line bg-surface text-sm">
            {signals.map((s) => (
              <li key={s.id} className="flex flex-wrap items-baseline gap-x-3 gap-y-1 px-4 py-2">
                <span className="rounded bg-surface-raised px-1.5 py-0.5 text-xs">
                  {signalTitle(s.type)}
                </span>
                <span>{describeSignal(s)}</span>
                <span className="ml-auto text-xs text-subtle">{formatTimestamp(s.detectedAt)}</span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-line bg-surface px-4 py-3 text-sm">
        <div>
          <h2 className="font-medium">Line history &amp; replay</h2>
          <p className="text-muted">
            {stats.observations > 0 && stats.firstObservedAt ? (
              <>
                {stats.observations.toLocaleString()} observations across {stats.snapshots} snapshot
                {stats.snapshots === 1 ? "" : "s"} since {formatTimestamp(stats.firstObservedAt)}{" "}
                (first observed by MarketScope, not necessarily the opening line).
              </>
            ) : (
              "No observations stored yet."
            )}
          </p>
        </div>
        {stats.observations > 0 && (
          <Link
            href={`/nfl/games/${game.id}/history`}
            className="rounded border border-line px-3 py-1 text-accent hover:border-accent"
          >
            Open market replay →
          </Link>
        )}
      </section>
    </div>
  );
}
