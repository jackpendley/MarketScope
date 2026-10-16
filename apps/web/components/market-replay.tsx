"use client";

import { useMemo, useState } from "react";
import { BOARD_BOOKS, formatAmericanOdds, formatPoint, type Market } from "@marketscope/shared";
import { HistoryCharts, type ChartSeries } from "@/components/history-charts";
import { buildReplayView, snapshotTimes, type ReplayCell } from "@/lib/replay-view";
import type { NamedMovement, ReplaySelectionData } from "@/lib/server/replay";

const timeFormat = new Intl.DateTimeFormat("en-US", {
  timeZone: "America/New_York",
  weekday: "short",
  month: "short",
  day: "numeric",
  hour: "numeric",
  minute: "2-digit",
  timeZoneName: "short",
});
const fmt = (iso: string) => timeFormat.format(new Date(iso));

function formatAge(minutes: number): string {
  if (minutes < 60) return `${Math.round(minutes)}m`;
  const h = Math.floor(minutes / 60);
  return h < 48 ? `${h}h` : `${Math.floor(h / 24)}d ${h % 24}h`;
}

export interface MarketReplayProps {
  market: Market;
  selections: ReplaySelectionData[];
  series: ChartSeries[];
  movements: NamedMovement[];
  homeTeamShort: string;
  awayTeamShort: string;
  pointLabel: string;
  priceLabel: string;
  freshnessMinutes: number;
}

