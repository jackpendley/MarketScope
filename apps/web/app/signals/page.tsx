import type { Metadata } from "next";
import Link from "next/link";
import { connection } from "next/server";
import { databaseHasSyntheticData, getGame, listSignals, type SignalRow } from "@marketscope/db";
import { SIGNAL_DEFINITIONS, SIGNAL_TYPES, type SignalType } from "@marketscope/shared";
import { DataUnavailable, Notice } from "@/components/data-states";
import { SIGNAL_WINDOWS, type SignalWindow } from "@/lib/params";
import { isConnectionError } from "@/lib/server/api";
import { DatabaseNotConfiguredError, getDb } from "@/lib/server/db";
import { describeSignal, signalTitle } from "@/lib/signal-format";
import { formatTimestamp } from "@/lib/time";

export const metadata: Metadata = { title: "Signal Lab" };

const first = (v: string | string[] | undefined) => (Array.isArray(v) ? v[0] : v);
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const DAY = 24 * 3_600_000;

function replayHref(s: SignalRow): string {
  const selection = s.selection ?? (s.market === "totals" ? "OVER" : "HOME");
  const params = new URLSearchParams({ market: s.market, selection, at: s.detectedAt });
  return `/nfl/games/${s.eventId}/history?${params}`;
}

export default async function SignalLabPage(props: PageProps<"/signals">) {
  await connection();
  const sp = await props.searchParams;
  const typeParam = first(sp.type) ?? "";
  const type = (SIGNAL_TYPES as readonly string[]).includes(typeParam)
    ? (typeParam as SignalType)
    : null;
  const windowParam = (first(sp.window) ?? "7d") as SignalWindow;
  const window: SignalWindow = windowParam in SIGNAL_WINDOWS ? windowParam : "7d";
  const eventParam = first(sp.event);
  const eventId = eventParam && UUID.test(eventParam) ? eventParam : undefined;
  const now = new Date();

  let rows: SignalRow[];
  let eventLabel: string | null = null;
  let synthetic = false;
  try {
    const db = getDb();
    rows = await listSignals(db, {
      from: new Date(now.getTime() - SIGNAL_WINDOWS[window] * DAY).toISOString(),
      types: type ? [type] : undefined,
      eventId,
      limit: 300,
    });
    synthetic = await databaseHasSyntheticData(db);
    if (eventId) {
      const game = await getGame(db, eventId);
      eventLabel = game ? `${game.awayTeam} @ ${game.homeTeam}` : null;
    }
  } catch (err) {
    if (err instanceof DatabaseNotConfiguredError || isConnectionError(err))
      return <DataUnavailable />;
    throw err;
  }

  const counts = new Map<string, number>();
  for (const r of rows) counts.set(r.type, (counts.get(r.type) ?? 0) + 1);

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">Signal Lab</h1>
        <p className="max-w-3xl text-sm text-muted">
          Reproducible, versioned detections of observable market behavior, each backed by the
          stored observations that produced it. Signals describe what the market did. They do not
          identify professional betting activity and are not betting advice.
        </p>
      </div>

      {synthetic && (
        <Notice tone="warn" title="Synthetic data: not real odds.">
          This database contains generated demo history for development and testing.
        </Notice>
      )}

      <form
        method="get"
        className="flex flex-wrap items-end gap-x-5 gap-y-3 rounded-lg border border-line bg-surface px-4 py-3 text-sm"
      >
        <label className="flex flex-col gap-1">
          <span className="text-xs text-muted">Signal type</span>
          <select
            name="type"
            defaultValue={type ?? ""}
            className="rounded border border-line bg-canvas px-2 py-1 text-fg"
          >
            <option value="">All types</option>
            {SIGNAL_TYPES.map((t) => (
              <option key={t} value={t}>
                {SIGNAL_DEFINITIONS[t].title}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-xs text-muted">Detected within</span>
          <select
            name="window"
            defaultValue={window}
            className="rounded border border-line bg-canvas px-2 py-1 text-fg"
          >
            <option value="24h">24 hours</option>
            <option value="3d">3 days</option>
            <option value="7d">7 days</option>
            <option value="30d">30 days</option>
          </select>
        </label>
        {eventId && <input type="hidden" name="event" value={eventId} />}
        <button
          type="submit"
          className="rounded bg-accent px-3 py-1 font-medium text-canvas hover:bg-accent/90"
        >
          Apply
        </button>
        {(type || eventId || window !== "7d") && (
          <a
            href="/signals"
            className="rounded border border-line px-3 py-1 text-muted hover:text-fg"
          >
            Reset
          </a>
        )}
      </form>

      {eventId && (
        <p className="text-sm text-muted">
          Showing signals for <span className="text-fg">{eventLabel ?? "an unknown game"}</span>.{" "}
          <Link href={`/nfl/games/${eventId}`} className="text-accent hover:underline">
            Game odds →
          </Link>
        </p>
      )}

      <div className="flex flex-wrap gap-2 text-xs" aria-label="Signal counts by type">
        {SIGNAL_TYPES.map((t) => (
          <span key={t} className="rounded border border-line bg-surface px-2 py-1 text-muted">
            {SIGNAL_DEFINITIONS[t].title}:{" "}
            <span className="tabular-nums text-fg">{counts.get(t) ?? 0}</span>
          </span>
        ))}
      </div>

      {rows.length === 0 ? (
        <Notice title="No signals in this window.">
          Signals are recomputed after every collection run.
        </Notice>
      ) : (
        <div className="relative overflow-x-auto rounded-lg border border-line bg-surface">
          <table className="w-full min-w-[760px] text-sm">
            <thead>
              <tr className="text-left text-xs text-muted">
                <th scope="col" className="px-4 py-2 font-medium">
                  Detected
                </th>
                <th scope="col" className="px-3 py-2 font-medium">
                  Signal
                </th>
                <th scope="col" className="px-3 py-2 font-medium">
                  Game
                </th>
                <th scope="col" className="px-3 py-2 font-medium">
                  What was observed
                </th>
                <th scope="col" className="px-3 py-2" />
              </tr>
            </thead>
            <tbody>
              {rows.map((s) => (
                <tr key={s.id} className="border-t border-line/60 align-top">
                  <td className="whitespace-nowrap px-4 py-2 text-xs text-muted">
                    {formatTimestamp(s.detectedAt)}
                    {s.windowStart !== s.windowEnd && (
                      <div
                        className="text-subtle"
                        title="The change happened somewhere in this interval"
                      >
                        since {formatTimestamp(s.windowStart)}
                      </div>
                    )}
                  </td>
                  <td className="whitespace-nowrap px-3 py-2">
                    <span
                      className="rounded bg-surface-raised px-1.5 py-0.5 text-xs"
                      data-signal-type={s.type}
                    >
                      {signalTitle(s.type)}
                    </span>
                    <span className="ml-1 text-xs text-subtle">v{s.version}</span>
                  </td>
                  <td className="whitespace-nowrap px-3 py-2">
                    <Link href={`/signals?event=${s.eventId}`} className="hover:text-accent">
                      {s.awayTeam.split(" ").at(-1)} @ {s.homeTeam.split(" ").at(-1)}
                    </Link>
                  </td>
                  <td className="px-3 py-2">
                    {describeSignal(s)}
                    {Boolean((s.details as { acrossGap?: boolean }).acrossGap) && (
                      <span className="ml-2 rounded bg-warn/15 px-1.5 py-0.5 text-xs text-warn">
                        across gap
                      </span>
                    )}
                    <div className="text-xs text-subtle">
                      Evidence: {s.evidence.length} observation{s.evidence.length === 1 ? "" : "s"}
                    </div>
                  </td>
                  <td className="whitespace-nowrap px-3 py-2 text-right">
                    <Link href={replayHref(s)} className="text-accent hover:underline">
                      Replay →
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <section className="space-y-3">
        <h2 className="text-sm font-medium uppercase tracking-wide text-muted">
          Definitions (algorithm v1)
        </h2>
        <dl className="grid gap-3 md:grid-cols-2">
          {SIGNAL_TYPES.map((t) => {
            const d = SIGNAL_DEFINITIONS[t];
            return (
              <div key={t} className="rounded-lg border border-line bg-surface px-4 py-3 text-sm">
                <dt className="font-medium">
                  {d.title}{" "}
                  <span className="text-xs font-normal text-subtle">
                    ({d.type}, v{d.version})
                  </span>
                </dt>
                <dd className="mt-1 text-muted">{d.definition}</dd>
                <dd className="mt-1 text-xs text-subtle">Limitations: {d.limitations}</dd>
              </div>
            );
          })}
        </dl>
      </section>
    </div>
  );
}
