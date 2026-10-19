"use client";

import { useMemo, useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  type DotItemDotProps,
  type TooltipContentProps,
} from "recharts";
import { formatPoint, type BookSeries, type Market } from "@marketscope/shared";
import {
  axisTicks,
  buildChartRows,
  FEED_COLORS,
  formatScaledAmerican,
  seriesSummary,
  type ChartField,
  type ChartRow,
} from "@/lib/history-chart";

export interface ChartSeries extends BookSeries {
  displayName: string;
}

const timeFormat = new Intl.DateTimeFormat("en-US", {
  timeZone: "America/New_York",
  month: "short",
  day: "numeric",
  hour: "numeric",
});
const tooltipTimeFormat = new Intl.DateTimeFormat("en-US", {
  timeZone: "America/New_York",
  weekday: "short",
  month: "short",
  day: "numeric",
  hour: "numeric",
  minute: "2-digit",
  timeZoneName: "short",
});

export function HistoryCharts({
  series,
  market,
  pointLabel,
  priceLabel,
  cursor,
}: {
  series: ChartSeries[];
  market: Market;
  pointLabel: string;
  priceLabel: string;
  /** Replay cursor (ms since epoch), drawn as a vertical line on both charts. */
  cursor?: number;
}) {
  const [hidden, setHidden] = useState<ReadonlySet<string>>(new Set());
  const visible = useMemo(
    () => series.filter((s) => !hidden.has(s.bookmakerKey)),
    [series, hidden],
  );
  const toggle = (key: string) =>
    setHidden((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });

  return (
    <div className="space-y-4">
      <div role="group" aria-label="Sportsbooks shown in charts" className="flex flex-wrap gap-2">
        {series.map((s) => {
          const on = !hidden.has(s.bookmakerKey);
          return (
            <button
              key={s.bookmakerKey}
              type="button"
              aria-pressed={on}
              onClick={() => toggle(s.bookmakerKey)}
              className={`flex items-center gap-2 rounded border px-2.5 py-1 text-xs ${
                on ? "border-line text-fg" : "border-line/50 text-subtle line-through"
              }`}
            >
              <span
                aria-hidden
                className="inline-block h-0.5 w-4 rounded"
                style={{ backgroundColor: FEED_COLORS[s.bookmakerKey] ?? "#8b98a9" }}
              />
              {s.displayName}
            </button>
          );
        })}
      </div>

      {market !== "h2h" && (
        <ChartPanel
          title={pointLabel}
          series={visible}
          field="point"
          market={market}
          cursor={cursor}
        />
      )}
      <ChartPanel
        title={priceLabel}
        series={visible}
        field="price"
        market={market}
        cursor={cursor}
      />
    </div>
  );
}

function ChartPanel({
  title,
  series,
  field,
  market,
  cursor,
}: {
  title: string;
  series: ChartSeries[];
  field: ChartField;
  market: Market;
  cursor?: number;
}) {
  const { rows, keys } = useMemo(() => buildChartRows(series, field), [series, field]);
  const axis = useMemo(
    () => axisTicks(rows, keys, field === "point" ? 0.5 : 5),
    [rows, keys, field],
  );
  const changeTimes = useMemo(
    () =>
      new Map(
        series.map((s) => [
          s.bookmakerKey,
          new Set(
            s.changes
              .filter((c) => (field === "point" ? c.type !== "price" : c.type !== "point"))
              .map((c) => Date.parse(c.intervalEnd)),
          ),
        ]),
      ),
    [series, field],
  );
  const format = (v: number) =>
    field === "point" ? formatPoint(v, market) : formatScaledAmerican(v);

  return (
    <figure className="rounded-lg border border-line bg-surface px-3 pb-2 pt-3">
      <figcaption className="mb-2 px-1 text-sm font-medium">{title}</figcaption>
      {rows.length === 0 ? (
        <p className="px-1 pb-3 text-sm text-muted">No observations in this range.</p>
      ) : (
        <>
          {/* Screen readers hear this summary first; the chart stays keyboard-explorable (Recharts' accessibility layer). */}
          <p className="sr-only">{seriesSummary(series, field, format)}</p>
          <div className="h-64 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={rows} margin={{ top: 8, right: 16, bottom: 4, left: 4 }}>
                <CartesianGrid stroke="#263041" strokeDasharray="0" vertical={false} />
                <XAxis
                  dataKey="t"
                  type="number"
                  scale="time"
                  domain={["dataMin", "dataMax"]}
                  tickFormatter={(t: number) => timeFormat.format(t)}
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
                {cursor !== undefined && (
                  <ReferenceLine
                    x={cursor}
                    stroke="#e6edf3"
                    strokeDasharray="4 3"
                    strokeWidth={1}
                    label={{
                      value: "replay",
                      position: "insideTopRight",
                      fill: "#8b98a9",
                      fontSize: 10,
                    }}
                  />
                )}
                <Tooltip
                  cursor={{ stroke: "#8b98a9", strokeWidth: 1 }}
                  content={(props) => <HistoryTooltip {...props} series={series} format={format} />}
                />
                {series.map((s) => (
                  <Line
                    key={s.bookmakerKey}
                    dataKey={s.bookmakerKey}
                    name={s.displayName}
                    type="stepAfter"
                    stroke={FEED_COLORS[s.bookmakerKey] ?? "#8b98a9"}
                    strokeWidth={2}
                    connectNulls={false}
                    isAnimationActive={false}
                    activeDot={{ r: 4, strokeWidth: 2, stroke: "#121821" }}
                    dot={(props: DotItemDotProps) => {
                      const { cx, cy } = props;
                      const payload = props.payload as ChartRow;
                      const key = `${s.bookmakerKey}-${payload.t}`;
                      const isChange = changeTimes.get(s.bookmakerKey)?.has(payload.t);
                      if (!isChange || cx === undefined || cy === undefined) return <g key={key} />;
                      return (
                        <circle
                          key={key}
                          cx={cx}
                          cy={cy}
                          r={4}
                          fill={FEED_COLORS[s.bookmakerKey] ?? "#8b98a9"}
                          stroke="#121821"
                          strokeWidth={2}
                        />
                      );
                    }}
                  />
                ))}
              </LineChart>
            </ResponsiveContainer>
          </div>
        </>
      )}
    </figure>
  );
}

function HistoryTooltip({
  active,
  payload,
  label,
  series,
  format,
}: TooltipContentProps & { series: ChartSeries[]; format: (v: number) => string }) {
  if (!active || !payload?.length || typeof label !== "number") return null;
  const row = payload[0]?.payload as ChartRow | undefined;
  if (!row) return null;
  return (
    <div className="rounded border border-line bg-canvas px-3 py-2 text-xs shadow-lg">
      <div className="mb-1 text-muted">{tooltipTimeFormat.format(label)}</div>
      <table>
        <tbody>
          {series.map((s) => {
            const v = row[s.bookmakerKey];
            return (
              <tr key={s.bookmakerKey}>
                <td className="pr-2">
                  <span
                    aria-hidden
                    className="mr-1.5 inline-block h-2 w-2 rounded-full"
                    style={{ backgroundColor: FEED_COLORS[s.bookmakerKey] ?? "#8b98a9" }}
                  />
                  <span className="text-fg">{s.displayName}</span>
                </td>
                <td className="text-right font-mono tabular-nums text-fg">
                  {v === null || v === undefined ? (
                    <span className="text-subtle">no data</span>
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
