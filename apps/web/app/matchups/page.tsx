import type { Metadata } from "next";
import Link from "next/link";
import { connection } from "next/server";
import {
  currentWeek,
  matchupsForWeek,
  matchupWeeks,
  ratingVersion,
  type Matchup,
} from "@marketscope/db";
import type { ConsensusResult } from "@marketscope/shared";
import { DataUnavailable, Notice } from "@/components/data-states";
import { ConsensusValue, ContributionBars, ExpectedQbs } from "@/components/model-estimate";
import {
  excitement,
  favoriteText,
  gameQuality,
  parseWeekQuery,
  percent,
  resolveMatchupWeek,
  spreadText,
} from "@/lib/model-view";
import { isSyntheticVersion, signed, weekLabel } from "@/lib/ratings-view";
import { isConnectionError } from "@/lib/server/api";
import { DatabaseNotConfiguredError, getDb } from "@/lib/server/db";
import { loadConsensus } from "@/lib/server/games";
import { formatKickoff, formatTimestamp } from "@/lib/time";

export const metadata: Metadata = { title: "Matchups" };

function TeamLabel({
  abbr,
  name,
  rank,
  adjEm,
}: {
  abbr: string;
  name: string;
  rank: number | null;
  adjEm: number | null;
}) {
  return (
    <span>
      {rank !== null && <span className="text-xs text-muted">#{rank} </span>}
      <Link href={`/teams/${abbr}`} className="font-medium hover:text-accent">
        {name}
      </Link>
      {adjEm !== null && <span className="text-xs text-subtle"> {signed(adjEm)}</span>}
    </span>
  );
}

function Score({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div>
      <dt className="text-xs text-muted">{label}</dt>
      <dd className="tabular-nums">{value}</dd>
    </div>
  );
}

function MatchupCard({ m, consensus }: { m: Matchup; consensus: ConsensusResult | undefined }) {
  const e = m.estimate;
  const quality = gameQuality(m.homeRank, m.awayRank, m.teams);
  const thrill = excitement(quality, e?.pHome ?? null);
  const final = m.homeFinal !== null && m.awayFinal !== null;
  const actualMargin = final ? m.homeFinal! - m.awayFinal! : null;

  return (
    <article
      className="space-y-3 rounded-lg border border-line bg-surface p-4"
      aria-label={`${m.awayTeam} at ${m.homeTeam}`}
    >
      <header className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-sm">
          <TeamLabel abbr={m.awayTeam} name={m.awayName} rank={m.awayRank} adjEm={m.awayAdjEm} />
          <span className="text-muted"> {m.neutralSite ? "vs" : "@"} </span>
          <TeamLabel abbr={m.homeTeam} name={m.homeName} rank={m.homeRank} adjEm={m.homeAdjEm} />
        </h2>
        <span className="text-xs text-muted">
          <time dateTime={m.kickoffUtc}>{formatKickoff(m.kickoffUtc)}</time>
          {m.neutralSite && " · neutral site"}
        </span>
      </header>

      <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm sm:grid-cols-4">
        <Score
          label="Model score"
          value={
            e && e.homeScore !== null && e.awayScore !== null
              ? `${m.awayTeam} ${e.awayScore.toFixed(1)} – ${m.homeTeam} ${e.homeScore.toFixed(1)}`
              : "–"
          }
        />
        <Score label="Win probability" value={e ? `${m.homeTeam} ${percent(e.pHome)}` : "–"} />
        <Score
          label={final ? "Close (nflverse)" : "Consensus now"}
          value={
            final ? (
              m.closeHomeSpread !== null ? (
                spreadText(m.homeTeam, m.awayTeam, m.closeHomeSpread)
              ) : (
                "–"
              )
            ) : (
              <ConsensusValue consensus={consensus} home={m.homeTeam} away={m.awayTeam} />
            )
          }
        />
        <Score
          label="Quality · excitement"
          value={quality === null ? "–" : `${quality} · ${thrill ?? "–"}`}
        />
      </dl>

      {final && (
        <p className="text-sm">
          <span className="text-xs uppercase tracking-wide text-muted">Final </span>
          <span className="tabular-nums">
            {m.awayTeam} {m.awayFinal} – {m.homeTeam} {m.homeFinal}
          </span>
          {e && actualMargin !== null && (
            <span className="text-muted">
              {" "}
              · model estimate {favoriteText(m.homeTeam, m.awayTeam, e.expectedMargin)}, missed by{" "}
              {Math.abs(e.expectedMargin - actualMargin).toFixed(1)}
            </span>
          )}
        </p>
      )}

      {e ? (
        <>
          <ContributionBars estimate={e} home={m.homeTeam} away={m.awayTeam} />
          <ExpectedQbs estimate={e} home={m.homeTeam} away={m.awayTeam} />
          <p className="text-xs text-subtle">
            Last model estimate before kickoff, made {formatTimestamp(e.predictedAt)}.
            {m.eventId && (
              <>
                {" "}
                <Link href={`/nfl/games/${m.eventId}`} className="text-accent hover:underline">
                  Odds and line history →
                </Link>
              </>
            )}
          </p>
        </>
      ) : (
        <p className="text-sm text-muted">
          No stored model estimate for this game. Estimates are written before kickoff from the live
          forward test onward; earlier games are covered by the 2023–25 evaluation.
        </p>
      )}
    </article>
  );
}

export default async function MatchupsPage(props: PageProps<"/matchups">) {
  await connection();
  const q = parseWeekQuery(await props.searchParams);

  let data;
  try {
    const db = getDb();
    const version = await ratingVersion(db);
    if (!version) data = null;
    else {
      const [weeks, current] = await Promise.all([
        matchupWeeks(db, version),
        currentWeek(db, new Date().toISOString()),
      ]);
      const at = resolveMatchupWeek(weeks, q, current);
      const games = at ? await matchupsForWeek(db, { version, ...at }) : [];
      const consensus = await loadConsensus(
        db,
        games.filter((g) => g.eventId && g.homeFinal === null).map((g) => g.eventId!),
      );
      data = { version, weeks, at, games, consensus };
    }
  } catch (err) {
    if (err instanceof DatabaseNotConfiguredError || isConnectionError(err))
      return <DataUnavailable />;
    throw err;
  }

  if (!data || !data.at) {
    return (
      <div className="space-y-4">
        <h1 className="text-xl font-semibold tracking-tight">Matchups</h1>
        <Notice title="No matchups yet.">
          The football jobs have not written games or ratings to this database.
        </Notice>
      </div>
    );
  }

  const { version, weeks, at, games, consensus } = data;
  const seasons = [...new Set(weeks.map((w) => w.season))].reverse();
  const seasonWeeks = weeks.filter((w) => w.season === at.season);
  const byExcitement = [...games].sort(
    (a, b) =>
      (excitement(gameQuality(b.homeRank, b.awayRank, b.teams), b.estimate?.pHome ?? null) ?? -1) -
      (excitement(gameQuality(a.homeRank, a.awayRank, a.teams), a.estimate?.pHome ?? null) ?? -1),
  );
  const top = byExcitement[0];

  return (
    <div className="space-y-5">
      <div className="space-y-1">
        <h1 className="text-xl font-semibold tracking-tight">Matchups</h1>
        <p className="max-w-3xl text-sm text-muted">
          Each game&apos;s <strong className="text-fg">model estimate</strong>: predicted score, win
          probability and what drives the margin (team ratings, home field, quarterbacks, other
          absences), next to the market. The model is less accurate than the market: in the 2025
          test it missed by 10.1 points per game on average, the closing line by 9.7 (
          <Link href="/model" className="text-accent hover:underline">
            scorecard
          </Link>
          ). Not betting advice.
        </p>
      </div>

      {isSyntheticVersion(version) && (
        <Notice tone="warn" title="Synthetic estimates: demo data, not real model output.">
          This database holds generated games, ratings and estimates for development and testing.
        </Notice>
      )}

      <form
        method="get"
        action="/matchups"
        className="flex flex-wrap items-end gap-x-5 gap-y-3 rounded-lg border border-line bg-surface px-4 py-3 text-sm"
      >
        <label className="flex flex-col gap-1">
          <span className="text-xs text-muted">Season</span>
          <select
            name="season"
            defaultValue={String(at.season)}
            className="rounded border border-line bg-canvas px-2 py-1"
          >
            {seasons.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-xs text-muted">Week</span>
          <select
            name="week"
            defaultValue={String(at.week)}
            className="rounded border border-line bg-canvas px-2 py-1"
          >
            {seasonWeeks.map((w) => (
              <option key={w.week} value={w.week}>
                {weekLabel(w.season, w.week)}
              </option>
            ))}
          </select>
        </label>
        <button
          type="submit"
          className="rounded border border-line bg-surface-raised px-3 py-1 hover:border-accent"
        >
          Show
        </button>
        <span className="text-xs text-subtle">
          {at.season} · {weekLabel(at.season, at.week)} · {games.length} games · model {version}
        </span>
      </form>

      {top && top.estimate && (
        <p className="text-sm text-muted">
          Most exciting on paper: <span className="text-fg">{top.awayName}</span> at{" "}
          <span className="text-fg">{top.homeName}</span> (quality{" "}
          {gameQuality(top.homeRank, top.awayRank, top.teams)}, excitement{" "}
          {excitement(gameQuality(top.homeRank, top.awayRank, top.teams), top.estimate.pHome)}).
        </p>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        {games.map((m) => (
          <MatchupCard
            key={m.gameId}
            m={m}
            consensus={m.eventId ? consensus.get(m.eventId) : undefined}
          />
        ))}
      </div>

      <details className="max-w-3xl text-sm text-muted">
        <summary className="cursor-pointer text-fg">How to read a matchup</summary>
        <ul className="mt-2 list-disc space-y-1 pl-5">
          <li>
            <strong className="text-fg">Model score</strong> comes from each offense against the
            other defense, pace and home field, so margin and total share one structure.
          </li>
          <li>
            <strong className="text-fg">Contributions</strong> add up to the expected margin: team
            ratings (opponent-adjusted offense, defense and special teams), home field, the expected
            quarterbacks against each team&apos;s usual level, and other expected absences from
            injury reports.
          </li>
          <li>
            <strong className="text-fg">Quality</strong> (0–100) is the average league percentile of
            the two teams&apos; ratings going in; <strong className="text-fg">excitement</strong>{" "}
            scales it by how close the game is expected to be. Both are descriptive.
          </li>
          <li>
            <strong className="text-fg">Consensus now</strong> is the median home spread across our
            board&apos;s books in the latest snapshot; once a game is final the page shows the
            nflverse closing line instead (a labeled benchmark).
          </li>
        </ul>
      </details>
    </div>
  );
}
