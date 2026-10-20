"use client";

import { useMemo, useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  type TooltipContentProps,
} from "recharts";
import type { LineMoveRow } from "@marketscope/db";
import { formatPoint, type Market, type Selection } from "@marketscope/shared";
import {
  axisTicks,
  FEED_COLORS,
  formatScaledAmerican,
  type ChartField,
  type ChartRow,
} from "@/lib/history-chart";
import {
  LINE_MOVE_RANGES,
  lineMoveChartRows,
  lineMoveSummary,
  movesByBook,
  pointMoveLog,
  type LineMoveRange,
} from "@/lib/line-moves-view";

export interface LineMoveBook {
  key: string;
  displayName: string;
  /** Market maker outside the board and consensus; drawn dashed. */
  reference: boolean;
}

const ET = "America/New_York";
const axisFormat = (hours: number) =>
  new Intl.DateTimeFormat("en-US", {
    timeZone: ET,
    ...(hours > 48 ? { month: "short", day: "numeric" } : { weekday: "short" }),
    hour: "numeric",
    ...(hours <= 6 ? { minute: "2-digit" } : {}),
  });
const exactFormat = new Intl.DateTimeFormat("en-US", {
  timeZone: ET,
  weekday: "short",
  month: "short",
  day: "numeric",
  hour: "numeric",
  minute: "2-digit",
  second: "2-digit",
  timeZoneName: "short",
});
const LOG_LIMIT = 60;

function formatLag(ms: number): string {
  const minutes = Math.round(ms / 60_000);
  if (minutes < 1) return "< 1 min";
  if (minutes < 60) return `${minutes} min`;
  const hours = minutes / 60;
  return `${hours < 10 ? hours.toFixed(1) : Math.round(hours)} h`;
}

