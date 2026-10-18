import type { Metadata } from "next";
import Link from "next/link";
import { connection } from "next/server";
import { projectionsForWeek, projectionWeeks, ratingVersion } from "@marketscope/db";
import { DataUnavailable, Notice } from "@/components/data-states";
import { groupByDivision, oddsText, oddsTone, winRange } from "@/lib/projections-view";
import {
  isSyntheticVersion,
  parseRatingsQuery,
  record,
  resolveWeek,
  signed,
  weekLabel,
} from "@/lib/ratings-view";
import { isConnectionError } from "@/lib/server/api";
import { DatabaseNotConfiguredError, getDb } from "@/lib/server/db";

export const metadata: Metadata = { title: "Season projections" };

const ODDS: {
  key: "playoffP" | "divisionP" | "seed1P" | "confP" | "sbP";
  label: string;
  title: string;
}[] = [
  {
    key: "playoffP",
    label: "Playoffs",
    title: "Share of simulated seasons in which the team made the playoffs",
  },
  { key: "divisionP", label: "Division", title: "Won the division" },
  {
    key: "seed1P",
    label: "#1 seed",
    title: "Earned the conference's top seed (the only bye since 2020)",
  },
  { key: "confP", label: "Conf.", title: "Won the conference (reached the Super Bowl)" },
  { key: "sbP", label: "Super Bowl", title: "Won the Super Bowl" },
];

