// Server-rendered SVG: one team's AdjEM by week with a ±1 SE band (MS-033). One series, so the
// title names it instead of a legend; every point has a native tooltip, and the page carries the
// same numbers in a table.
import { signed, weekLabel } from "@/lib/ratings-view";

export interface TrendPoint {
  week: number;
  adjEm: number;
  adjEmSe: number;
}

const W = 640;
const H = 220;
const PAD = { left: 40, right: 12, top: 12, bottom: 28 };

export function RatingTrend({ season, points }: { season: number; points: TrendPoint[] }) {
  if (points.length < 2) {
    return <p className="text-sm text-muted">Not enough weeks yet for a trend.</p>;
  }
  const lo = Math.min(0, ...points.map((p) => p.adjEm - p.adjEmSe));
  const hi = Math.max(0, ...points.map((p) => p.adjEm + p.adjEmSe));
  const span = Math.max(hi - lo, 1);
  const x = (i: number) => PAD.left + (i * (W - PAD.left - PAD.right)) / (points.length - 1);
  const y = (v: number) => PAD.top + ((hi - v) * (H - PAD.top - PAD.bottom)) / span;
  const line = points
    .map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(p.adjEm).toFixed(1)}`)
    .join("");
  const band =
    points
      .map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(p.adjEm + p.adjEmSe).toFixed(1)}`)
      .join("") +
    [...points]
      .reverse()
      .map((p, j) => `L${x(points.length - 1 - j).toFixed(1)},${y(p.adjEm - p.adjEmSe).toFixed(1)}`)
      .join("") +
    "Z";
  const ticks = [lo, 0, hi].filter((v, i, a) => a.indexOf(v) === i);
  const labelEvery = Math.ceil(points.length / 8);

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      className="h-auto w-full max-w-2xl"
      role="img"
      aria-label={`AdjEM by week, ${season}, with a one standard error band`}
    >
      {ticks.map((v) => (
        <g key={v}>
          <line
            x1={PAD.left}
            x2={W - PAD.right}
            y1={y(v)}
            y2={y(v)}
            className={v === 0 ? "stroke-subtle" : "stroke-line"}
            strokeWidth={1}
          />
          <text x={PAD.left - 6} y={y(v) + 4} textAnchor="end" className="fill-muted text-[11px]">
            {signed(v)}
          </text>
        </g>
      ))}
      <path d={band} className="fill-accent/15" />
      <path d={line} className="stroke-accent" fill="none" strokeWidth={2} strokeLinejoin="round" />
      {points.map((p, i) => (
        <g key={p.week}>
          <circle
            cx={x(i)}
            cy={y(p.adjEm)}
            r={4}
            className="fill-accent stroke-surface"
            strokeWidth={2}
          >
            <title>{`${weekLabel(season, p.week)}: AdjEM ${signed(p.adjEm)} ± ${p.adjEmSe.toFixed(1)}`}</title>
          </circle>
          {i % labelEvery === 0 && (
            <text x={x(i)} y={H - 8} textAnchor="middle" className="fill-muted text-[11px]">
              {p.week === 0 ? "Pre" : p.week}
            </text>
          )}
        </g>
      ))}
    </svg>
  );
}
