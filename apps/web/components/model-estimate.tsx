// Shared pieces for showing a stored model estimate (MS-033b): the contribution waterfall and the
// expected-quarterback line. Server components; values come from model_predictions.
import type { ModelEstimate } from "@marketscope/db";
import type { ConsensusResult } from "@marketscope/shared";
import { contributionRows, favoriteText, percent, spreadText } from "@/lib/model-view";
import { signed } from "@/lib/ratings-view";

/**
 * Additive contributions to the expected margin as diverging bars: right (accent) favors the home
 * team, left (muted) the away team. The rows sum to the expected margin shown last.
 */
export function ContributionBars({
  estimate,
  home,
  away,
}: {
  estimate: Pick<ModelEstimate, "contributions" | "expectedMargin">;
  home: string;
  away: string;
}) {
  const rows = contributionRows(estimate.contributions);
  const scale = Math.max(
    1,
    ...rows.map((r) => Math.abs(r.value)),
    Math.abs(estimate.expectedMargin),
  );
  const all = [...rows, { key: "total", label: "Expected margin", value: estimate.expectedMargin }];
  return (
    <table
      className="w-full text-sm"
      aria-label={`Model estimate contributions, ${home} vs ${away}`}
    >
      <thead className="sr-only">
        <tr>
          <th scope="col">Component</th>
          <th scope="col">Bar</th>
          <th scope="col">
            Points toward {home} (negative: toward {away})
          </th>
        </tr>
      </thead>
      <tbody>
        {all.map((r) => {
          const width = `${(50 * Math.abs(r.value)) / scale}%`;
          const isTotal = r.key === "total";
          return (
            <tr key={r.key} className={isTotal ? "border-t border-line/60 font-medium" : ""}>
              <td className="whitespace-nowrap py-0.5 pr-3 text-muted">{r.label}</td>
              <td className="w-1/2 py-0.5">
                <div className="relative h-3 rounded bg-surface-raised">
                  <div className="absolute inset-y-0 left-1/2 w-px bg-line" />
                  <div
                    className={`absolute inset-y-0 rounded ${r.value >= 0 ? "bg-accent/70" : "bg-muted/60"} ${isTotal ? "opacity-100" : "opacity-80"}`}
                    style={r.value >= 0 ? { left: "50%", width } : { right: "50%", width }}
                  />
                </div>
              </td>
              <td className="whitespace-nowrap py-0.5 pl-3 text-right tabular-nums">
                {signed(r.value)}
              </td>
            </tr>
          );
        })}
      </tbody>
      <caption className="caption-bottom pt-1 text-left text-xs text-subtle">
        Points toward {home} (right) or {away} (left). Model estimate:{" "}
        {favoriteText(home, away, estimate.expectedMargin)}.
      </caption>
    </table>
  );
}

/** "P. Mahomes vs Rookie QB (64% to play)"; unknown names show as "not available". */
export function ExpectedQbs({
  estimate,
  home,
  away,
}: {
  estimate: Pick<ModelEstimate, "homeQb" | "awayQb" | "homeQbP" | "awayQbP">;
  home: string;
  away: string;
}) {
  const qb = (team: string, name: string | null, p: number | null) => (
    <span>
      <span className="text-muted">{team}</span>{" "}
      {name ?? <span className="text-subtle">not available</span>}
      {p !== null && p < 0.995 && (
        <span className="text-xs text-warn"> ({percent(p)} to play)</span>
      )}
    </span>
  );
  return (
    <p className="text-sm">
      <span className="text-xs uppercase tracking-wide text-muted">Expected QBs </span>
      {qb(away, estimate.awayQb, estimate.awayQbP)}
      <span className="text-subtle"> · </span>
      {qb(home, estimate.homeQb, estimate.homeQbP)}
    </p>
  );
}

/** The board consensus as a posted home spread, or "n/a" with the reason (e.g. too few books). */
export function ConsensusValue({
  consensus,
  home,
  away,
}: {
  consensus: ConsensusResult | undefined;
  home: string;
  away: string;
}) {
  if (!consensus) return <>–</>;
  if (consensus.homePoint === null)
    return (
      <span className="text-subtle" title={consensus.reason}>
        n/a <span className="text-xs">({consensus.bookmakerKeys.length} of 3 books)</span>
      </span>
    );
  return <>{spreadText(home, away, consensus.homePoint)}</>;
}