export default async function ProjectionsPage(props: PageProps<"/projections">) {
  await connection();
  const q = parseRatingsQuery(await props.searchParams);

  let data;
  try {
    const db = getDb();
    const version = await ratingVersion(db);
    if (!version) data = null;
    else {
      const weeks = await projectionWeeks(db, version);
      const at = resolveWeek(weeks, q);
      const rows = at ? await projectionsForWeek(db, { version, ...at }) : [];
      data = { version, weeks, at, rows };
    }
  } catch (err) {
    if (err instanceof DatabaseNotConfiguredError || isConnectionError(err))
      return <DataUnavailable />;
    throw err;
  }

  if (!data || !data.at) {
    return (
      <div className="space-y-4">
        <h1 className="text-xl font-semibold tracking-tight">Season projections</h1>
        <Notice title="No projections yet.">
          The projections job has not written any simulated seasons to this database.
        </Notice>
      </div>
    );
  }

  const { version, weeks, at, rows } = data;
  const seasons = [...new Set(weeks.map((w) => w.season))].reverse();
  const seasonWeeks = weeks.filter((w) => w.season === at.season);
  const groups = groupByDivision(rows, q.conference);
  const sims = rows[0]?.sims ?? 0;

  return (
    <div className="space-y-5">
      <div className="space-y-1">
        <h1 className="text-xl font-semibold tracking-tight">Season projections</h1>
        <p className="max-w-3xl text-sm text-muted">
          Playoff, division, top-seed, conference and Super Bowl odds from {sims.toLocaleString()}{" "}
          simulated seasons. Every number is a <strong className="text-fg">model estimate</strong>:
          the rest of the schedule is played from the{" "}
          <Link href="/ratings" className="text-accent hover:underline">
            MarketScope Ratings
          </Link>{" "}
          as of the week shown, with their uncertainty, then the NFL tiebreakers and the playoff
          bracket. In a 2016–24 backtest the odds were well calibrated (teams given 70–80% made the
          playoffs 69% of the time), but they are not certainties. Not betting advice.
        </p>
      </div>

      {isSyntheticVersion(version) && (
        <Notice tone="warn" title="Synthetic projections: demo data, not real model output.">
          This database holds generated projections for development and testing.
        </Notice>
      )}

      <form
        method="get"
        action="/projections"
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
          <span className="text-xs text-muted">Projection after</span>
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
        <label className="flex flex-col gap-1">
          <span className="text-xs text-muted">Conference</span>
          <select
            name="conf"
            defaultValue={q.conference ?? ""}
            className="rounded border border-line bg-canvas px-2 py-1"
          >
            <option value="">All</option>
            <option value="AFC">AFC</option>
            <option value="NFC">NFC</option>
          </select>
        </label>
        <button
          type="submit"
          className="rounded border border-line bg-surface-raised px-3 py-1 hover:border-accent"
        >
          Show
        </button>
        <span className="text-xs text-subtle">
          {at.season} · {weekLabel(at.season, at.week)} · {rows[0]?.gamesPlayed ?? 0} games final ·
          model {version}
        </span>
      </form>

      <div className="grid gap-4 xl:grid-cols-2">
        {groups.map((g) => (
          <section
            key={g.division}
            aria-labelledby={`div-${g.division.replace(" ", "-")}`}
            className="overflow-x-auto rounded-lg border border-line bg-surface"
          >
            <table className="w-full min-w-[40rem] text-sm">
              <caption
                id={`div-${g.division.replace(" ", "-")}`}
                className="px-3 pt-2 text-left text-xs font-medium uppercase tracking-wide text-muted"
              >
                {g.division}
              </caption>
              <thead className="text-xs text-muted">
                <tr>
                  <th scope="col" className="px-3 py-1.5 text-left font-medium">
                    Team
                  </th>
                  <th scope="col" className="px-2 py-1.5 text-right font-medium">
                    W-L
                  </th>
                  <th
                    scope="col"
                    className="px-2 py-1.5 text-right font-medium"
                    title="AdjEM and rank after the week shown"
                  >
                    AdjEM
                  </th>
                  <th
                    scope="col"
                    className="px-2 py-1.5 text-right font-medium"
                    title="Mean simulated regular-season wins (middle 80% range)"
                  >
                    Proj. W
                  </th>
                  {ODDS.map((o) => (
                    <th
                      key={o.key}
                      scope="col"
                      title={o.title}
                      className="px-2 py-1.5 text-right font-medium"
                    >
                      {o.label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {g.rows.map((r) => {
                  const range = winRange(r.winDist);
                  return (
                    <tr key={r.team} className="border-t border-line/50 hover:bg-surface-raised">
                      <td className="whitespace-nowrap px-3 py-1">
                        <Link
                          href={`/teams/${r.team}?season=${at.season}&week=${at.week}`}
                          className="hover:text-accent"
                        >
                          {r.fullName}
                        </Link>
                      </td>
                      <td className="px-2 py-1 text-right tabular-nums">
                        {r.wins === null
                          ? "–"
                          : record({ wins: r.wins, losses: r.losses ?? 0, ties: r.ties ?? 0 })}
                      </td>
                      <td className="whitespace-nowrap px-2 py-1 text-right tabular-nums">
                        {signed(r.adjEm)}{" "}
                        <span className="text-xs text-muted">{r.adjEmRank ?? "–"}</span>
                      </td>
                      <td className="whitespace-nowrap px-2 py-1 text-right tabular-nums">
                        {r.meanWins.toFixed(1)}{" "}
                        <span className="text-xs text-subtle">
                          {range.low}–{range.high}
                        </span>
                      </td>
                      {ODDS.map((o) => (
                        <td
                          key={o.key}
                          className={`whitespace-nowrap px-2 py-1 text-right tabular-nums ${oddsTone(r[o.key])}`}
                        >
                          {oddsText(r[o.key])}
                        </td>
                      ))}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </section>
        ))}
      </div>

      <details className="max-w-3xl text-sm text-muted">
        <summary className="cursor-pointer text-fg">How the simulation works</summary>
        <ul className="mt-2 list-disc space-y-1 pl-5">
          <li>
            Each simulated season draws every team&apos;s true strength from the ratings and their
            uncertainty, so a team that is better than its rating is better in all its games. The
            strength then drifts week to week the way the rating model expects.
          </li>
          <li>
            Next week&apos;s games use the full model estimate (ratings, home field, expected
            quarterbacks, injury reports, as on{" "}
            <Link href="/matchups" className="text-accent hover:underline">
              Matchups
            </Link>
            ). Later games use ratings, home field and each team&apos;s current quarterback
            situation. A team that has clinched the top seed rests its starter in the final week two
            times in three.
          </li>
          <li>
            Standings use the NFL tiebreakers through strength of schedule (then a coin flip); on
            the real results they reproduce every playoff field of 2016–24. The bracket re-seeds
            after the Wild Card round, and the Super Bowl is neutral.
          </li>
          <li>
            &ldquo;100%&rdquo; means every simulated season, not a clinch; &ldquo;0%&rdquo; means
            none. Methodology and backtest: <code>apps/football/reports/season-sim.md</code>.
          </li>
        </ul>
      </details>
    </div>
  );
}
