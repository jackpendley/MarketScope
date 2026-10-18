// Team-page season outlook (MS-034): simulated odds, the win distribution and playoff odds by week.
// Server-rendered SVG; values come from season_projections (model estimates).
import type { ProjectionHistoryRow } from "@marketscope/db";
import { oddsText, winRange } from "@/lib/projections-view";
import { weekLabel } from "@/lib/ratings-view";

const W = 640;
const H = 140;
const PAD = { l: 28, r: 8, t: 8, b: 22 };

function WinDistribution({ dist, team }: { dist: number[]; team: string }) {
  const max = Math.max(...dist, 0.01);
  const bw = (W - PAD.l - PAD.r) / dist.length;
  const range = winRange(dist);
  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      className="w-full max-w-2xl"
      role="img"
      aria-label={`${team} simulated regular-season wins: most likely ${range.mode}, middle 80% ${range.low} to ${range.high}`}
    >
      {dist.map((p, k) => {
        const h = ((H - PAD.t - PAD.b) * p) / max;
        return (
          <g key={k}>
            <rect
              x={PAD.l + k * bw + 2}
              y={H - PAD.b - h}
              width={bw - 4}
              height={h}
              className={k >= range.low && k <= range.high ? "fill-accent/70" : "fill-muted/40"}
            >
              <title>{`${k} wins: ${oddsText(p)}`}</title>
            </rect>
            <text
              x={PAD.l + k * bw + bw / 2}
              y={H - 6}
              textAnchor="middle"
              className="fill-muted text-[10px]"
            >
              {k}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

function OddsTrend({ season, rows }: { season: number; rows: ProjectionHistoryRow[] }) {
  if (rows.length < 2) return null;
  const x = (i: number) => PAD.l + ((W - PAD.l - PAD.r) * i) / (rows.length - 1);
  const y = (p: number) => PAD.t + (H - PAD.t - PAD.b) * (1 - p);
  const line = (key: "playoffP" | "divisionP") =>
    rows.map((r, i) => `${x(i).toFixed(1)},${y(r[key]).toFixed(1)}`).join(" ");
  const last = rows.at(-1)!;
  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      className="w-full max-w-2xl"
      role="img"
      aria-label={`Playoff odds by week, ${season}: now ${oddsText(last.playoffP)}; division ${oddsText(last.divisionP)}`}
    >
      {[0, 0.5, 1].map((p) => (
        <g key={p}>
          <line x1={PAD.l} x2={W - PAD.r} y1={y(p)} y2={y(p)} className="stroke-line" />
          <text x={PAD.l - 4} y={y(p) + 3} textAnchor="end" className="fill-muted text-[10px]">
            {p * 100}%
          </text>
        </g>
      ))}
      <polyline
        points={line("divisionP")}
        fill="none"
        className="stroke-muted"
        strokeWidth={1.5}
        strokeDasharray="4 3"
      />
      <polyline points={line("playoffP")} fill="none" className="stroke-accent" strokeWidth={2} />
      {rows.map((r, i) => (
        <g key={r.week}>
          <circle cx={x(i)} cy={y(r.playoffP)} r={3} className="fill-accent">
            <title>{`${weekLabel(season, r.week)}: playoffs ${oddsText(r.playoffP)}, division ${oddsText(r.divisionP)}`}</title>
          </circle>
          {(i === 0 || i === rows.length - 1 || r.week % 4 === 0) && (
            <text x={x(i)} y={H - 6} textAnchor="middle" className="fill-muted text-[10px]">
              {r.week === 0 ? "Pre" : `W${r.week}`}
            </text>
          )}
        </g>
      ))}
    </svg>
  );
}

export function SeasonOutlook({
  team,
  season,
  week,
  history,
}: {
  team: string;
  season: number;
  week: number;
  history: ProjectionHistoryRow[];
}) {
  const rows = history.filter((h) => h.week <= week);
  const now = rows.at(-1);
  if (!now) return null;
  const cards: [string, string][] = [
    ["Projected wins", now.meanWins.toFixed(1)],
    ["Playoffs", oddsText(now.playoffP)],
    ["Division", oddsText(now.divisionP)],
    ["#1 seed", oddsText(now.seed1P)],
    ["Conference", oddsText(now.confP)],
    ["Super Bowl", oddsText(now.sbP)],
  ];
  return (
    <section aria-labelledby="outlook" className="space-y-3">
      <h2 id="outlook" className="text-sm font-medium uppercase tracking-wide text-muted">
        Season outlook (simulated, after {weekLabel(season, now.week)})
      </h2>
      <dl className="flex flex-wrap gap-x-8 gap-y-3 rounded-lg border border-line bg-surface px-4 py-3 text-sm">
        {cards.map(([label, value]) => (
          <div key={label}>
            <dt className="text-xs text-muted">{label}</dt>
            <dd className="mt-0.5 font-medium tabular-nums">{value}</dd>
          </div>
        ))}
      </dl>
      <div className="grid gap-4 lg:grid-cols-2">
        <figure className="space-y-1">
          <WinDistribution dist={now.winDist} team={team} />
          <figcaption className="text-xs text-subtle">
            Regular-season wins across simulated seasons (highlighted: the middle 80%).
          </figcaption>
        </figure>
        {rows.length >= 2 && (
          <figure className="space-y-1">
            <OddsTrend season={season} rows={rows} />
            <figcaption className="text-xs text-subtle">
              Playoff odds (solid) and division odds (dashed) by week. Model estimates, not
              certainties.
            </figcaption>
          </figure>
        )}
      </div>
    </section>
  );
}