export function MarketReplay({
  market,
  selections,
  series,
  movements,
  homeTeamShort,
  awayTeamShort,
  pointLabel,
  priceLabel,
  freshnessMinutes,
}: MarketReplayProps) {
  const times = useMemo(() => snapshotTimes(selections), [selections]);
  const [index, setIndex] = useState(times.length - 1);
  const at = times[Math.min(Math.max(index, 0), times.length - 1)];
  const view = useMemo(
    () =>
      at ? buildReplayView(selections, { at, books: BOARD_BOOKS, market, freshnessMinutes }) : null,
    [selections, at, market, freshnessMinutes],
  );
  if (!at || !view) return null;

  const jumpTo = (iso: string) => {
    const i = times.indexOf(iso);
    if (i >= 0) setIndex(i);
  };
  const isLatest = index === times.length - 1;
  const past = movements.filter((m) => m.intervalEnd <= at);

  return (
    <div className="space-y-5">
      <section
        aria-label="Replay controls"
        className="space-y-3 rounded-lg border border-line bg-surface px-4 py-3"
      >
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <div>
            <div className="text-xs uppercase tracking-wide text-muted">Market as observed at</div>
            <div className="text-lg font-medium tabular-nums" data-testid="replay-time">
              {fmt(at)}
            </div>
          </div>
          <div className="text-sm text-muted">
            Snapshot {index + 1} of {times.length}
            {isLatest && (
              <span className="ml-2 rounded bg-accent/15 px-1.5 py-0.5 text-xs text-accent">
                latest
              </span>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setIndex((i) => Math.max(0, i - 1))}
            disabled={index === 0}
            className="rounded border border-line px-2.5 py-1 text-sm disabled:opacity-40"
            aria-label="Previous snapshot"
          >
            ◀
          </button>
          <input
            type="range"
            min={0}
            max={times.length - 1}
            step={1}
            value={index}
            onChange={(e) => setIndex(Number(e.target.value))}
            aria-label="Replay time"
            aria-valuetext={fmt(at)}
            className="h-2 flex-1 cursor-pointer accent-accent"
          />
          <button
            type="button"
            onClick={() => setIndex((i) => Math.min(times.length - 1, i + 1))}
            disabled={isLatest}
            className="rounded border border-line px-2.5 py-1 text-sm disabled:opacity-40"
            aria-label="Next snapshot"
          >
            ▶
          </button>
          <button
            type="button"
            onClick={() => setIndex(times.length - 1)}
            disabled={isLatest}
            className="rounded border border-line px-2.5 py-1 text-sm disabled:opacity-40"
          >
            Latest
          </button>
        </div>
        <p className="text-xs text-subtle">
          Each book shows its latest observation at or before this time. Books not observed in the
          previous {freshnessMinutes / 60} hours are shown as stale and excluded from consensus.
          Prices are never carried forward silently.
        </p>
      </section>

      <section
        aria-label="Market state at replay time"
        className="overflow-hidden rounded-lg border border-line bg-surface"
      >
        <div className="flex flex-wrap items-baseline gap-x-6 gap-y-1 border-b border-line px-4 py-2 text-sm">
          {market === "h2h" ? (
            <span className="text-muted">Moneylines have no line to form a consensus.</span>
          ) : view.consensus ? (
            <>
              <span data-testid="replay-consensus">
                <span className="text-muted">
                  Consensus (median, {view.consensus.books} fresh books):{" "}
                </span>
                <span className="font-mono tabular-nums">
                  {market === "spreads" ? `${homeTeamShort} ` : ""}
                  {formatPoint(view.consensus.point, market)}
                </span>
              </span>
              {view.dispersion && (
                <span className="text-muted">
                  Range {view.dispersion.range} · σ {view.dispersion.stdDev} ·{" "}
                  {view.dispersion.booksOffCenter} book
                  {view.dispersion.booksOffCenter === 1 ? "" : "s"} ≥ 0.5 pts off consensus
                </span>
              )}
            </>
          ) : (
            <span className="text-muted" data-testid="replay-consensus">
              No consensus: {view.freshBooks} fresh book{view.freshBooks === 1 ? "" : "s"} (need 3).
            </span>
          )}
        </div>
        <div className="relative overflow-x-auto">
          <table className="w-full min-w-[640px] text-sm">
            <thead>
              <tr className="text-left text-xs text-muted">
                <th scope="col" className="px-4 py-2 font-medium">
                  Side
                </th>
                {view.columns.map((c) => (
                  <th key={c.book.id} scope="col" className="px-3 py-2 text-right font-medium">
                    <div className="text-fg">{c.book.displayName}</div>
                    {c.fallbackLabel && (
                      <div className="font-normal text-warn">{c.fallbackLabel}</div>
                    )}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {view.rows.map((row) => (
                <tr key={row.selection} className="border-t border-line/60">
                  <th scope="row" className="whitespace-nowrap px-4 py-2 text-left font-normal">
                    {row.label}
                  </th>
                  {view.columns.map((c) => (
                    <td key={c.book.id} className="px-3 py-2 text-right font-mono tabular-nums">
                      <ReplayCellView cell={row.cells[c.book.id]!} market={market} />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <HistoryCharts
        series={series}
        market={market}
        pointLabel={pointLabel}
        priceLabel={priceLabel}
        cursor={Date.parse(at)}
      />

      <section className="space-y-2">
        <h2 className="text-sm font-medium uppercase tracking-wide text-muted">
          Movement timeline ({past.length} of {movements.length} up to the replay time)
        </h2>
        {movements.length === 0 ? (
          <p className="text-sm text-muted">No movements observed.</p>
        ) : (
          <ol className="divide-y divide-line/60 overflow-hidden rounded-lg border border-line bg-surface text-sm">
            {[...movements].reverse().map((m, i) => {
              const future = m.intervalEnd > at;
              const current = m.intervalEnd === at;
              return (
                <li key={`${m.bookmakerKey}-${m.intervalEnd}-${i}`}>
                  <button
                    type="button"
                    onClick={() => jumpTo(m.intervalEnd)}
                    className={`flex w-full flex-wrap items-baseline gap-x-4 gap-y-1 px-4 py-2 text-left hover:bg-surface-raised ${
                      future ? "opacity-45" : ""
                    } ${current ? "bg-accent/10" : ""}`}
                    aria-current={current ? "true" : undefined}
                  >
                    <span className="w-40 shrink-0 font-medium">{m.displayName}</span>
                    <span className="font-mono tabular-nums">
                      {quote(m.fromPoint, m.fromPrice, market)}{" "}
                      <span className="text-subtle">→</span> {quote(m.toPoint, m.toPrice, market)}
                    </span>
                    <span className="text-xs text-muted">
                      {directionLabel(m, homeTeamShort, awayTeamShort)}
                    </span>
                    {m.keyNumbers.map((k) => (
                      <span
                        key={`${k.signedKey}-${k.kind}`}
                        className="rounded bg-warn/15 px-1.5 py-0.5 text-xs text-warn"
                        title="NFL key number (most common margins of victory). Descriptive only."
                      >
                        {k.kind === "crossed"
                          ? "crossed"
                          : k.kind === "landed-on"
                            ? "landed on"
                            : "left"}{" "}
                        {formatPoint(k.signedKey, "spreads")}
                      </span>
                    ))}
                    {m.acrossGap && (
                      <span className="rounded bg-warn/15 px-1.5 py-0.5 text-xs text-warn">
                        across gap
                      </span>
                    )}
                    <span className="ml-auto text-xs text-subtle">
                      between {fmt(m.intervalStart)} and {fmt(m.intervalEnd)}
                    </span>
                  </button>
                </li>
              );
            })}
          </ol>
        )}
      </section>
    </div>
  );
}

function quote(point: number | null, price: number, market: Market) {
  const p = formatPoint(point, market);
  return `${p ? `${p} ` : ""}${formatAmericanOdds(price)}`;
}

function directionLabel(m: NamedMovement, homeShort: string, awayShort: string): string {
  switch (m.direction) {
    case "price-only":
      return "price only";
    case "total-up":
      return `total up ${Math.abs(m.pointDelta ?? 0)}`;
    case "total-down":
      return `total down ${Math.abs(m.pointDelta ?? 0)}`;
    case "toward-home":
      return `${Math.abs(m.pointDelta ?? 0)} pt toward ${homeShort}`;
    case "toward-away":
      return `${Math.abs(m.pointDelta ?? 0)} pt toward ${awayShort}`;
  }
}

function ReplayCellView({ cell, market }: { cell: ReplayCell; market: Market }) {
  if (cell.status === "none" || cell.americanPrice === null) {
    return <span className="font-sans text-xs text-subtle">no data yet</span>;
  }
  const value = (
    <>
      {cell.point !== null && market !== "h2h" && (
        <span className="mr-1.5">{formatPoint(cell.point, market)}</span>
      )}
      {formatAmericanOdds(cell.americanPrice)}
    </>
  );
  if (cell.status === "stale") {
    return (
      <span
        className="italic text-subtle"
        title={cell.observedAt ? `Last seen ${fmt(cell.observedAt)}` : undefined}
      >
        {value}
        <span className="ml-1.5 font-sans text-xs not-italic">
          ({formatAge(cell.ageMinutes ?? 0)} old)
        </span>
      </span>
    );
  }
  return <span>{value}</span>;
}
