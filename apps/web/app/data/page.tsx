import type { Metadata } from "next";
import Link from "next/link";
import { connection } from "next/server";
import { footballDataStatus, gameCoverage, latestCompletedRun, recentRuns } from "@marketscope/db";
import { formatAge } from "@marketscope/shared";
import { DataUnavailable, Notice } from "@/components/data-states";
import {
  collectionStatus,
  COVERAGE_COLUMNS,
  coverageCell,
  FEED_COLUMNS,
  SOURCE_LABELS,
  summarizeCoverage,
  type CoverageLevel,
} from "@/lib/coverage-view";
import { isConnectionError } from "@/lib/server/api";
import { DatabaseNotConfiguredError, getDb } from "@/lib/server/db";
import { formatTimestamp } from "@/lib/time";

export const metadata: Metadata = { title: "Data Coverage" };

const DAY = 86_400_000;
const MAX_GAMES = 400;

// One hue, light → strong, always paired with the percentage text (never color alone).
const LEVEL_CLASS: Record<CoverageLevel, string> = {
  none: "text-subtle",
  low: "bg-accent/10 text-fg",
  partial: "bg-accent/25 text-fg",
  full: "bg-accent/40 text-fg",
};

const pct = (share: number) => `${Math.round(share * 100)}%`;

