"use client";

import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

export interface EquitySeries {
  key: string;
  label: string;
  color: string;
  rows: { n: number; units: number; season: number }[];
}

/** Cumulative hypothetical units by teaser number, one line per variant. */
export function EquityChart({ series, summary }: { series: EquitySeries[]; summary: string }) {
  const length = Math.max(...series.map((s) => s.rows.length));
  const data = Array.from({ length }, (_, i) => {
    const row: Record<string, number | null> = { n: i + 1 };
    for (const s of series) row[s.key] = s.rows[i]?.units ?? null;
    return row;
  });
  return (
    <figure className="rounded-lg border border-line bg-surface px-3 pb-2 pt-3">
      <figcaption className="mb-2 px-1 text-sm font-medium">
        Cumulative units, one unit per teaser, in date order (hypothetical)
      </figcaption>
      <p className="sr-only">{summary}</p>
      <div className="mb-2 flex flex-wrap gap-4 px-1 text-xs text-muted">
        {series.map((s) => (
          <span key={s.key} className="flex items-center gap-1.5">
            <span
              aria-hidden
              className="inline-block h-0.5 w-4"
              style={{ backgroundColor: s.color }}
            />
            {s.label}
          </span>
        ))}
      </div>
      <div className="h-64 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 8, right: 16, bottom: 4, left: 4 }}>
            <CartesianGrid stroke="#263041" vertical={false} />
            <XAxis
              dataKey="n"
              type="number"
              domain={[1, length]}
              stroke="#5d6b7d"
              tick={{ fill: "#8b98a9", fontSize: 11 }}
              label={{
                value: "Teaser number",
                position: "insideBottomRight",
                offset: -2,
                fill: "#8b98a9",
                fontSize: 11,
              }}
            />
            <YAxis stroke="#5d6b7d" tick={{ fill: "#8b98a9", fontSize: 11 }} width={44} />
            <ReferenceLine y={0} stroke="#8b98a9" strokeDasharray="4 3" />
            <Tooltip
              contentStyle={{ background: "#0d1117", border: "1px solid #263041", fontSize: 12 }}
              labelFormatter={(n) => `Teaser ${n}`}
              formatter={(v, name) => [typeof v === "number" ? v.toFixed(1) : v, name]}
            />
            {series.map((s) => (
              <Line
                key={s.key}
                dataKey={s.key}
                name={s.label}
                stroke={s.color}
                strokeWidth={2}
                dot={false}
                isAnimationActive={false}
                connectNulls={false}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </figure>
  );
}
