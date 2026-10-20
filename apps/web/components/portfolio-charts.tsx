"use client";

import { useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { EquityPoint } from "@/lib/portfolio-view";

// Categorical palette validated for the dark surface (shared with the history charts).
const PALETTE = [
  "#3987e5",
  "#2fb3a6",
  "#c98500",
  "#d95926",
  "#9085e9",
  "#199e70",
  "#d55181",
  "#c7ced8",
  "#5aa9e6",
  "#e0a35b",
  "#7bc96f",
  "#b07cd8",
  "#e46a6a",
];
const AXIS = { stroke: "#5d6b7d", tick: { fill: "#8b98a9", fontSize: 11 } };
const dayFormat = new Intl.DateTimeFormat("en-US", {
  month: "short",
  day: "numeric",
  timeZone: "UTC",
});

export interface ClvBar {
  id: string;
  label: string;
  meanClv: number;
  count: number;
}

export function PortfolioCharts({
  points,
  strategies,
  labels,
  initiallyShown,
  clv,
  equitySummary,
  clvSummary,
}: {
  points: EquityPoint[];
  strategies: string[];
  labels: Record<string, string>;
  initiallyShown: string[];
  clv: ClvBar[];
  equitySummary: string;
  clvSummary: string;
}) {
  const [shown, setShown] = useState<ReadonlySet<string>>(new Set(initiallyShown));
  const color = (id: string) => PALETTE[strategies.indexOf(id) % PALETTE.length]!;
  const toggle = (id: string) =>
    setShown((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  return (
    <div className="grid gap-4 xl:grid-cols-[2fr_1fr]">
      <figure className="rounded-lg border border-line bg-surface px-3 pb-2 pt-3">
        <figcaption className="mb-2 px-1 text-sm font-medium">
          Cumulative units by strategy (hypothetical, one unit per position or teaser)
        </figcaption>
        <p className="sr-only">{equitySummary}</p>
        <div
          role="group"
          aria-label="Strategies shown"
          className="mb-2 flex flex-wrap gap-1.5 px-1"
        >
          {strategies.map((id) => {
            const on = shown.has(id);
            return (
              <button
                key={id}
                type="button"
                aria-pressed={on}
                onClick={() => toggle(id)}
                title={labels[id]}
                className={`flex items-center gap-1.5 rounded border px-2 py-0.5 text-xs ${
                  on ? "border-line text-fg" : "border-line/50 text-subtle line-through"
                }`}
              >
                <span
                  aria-hidden
                  className="inline-block h-0.5 w-3"
                  style={{ backgroundColor: color(id) }}
                />
                {id}
              </button>
            );
          })}
        </div>
        <div className="h-72 w-full">
          {points.length === 0 ? (
            <p className="px-1 text-sm text-muted">Nothing settled yet.</p>
          ) : (
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={points} margin={{ top: 8, right: 16, bottom: 4, left: 4 }}>
                <CartesianGrid stroke="#263041" vertical={false} />
                <XAxis
                  dataKey="day"
                  tickFormatter={(d: string) => dayFormat.format(new Date(d))}
                  {...AXIS}
                  minTickGap={24}
                />
                <YAxis {...AXIS} width={40} />
                <ReferenceLine y={0} stroke="#8b98a9" strokeDasharray="4 3" />
                <Tooltip
                  contentStyle={{
                    background: "#0d1117",
                    border: "1px solid #263041",
                    fontSize: 12,
                  }}
                  labelFormatter={(d) => dayFormat.format(new Date(String(d)))}
                  formatter={(v, name) => [
                    typeof v === "number" ? v.toFixed(2) : "–",
                    labels[String(name)] ?? name,
                  ]}
                />
                {strategies
                  .filter((id) => shown.has(id))
                  .map((id) => (
                    <Line
                      key={id}
                      dataKey={id}
                      name={id}
                      type="stepAfter"
                      stroke={color(id)}
                      strokeWidth={2}
                      dot={false}
                      connectNulls
                      isAnimationActive={false}
                    />
                  ))}
              </LineChart>
            </ResponsiveContainer>
          )}
        </div>
      </figure>

      <figure className="rounded-lg border border-line bg-surface px-3 pb-2 pt-3">
        <figcaption className="mb-2 px-1 text-sm font-medium">
          Mean CLV in points (beating Pinnacle&apos;s close is positive)
        </figcaption>
        <p className="sr-only">{clvSummary}</p>
        <div className="h-80 w-full">
          {clv.length === 0 ? (
            <p className="px-1 text-sm text-muted">No graded positions with a close yet.</p>
          ) : (
            <ResponsiveContainer width="100%" height="100%">
              <BarChart
                data={clv}
                layout="vertical"
                margin={{ top: 4, right: 16, bottom: 4, left: 4 }}
              >
                <CartesianGrid stroke="#263041" horizontal={false} />
                <XAxis type="number" {...AXIS} />
                <YAxis type="category" dataKey="id" {...AXIS} width={64} />
                <ReferenceLine x={0} stroke="#8b98a9" />
                <Tooltip
                  contentStyle={{
                    background: "#0d1117",
                    border: "1px solid #263041",
                    fontSize: 12,
                  }}
                  formatter={(v, _n, item) => [
                    `${typeof v === "number" ? v.toFixed(2) : v} points over ${(item.payload as ClvBar).count}`,
                    (item.payload as ClvBar).label,
                  ]}
                />
                <Bar dataKey="meanClv" isAnimationActive={false}>
                  {clv.map((b) => (
                    <Cell key={b.id} fill={b.meanClv >= 0 ? "#2fb3a6" : "#d95926"} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>
      </figure>
    </div>
  );
}
