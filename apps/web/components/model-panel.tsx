// Game-page "Model estimate" panel (MS-033b): the last stored estimate for the football game linked
// to this odds event, its contributions, expected QBs, the market consensus beside it, and, once
// final, the result vs the model vs the close.
import Link from "next/link";
import type { Matchup } from "@marketscope/db";
import type { ConsensusResult } from "@marketscope/shared";
import { Notice } from "@/components/data-states";
import { ConsensusValue, ContributionBars, ExpectedQbs } from "@/components/model-estimate";
import { favoriteText, percent, spreadText } from "@/lib/model-view";
import { isSyntheticVersion, signed, weekLabel } from "@/lib/ratings-view";
import { formatTimestamp } from "@/lib/time";

export function ModelPanel({
  matchup: m,
  consensus,
  version,
}: {
  matchup: Matchup;
  consensus: ConsensusResult;
  version: string;
}) {
  const e = m.estimate;
  const final = m.homeFinal !== null && m.awayFinal !== null;
  const actual = final ? m.homeFinal! - m.awayFinal! : null;
  const rank = (r: number | null, em: number | null) =>
    r === null ? "" : ` (#${r}${em === null ? "" : `, AdjEM ${signed(em)}`})`;

  return (
    <section
      aria-labelledby="model-estimate"
      className="space-y-3 rounded-lg border border-line bg-surface p-4"
    >
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 id="model-estimate" className="text-sm font-medium uppercase tracking-wide text-muted">
          Model estimate
        </h2>
        <Link
          href={`/matchups?season=${m.season}&week=${m.week}`}
          className="text-sm text-accent hover:underline"
        >
          All {weekLabel(m.season, m.week)} matchups →
        </Link>
      </div>
      {isSyntheticVersion(version) && (
        <Notice tone="warn" title="Synthetic estimate: demo data, not real model output." />
      )}
      <p className="text-sm text-muted">
        <Link href={`/teams/${m.awayTeam}`} className="text-fg hover:text-accent">
          {m.awayName}
        </Link>
        {rank(m.awayRank, m.awayAdjEm)} at{" "}
        <Link href={`/teams/${m.homeTeam}`} className="text-fg hover:text-accent">
          {m.homeName}
        </Link>
        {rank(m.homeRank, m.homeAdjEm)}. Ranks are MarketScope Ratings going into the game.
      </p>
      {!e ? (
        <p className="text-sm text-muted">
          No model estimate was stored for this game before kickoff.
        </p>
      ) : (
        <>
          <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm sm:grid-cols-4">
            <div>
              <dt className="text-xs text-muted">Model estimate</dt>
              <dd className="font-medium">
                {favoriteText(m.homeTeam, m.awayTeam, e.expectedMargin)}
              </dd>
            </div>
            <div>
              <dt className="text-xs text-muted">Model score</dt>
              <dd className="tabular-nums">
                {e.homeScore !== null && e.awayScore !== null
                  ? `${m.awayTeam} ${e.awayScore.toFixed(1)} – ${m.homeTeam} ${e.homeScore.toFixed(1)}`
                  : "–"}
              </dd>
            </div>
            <div>
              <dt className="text-xs text-muted">Win probability</dt>
              <dd className="tabular-nums">
                {m.homeTeam} {percent(e.pHome)} · {m.awayTeam} {percent(1 - e.pHome)}
              </dd>
            </div>
            <div>
              <dt className="text-xs text-muted">{final ? "Close (nflverse)" : "Consensus now"}</dt>
              <dd className="tabular-nums">
                {final ? (
                  m.closeHomeSpread === null ? (
                    "–"
                  ) : (
                    spreadText(m.homeTeam, m.awayTeam, m.closeHomeSpread)
                  )
                ) : (
                  <ConsensusValue consensus={consensus} home={m.homeTeam} away={m.awayTeam} />
                )}
              </dd>
            </div>
          </dl>
          {final && actual !== null && (
            <p className="text-sm">
              <span className="text-xs uppercase tracking-wide text-muted">Final </span>
              <span className="tabular-nums">
                {m.awayTeam} {m.awayFinal} – {m.homeTeam} {m.homeFinal}
              </span>
              <span className="text-muted">
                {" "}
                · model missed by {Math.abs(e.expectedMargin - actual).toFixed(1)}
                {m.closeHomeSpread !== null &&
                  `, the close by ${Math.abs(-m.closeHomeSpread - actual).toFixed(1)}`}
              </span>
            </p>
          )}
          <ContributionBars estimate={e} home={m.homeTeam} away={m.awayTeam} />
          <ExpectedQbs estimate={e} home={m.homeTeam} away={m.awayTeam} />
          <p className="text-xs text-subtle">
            Last estimate before kickoff, made {formatTimestamp(e.predictedAt)} ({version}). Model
            estimates are less accurate than the market (2025 test: 10.1 vs 9.7 points per game;{" "}
            <Link href="/model" className="underline hover:text-muted">
              scorecard
            </Link>
            ). Not betting advice.
          </p>
        </>
      )}
    </section>
  );
}