export function LineMovesPanel({
  rows,
  books,
  market,
  selection,
  end,
  pointLabel,
  priceLabel,
}: {
  rows: LineMoveRow[];
  books: LineMoveBook[];
  market: Market;
  selection: Selection;
  /** Kickoff, or now for a game that hasn't started (ISO). */
  end: string;
  pointLabel: string;
  priceLabel: string;
}) {
  const [range, setRange] = useState<LineMoveRange>("48h");
  const [hidden, setHidden] = useState<ReadonlySet<string>>(new Set());
  const until = Date.parse(end);
  const byBook = useMemo(() => movesByBook(rows, market, selection), [rows, market, selection]);
  // Start at the range or at the first stored move, whichever is later (no empty stretch).
  const firstMove = Math.min(...[...byBook.values()].map((m) => m[0]?.t ?? Infinity));
  const from = Math.max(
    until - LINE_MOVE_RANGES[range].hours * 3_600_000,
    Math.min(firstMove, until),
  );

  const names = useMemo(
    () => Object.fromEntries(books.map((b) => [b.key, b.displayName])),
    [books],
  );
  const visible = useMemo(
    () => new Map([...byBook].filter(([k]) => !hidden.has(k))),
    [byBook, hidden],
  );
  const log = useMemo(
    () =>
      market === "h2h"
        ? []
        : pointMoveLog(byBook).filter(
            (m) => m.t > from && m.t <= until && !hidden.has(m.bookmakerKey),
          ),
    [byBook, market, from, until, hidden],
  );
  const toggle = (key: string) =>
    setHidden((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  const shown = books.filter((b) => byBook.has(b.key));

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div
          role="group"
          aria-label="Sportsbooks shown in line-move charts"
          className="flex flex-wrap gap-2"
        >
          {shown.map((b) => {
            const on = !hidden.has(b.key);
            return (
              <button
                key={b.key}
                type="button"
                aria-pressed={on}
                onClick={() => toggle(b.key)}
                className={`flex items-center gap-2 rounded border px-2.5 py-1 text-xs ${
                  on ? "border-line text-fg" : "border-line/50 text-subtle line-through"
                }`}
              >
                <svg aria-hidden width="16" height="4" className="shrink-0">
                  <line
                    x1="0"
                    y1="2"
                    x2="16"
                    y2="2"
                    stroke={FEED_COLORS[b.key] ?? "#8b98a9"}
                    strokeWidth="2"
                    strokeDasharray={b.reference ? "4 2" : undefined}
                  />
                </svg>
                {b.displayName}
                {b.reference && <span className="text-subtle">(reference)</span>}
              </button>
            );
          })}
        </div>
        <div role="group" aria-label="Time range" className="flex gap-1 text-xs">
          {(Object.keys(LINE_MOVE_RANGES) as LineMoveRange[]).map((r) => (
            <button
              key={r}
              type="button"
              aria-pressed={range === r}
              onClick={() => setRange(r)}
              className={`rounded border px-2.5 py-1 ${
                range === r ? "border-accent text-fg" : "border-line text-muted"
              }`}
            >
              {LINE_MOVE_RANGES[r].label}
            </button>
          ))}
        </div>
      </div>

      {market !== "h2h" && (
        <MovesChart
          title={pointLabel}
          field="point"
          byBook={visible}
          books={books}
          names={names}
          market={market}
          from={from}
          until={until}
          hours={LINE_MOVE_RANGES[range].hours}
        />
      )}
      <MovesChart
        title={priceLabel}
        field="price"
        byBook={visible}
        books={books}
        names={names}
        market={market}
        from={from}
        until={until}
        hours={LINE_MOVE_RANGES[range].hours}
      />

      {market !== "h2h" && (
        <section className="space-y-2">
          <h3 className="text-sm font-medium">
            Line changes, and which book posted each number first
          </h3>
          {log.length === 0 ? (
            <p className="text-sm text-muted">No line changes in this range.</p>
          ) : (
            <div
              tabIndex={0}
              role="region"
              aria-label="Line changes"
              className="relative max-h-96 overflow-auto rounded-lg border border-line bg-surface"
            >
              <table className="w-full min-w-[600px] text-sm">
                <thead className="sticky top-0 bg-surface">
                  <tr className="text-left text-xs text-muted">
                    <th scope="col" className="px-4 py-2 font-medium">
                      Time (ET)
                    </th>
                    <th scope="col" className="px-3 py-2 font-medium">
                      Book
                    </th>
                    <th scope="col" className="px-3 py-2 font-medium">
                      Line
                    </th>
                    <th scope="col" className="px-3 py-2 font-medium">
                      First to post it
                    </th>
                    <th scope="col" className="px-3 py-2 text-right font-medium">
                      Limit
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {log.slice(-LOG_LIMIT).map((m) => (
                    <tr key={`${m.bookmakerKey}-${m.t}`} className="border-t border-line/60">
                      <td className="whitespace-nowrap px-4 py-1.5 text-xs text-muted">
                        <time dateTime={new Date(m.t).toISOString()}>
                          {exactFormat.format(m.t)}
                        </time>
                      </td>
                      <td className="px-3 py-1.5">{names[m.bookmakerKey] ?? m.bookmakerKey}</td>
                      <td className="whitespace-nowrap px-3 py-1.5 font-mono tabular-nums">
                        {formatPoint(m.from, market)} → {formatPoint(m.to, market)}
                      </td>
                      <td className="px-3 py-1.5">
                        {m.lagMs === 0 && m.leaderKey === m.bookmakerKey ? (
                          <span className="font-medium text-fg">First</span>
                        ) : (
                          <span className="text-muted">
                            {names[m.leaderKey] ?? m.leaderKey}, {formatLag(m.lagMs)} earlier
                          </span>
                        )}
                      </td>
                      <td className="px-3 py-1.5 text-right tabular-nums text-muted">
                        {m.limit === null ? "–" : m.limit.toLocaleString("en-US")}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <p className="text-xs text-subtle">
            &ldquo;First to post it&rdquo; is the earliest book to move to the same number in the
            same direction within the previous 24 hours. It describes timing only: it does not say
            who bet or why.
            {log.length > LOG_LIMIT && ` Showing the latest ${LOG_LIMIT} of ${log.length}.`}
          </p>
        </section>
      )}
    </div>
  );
}

function MovesChart({
  title,
  field,
  byBook,
  books,
  names,
  market,
  from,
  until,
  hours,
}: {
  title: string;
  field: ChartField;
  byBook: ReturnType<typeof movesByBook>;
  books: LineMoveBook[];
  names: Record<string, string>;
  market: Market;
  from: number;
  until: number;
  hours: number;
}) {
  const keys = useMemo(() => [...byBook.keys()], [byBook]);
  const data = useMemo(
    () => lineMoveChartRows(byBook, field, from, until),
    [byBook, field, from, until],
  );
  const axis = useMemo(
    () => axisTicks(data, keys, field === "point" ? 0.5 : 5),
    [data, keys, field],
  );
  const format = (v: number) =>
    field === "point" ? formatPoint(v, market) : formatScaledAmerican(v);
  const tickFormat = axisFormat(hours);
  const reference = new Set(books.filter((b) => b.reference).map((b) => b.key));

  return (
    <figure className="rounded-lg border border-line bg-surface px-3 pb-2 pt-3">
      <figcaption className="mb-2 px-1 text-sm font-medium">{title}</figcaption>
      <p className="sr-only">{lineMoveSummary(byBook, names, field, from, until, format)}</p>
      <div className="h-64 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 8, right: 16, bottom: 4, left: 4 }}>
            <CartesianGrid stroke="#263041" vertical={false} />
            <XAxis
              dataKey="t"
              type="number"
              scale="time"
              domain={[from, until]}
              tickFormatter={(t: number) => tickFormat.format(t)}
              stroke="#5d6b7d"
              tick={{ fill: "#8b98a9", fontSize: 11 }}
              minTickGap={40}
            />
            <YAxis
              domain={axis?.domain ?? ["auto", "auto"]}
              ticks={axis?.ticks}
              interval={0}
              allowDecimals
              tickFormatter={format}
              stroke="#5d6b7d"
              tick={{ fill: "#8b98a9", fontSize: 11 }}
              width={52}
            />
            <Tooltip
              cursor={{ stroke: "#8b98a9", strokeWidth: 1 }}
              content={(props) => (
                <MovesTooltip {...props} keys={keys} names={names} format={format} />
              )}
            />
            {keys.map((key) => (
              <Line
                key={key}
                dataKey={key}
                name={names[key] ?? key}
                type="stepAfter"
                stroke={FEED_COLORS[key] ?? "#8b98a9"}
                strokeWidth={2}
                strokeDasharray={reference.has(key) ? "6 3" : undefined}
                connectNulls={false}
                dot={false}
                isAnimationActive={false}
                activeDot={{ r: 3, strokeWidth: 2, stroke: "#121821" }}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </figure>
  );
}

function MovesTooltip({
  active,
  payload,
  label,
  keys,
  names,
  format,
}: TooltipContentProps & {
  keys: string[];
  names: Record<string, string>;
  format: (v: number) => string;
}) {
  if (!active || !payload?.length || typeof label !== "number") return null;
  const row = payload[0]?.payload as ChartRow | undefined;
  if (!row) return null;
  return (
    <div className="rounded border border-line bg-canvas px-3 py-2 text-xs shadow-lg">
      <div className="mb-1 text-muted">{exactFormat.format(label)}</div>
      <table>
        <tbody>
          {keys.map((key) => {
            const v = row[key];
            return (
              <tr key={key}>
                <td className="pr-2 text-fg">{names[key] ?? key}</td>
                <td className="text-right font-mono tabular-nums text-fg">
                  {v === null || v === undefined ? (
                    <span className="text-subtle">no line</span>
                  ) : (
                    format(v)
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