export default async function DataCoveragePage() {
  await connection();
  const now = new Date();

  let data;
  try {
    const db = getDb();
    const from = new Date(now.getTime() - 150 * DAY).toISOString();
    const to = new Date(now.getTime() + 14 * DAY).toISOString();
    const [rows, latest, runs, football] = await Promise.all([
      gameCoverage(db, { from, to, feedColumns: FEED_COLUMNS, limit: MAX_GAMES }),
      latestCompletedRun(db),
      recentRuns(db, 12),
      footballDataStatus(db, { from, to, limit: 20 }),
    ]);
    data = { rows, latest, runs, football };
  } catch (err) {
    if (err instanceof DatabaseNotConfiguredError || isConnectionError(err))
      return <DataUnavailable />;
    throw err;
  }

  const { rows, latest, runs, football } = data;
  const summary = summarizeCoverage(rows);
  const health = collectionStatus(latest, now);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">Data Coverage</h1>
        <p className="max-w-3xl text-sm text-muted">
          What history MarketScope holds, where it came from, and how complete it is. Coverage is
          the share of a game&apos;s pregame snapshots in which a book posted a spread. Counts only:
          no prices are shown here.
        </p>
      </div>

      {summary.gamesBySource.some(([s]) => s === "synthetic") && (
        <Notice tone="warn" title="Synthetic data: not real odds.">
          This database contains generated demo history for development and testing.
        </Notice>
      )}

      <section aria-labelledby="collection" className="space-y-2">
        <h2 id="collection" className="text-sm font-medium uppercase tracking-wide text-muted">
          Live collection
        </h2>
        <div className="flex flex-wrap items-start gap-x-8 gap-y-3 rounded-lg border border-line bg-surface px-4 py-3 text-sm">
          <div>
            <div className="text-xs text-muted">Status</div>
            <div className="mt-0.5 font-medium" data-status={health.status}>
              {health.status === "ok" && <span className="text-best">● On schedule</span>}
              {health.status === "behind" && <span className="text-warn">▲ Behind schedule</span>}
              {health.status === "no-data" && (
                <span className="text-muted">○ No live runs yet</span>
              )}
            </div>
          </div>
          {latest && (
            <div>
              <div className="text-xs text-muted">Last successful run</div>
              <div className="mt-0.5">
                <time dateTime={latest.startedAt}>{formatTimestamp(latest.startedAt)}</time>{" "}
                <span className="text-muted">· {formatAge(health.ageMinutes ?? 0)} ago</span>
              </div>
            </div>
          )}
          <div>
            <div className="text-xs text-muted">Schedule</div>
            <div className="mt-0.5">Every 6 hours (00:07, 06:07, 12:07, 18:07 UTC)</div>
          </div>
          {runs.length > 0 && (
            <div className="min-w-0">
              <div className="text-xs text-muted">Recent runs (newest first)</div>
              <ol className="mt-1 flex flex-wrap gap-1" aria-label="Recent live runs">
                {runs.map((r) => (
                  <li
                    key={r.id}
                    title={`${formatTimestamp(r.startedAt)} · ${r.status}${r.errorCode ? ` (${r.errorCode})` : ""}`}
                    className={`rounded px-1.5 py-0.5 text-xs ${
                      r.status === "completed"
                        ? "bg-best/15 text-best"
                        : r.status === "failed"
                          ? "bg-danger/15 text-danger"
                          : "bg-surface-raised text-muted"
                    }`}
                  >
                    {r.status === "completed" ? "✓" : r.status === "failed" ? "✕" : "…"}
                    <span className="sr-only"> {r.status}</span>
                  </li>
                ))}
              </ol>
            </div>
          )}
        </div>
      </section>

      <section aria-labelledby="summary" className="space-y-2">
        <h2 id="summary" className="text-sm font-medium uppercase tracking-wide text-muted">
          Stored history
        </h2>
        <dl className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <Stat label="Games with history" value={summary.games.toLocaleString()}>
            {summary.gamesBySource.map(([source, n]) => (
              <div key={source}>
                {SOURCE_LABELS[source] ?? source}: {n}
              </div>
            ))}
          </Stat>
          <Stat label="Pregame snapshots" value={summary.snapshots.toLocaleString()}>
            Summed over games
          </Stat>
          <Stat label="Signals" value={summary.signals.toLocaleString()}>
            <Link href="/signals?window=30d" className="text-accent hover:underline">
              Signal Lab →
            </Link>
          </Stat>
          <Stat
            label="Consensus-eligible games"
            value={summary.consensusEligibleGames.toLocaleString()}
          >
            At least 3 board books posted a spread
          </Stat>
        </dl>
      </section>

      <section aria-labelledby="football" className="space-y-2">
        <h2 id="football" className="text-sm font-medium uppercase tracking-wide text-muted">
          Football data (nflverse)
        </h2>
        {football.games === 0 ? (
          <Notice title="No football data loaded yet.">
            The nflverse pipeline (<code>apps/football</code>) loads schedules and results.
          </Notice>
        ) : (
          <>
            <dl className="grid grid-cols-2 gap-3 md:grid-cols-4">
              <Stat label="Games stored" value={football.games.toLocaleString()}>
                Seasons {football.firstSeason}–{football.lastSeason} ·{" "}
                {football.finalGames.toLocaleString()} final
              </Stat>
              <Stat
                label="Odds events linked"
                value={`${football.linkedEvents} / ${football.events}`}
              >
                Same teams and orientation, kickoff within 36 h
              </Stat>
              {football.latestRun && (
                <Stat label="Last football ingest" value={football.latestRun.status}>
                  <time dateTime={football.latestRun.startedAt}>
                    {formatTimestamp(football.latestRun.startedAt)}
                  </time>
                  {football.latestRun.sourceVersion && (
                    <div className="truncate" title={football.latestRun.sourceVersion}>
                      {football.latestRun.sourceVersion}
                    </div>
                  )}
                </Stat>
              )}
            </dl>
            {football.unlinked.length > 0 && (
              <Notice
                tone="warn"
                title={`${football.unlinked.length} odds event(s) not linked to a game.`}
              >
                <ul className="mt-1 space-y-0.5">
                  {football.unlinked.map((u) => (
                    <li key={u.eventId}>
                      {u.awayTeam} @ {u.homeTeam} · {formatTimestamp(u.commenceTime)}
                    </li>
                  ))}
                </ul>
              </Notice>
            )}
          </>
        )}
      </section>

      <section aria-labelledby="games" className="space-y-2">
        <div className="flex flex-wrap items-end justify-between gap-2">
          <h2 id="games" className="text-sm font-medium uppercase tracking-wide text-muted">
            Coverage by game
          </h2>
          <p className="flex flex-wrap items-center gap-2 text-xs text-muted" aria-hidden="true">
            Share of snapshots with a spread:
            <span className={`rounded px-1.5 ${LEVEL_CLASS.full}`}>≥ 90%</span>
            <span className={`rounded px-1.5 ${LEVEL_CLASS.partial}`}>50–89%</span>
            <span className={`rounded px-1.5 ${LEVEL_CLASS.low}`}>&lt; 50%</span>
            <span className={`rounded px-1.5 ${LEVEL_CLASS.none}`}>— not in feed</span>
          </p>
        </div>

        {rows.length === 0 ? (
          <Notice title="No stored history yet.">
            Coverage appears after the collector or an import runs.
          </Notice>
        ) : (
          <div className="relative overflow-x-auto rounded-lg border border-line bg-surface">
            <table className="w-full min-w-[960px] text-sm">
              <caption className="sr-only">
                Pregame spread coverage per game and sportsbook, newest kickoff first
              </caption>
              <thead>
                <tr className="text-left text-xs text-muted">
                  <th scope="col" className="px-4 py-2 font-medium">
                    Game
                  </th>
                  <th scope="col" className="px-3 py-2 font-medium">
                    Kickoff
                  </th>
                  <th scope="col" className="px-3 py-2 font-medium">
                    Source
                  </th>
                  <th scope="col" className="px-3 py-2 text-right font-medium">
                    Snapshots
                  </th>
                  {COVERAGE_COLUMNS.map((c) => (
                    <th
                      key={c.key}
                      scope="col"
                      className="px-2 py-2 text-center font-medium"
                      title={c.reference ? "Reference book: stored, never in consensus" : undefined}
                    >
                      {c.label}
                      {c.reference && <span className="block text-[10px] text-subtle">ref.</span>}
                    </th>
                  ))}
                  <th scope="col" className="px-3 py-2 text-right font-medium">
                    Signals
                  </th>
                  <th scope="col" className="px-3 py-2">
                    <span className="sr-only">Replay</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.eventId} className="border-t border-line/60">
                    <th scope="row" className="whitespace-nowrap px-4 py-1.5 text-left font-normal">
                      {r.awayTeam.split(" ").at(-1)} <span className="text-muted">@</span>{" "}
                      {r.homeTeam.split(" ").at(-1)}
                    </th>
                    <td className="whitespace-nowrap px-3 py-1.5 text-muted">
                      {formatTimestamp(r.commenceTime)}
                    </td>
                    <td className="whitespace-nowrap px-3 py-1.5 text-xs text-muted">
                      {r.sources.map((s) => SOURCE_LABELS[s] ?? s).join(", ")}
                    </td>
                    <td
                      className="px-3 py-1.5 text-right tabular-nums"
                      title={`${formatTimestamp(r.firstObservedAt)} → ${formatTimestamp(r.lastObservedAt)}`}
                    >
                      {r.snapshots}
                    </td>
                    {COVERAGE_COLUMNS.map((c) => {
                      const { share, level } = coverageCell(
                        r.snapshots,
                        r.snapshotsByColumn[c.key],
                      );
                      return (
                        <td key={c.key} className="px-1 py-1">
                          <span
                            className={`block rounded px-1.5 py-0.5 text-center text-xs tabular-nums ${LEVEL_CLASS[level]}`}
                            title={
                              level === "none"
                                ? `${c.label}: no spread quotes stored`
                                : `${c.label}: ${r.snapshotsByColumn[c.key]} of ${r.snapshots} snapshots`
                            }
                          >
                            {level === "none" ? "—" : pct(share)}
                          </span>
                        </td>
                      );
                    })}
                    <td className="px-3 py-1.5 text-right tabular-nums">{r.signals}</td>
                    <td className="whitespace-nowrap px-3 py-1.5 text-right">
                      <Link
                        href={`/nfl/games/${r.eventId}/history`}
                        className="text-accent hover:underline"
                      >
                        Replay →
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr className="border-t border-line text-xs text-muted">
                  <th scope="row" colSpan={4} className="px-4 py-2 text-left font-medium">
                    Average, over games each book posted
                  </th>
                  {COVERAGE_COLUMNS.map((c) => {
                    const avg = summary.columnAverages[c.key];
                    return (
                      <td key={c.key} className="px-2 py-2 text-center tabular-nums">
                        {avg == null ? "—" : pct(avg)}
                      </td>
                    );
                  })}
                  <td colSpan={2} />
                </tr>
              </tfoot>
            </table>
          </div>
        )}
        <p className="text-xs text-subtle">
          Games kicking off in the last 150 days or next 14 days (up to {MAX_GAMES}). Imported games
          use derived 6-hourly snapshots and exclude BetMGM (ADR-026). Live snapshots lack Caesars
          on the current data plan.
        </p>
      </section>
    </div>
  );
}

function Stat({
  label,
  value,
  children,
}: {
  label: string;
  value: string;
  children?: React.ReactNode;
}) {
  return (
    <div className="rounded-lg border border-line bg-surface px-4 py-3">
      <dt className="text-xs text-muted">{label}</dt>
      <dd className="mt-1 text-2xl font-semibold tabular-nums">{value}</dd>
      {children && <dd className="mt-1 text-xs text-muted">{children}</dd>}
    </div>
  );
}
