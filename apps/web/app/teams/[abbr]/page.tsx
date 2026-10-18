import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { connection } from "next/server";
import {
  ratingsForWeek,
  ratingVersion,
  ratingWeeks,
  teamGames,
  teamRatingHistory,
  teamProjectionHistory,
  teamStaff,
  type RatingRow,
} from "@marketscope/db";
import { DataUnavailable, Notice } from "@/components/data-states";
import { RatingTrend } from "@/components/rating-trend";
import { SeasonOutlook } from "@/components/season-outlook";
import {
  fixed,
  isSyntheticVersion,
  parseRatingsQuery,
  rankBy,
  rankTone,
  record,
  resolveWeek,
  signed,
  weekLabel,
} from "@/lib/ratings-view";
import { isConnectionError } from "@/lib/server/api";
import { DatabaseNotConfiguredError, getDb } from "@/lib/server/db";
import { formatTimestamp } from "@/lib/time";

export async function generateMetadata(props: PageProps<"/teams/[abbr]">): Promise<Metadata> {
  const { abbr } = await props.params;
  return { title: abbr.toUpperCase() };
}

const FACTORS: {
  label: string;
  off: keyof RatingRow;
  def: keyof RatingRow;
  digits: number;
  higherOffIsBetter: boolean;
}[] = [
  {
    label: "Success rate",
    off: "offSuccessRate",
    def: "defSuccessRate",
    digits: 3,
    higherOffIsBetter: true,
  },
  {
    label: "Explosiveness (EPA per successful play)",
    off: "offExplosiveness",
    def: "defExplosiveness",
    digits: 2,
    higherOffIsBetter: true,
  },
  {
    label: "Field position (average start yard line)",
    off: "offStartYardline",
    def: "defStartYardline",
    digits: 1,
    higherOffIsBetter: true,
  },
  {
    label: "Finishing drives (points per trip inside the 40)",
    off: "offPointsPerOpp",
    def: "defPointsPerOpp",
    digits: 2,
    higherOffIsBetter: true,
  },
  {
    label: "Turnovers per game (giveaways / takeaways)",
    off: "offTurnovers",
    def: "defTurnovers",
    digits: 2,
    higherOffIsBetter: false,
  },
];

const ROLE: Record<string, string> = {
  HC: "Head coach",
  OC: "Offensive coordinator",
  DC: "Defensive coordinator",
  STC: "Special teams",
  PC: "Play-caller",
};

function Stat({
  label,
  value,
  rank,
  n,
  hint,
}: {
  label: string;
  value: string;
  rank?: number | null;
  n?: number;
  hint?: string;
}) {
  return (
    <div title={hint}>
      <div className="text-xs text-muted">{label}</div>
      <div className="mt-0.5 font-medium tabular-nums">
        {value}{" "}
        {rank !== undefined && (
          <span
            className={`rounded px-1 text-xs font-normal text-muted ${rankTone(rank, n ?? 32)}`}
          >
            #{rank ?? "–"}
          </span>
        )}
      </div>
    </div>
  );
}

export default async function TeamPage(props: PageProps<"/teams/[abbr]">) {
  await connection();
  const { abbr } = await props.params;
  const team = abbr.toUpperCase();
  if (!/^[A-Z]{2,3}$/.test(team)) notFound();
  const q = parseRatingsQuery(await props.searchParams);

  let data;
  try {
    const db = getDb();
    const version = await ratingVersion(db);
    if (!version) data = null;
    else {
      const weeks = await ratingWeeks(db, version);
      const at = resolveWeek(weeks, q);
      if (!at) data = null;
      else {
        const [league, history, games, staff, outlook] = await Promise.all([
          ratingsForWeek(db, { version, ...at }),
          teamRatingHistory(db, { version, team, season: at.season }),
          teamGames(db, { version, team, season: at.season }),
          teamStaff(db, { team, season: at.season }),
          teamProjectionHistory(db, { version, team, season: at.season }),
        ]);
        data = { version, weeks, at, league, history, games, staff, outlook };
      }
    }
  } catch (err) {
    if (err instanceof DatabaseNotConfiguredError || isConnectionError(err))
      return <DataUnavailable />;
    throw err;
  }
  if (!data)
    return (
      <Notice title="No ratings yet.">
        The ratings job has not written any snapshots to this database.
      </Notice>
    );

  const { version, weeks, at, league, history, games, staff, outlook } = data;
  const r = league.find((x) => x.team === team);
  if (!r) notFound();
  const n = league.length;
  const seasons = [...new Set(weeks.map((w) => w.season))].reverse();
  const throughWeek = history.filter((h) => h.week <= at.week);
  const ranks = FACTORS.map((f) => ({
    off: rankBy(league, (x) => x[f.off] as number | null, f.higherOffIsBetter).get(r) ?? null,
    def: rankBy(league, (x) => x[f.def] as number | null, !f.higherOffIsBetter).get(r) ?? null,
  }));

  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <p className="text-sm text-muted">
          <Link href={`/ratings?season=${at.season}&week=${at.week}`} className="hover:text-accent">
            ← Ratings
          </Link>
        </p>
        <h1 className="text-xl font-semibold tracking-tight">
          {r.fullName}{" "}
          <span className="text-base font-normal text-muted">
            {record(r)} · {r.division}
          </span>
        </h1>
        <p className="text-sm text-muted">
          Model estimates after {weekLabel(at.season, at.week)} {at.season} (point-in-time, model{" "}
          {version}).
        </p>
      </div>

      {isSyntheticVersion(version) && (
        <Notice tone="warn" title="Synthetic ratings: demo data, not real model output." />
      )}

      <form method="get" className="flex flex-wrap items-end gap-3 text-sm">
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
        <button
          type="submit"
          className="rounded border border-line bg-surface-raised px-3 py-1 hover:border-accent"
        >
          Show
        </button>
      </form>

      <section
        aria-label="Ratings"
        className="flex flex-wrap gap-x-8 gap-y-3 rounded-lg border border-line bg-surface px-4 py-3 text-sm"
      >
        <Stat
          label="AdjEM"
          value={`${signed(r.adjEm)} ± ${r.adjEmSe.toFixed(1)}`}
          rank={r.adjEmRank}
          n={n}
          hint="Expected margin vs an average team, neutral field"
        />
        <Stat label="AdjO (pts/drive)" value={fixed(r.adjO)} rank={r.adjORank} n={n} />
        <Stat
          label="AdjD (pts/drive)"
          value={fixed(r.adjD)}
          rank={r.adjDRank}
          n={n}
          hint="Lower is better"
        />
        <Stat label="AdjST (pts/game)" value={signed(r.adjSt)} rank={r.adjStRank} n={n} />
        <Stat label="AdjPace (drives)" value={fixed(r.adjPace, 1)} rank={r.adjPaceRank} n={n} />
        <Stat label="Luck (wins)" value={signed(r.luck)} rank={r.luckRank} n={n} />
        <Stat label="SOS" value={signed(r.sos)} rank={r.sosRank} n={n} />
        <Stat
          label="Remaining SOS"
          value={signed(r.remainingSos)}
          hint={`${r.remainingGames} regular-season games left`}
        />
        <Stat
          label="From preseason prior"
          value={`${Math.round(r.priorWeight * 100)}%`}
          hint="≈ share of the rating still carried by the preseason prior"
        />
      </section>

      <SeasonOutlook team={r.fullName} season={at.season} week={at.week} history={outlook} />

      <section aria-labelledby="trend" className="space-y-2">
        <h2 id="trend" className="text-sm font-medium uppercase tracking-wide text-muted">
          AdjEM by week, {at.season}
        </h2>
        <RatingTrend season={at.season} points={throughWeek} />
      </section>

      <div className="grid gap-6 lg:grid-cols-2">
        <section aria-labelledby="factors" className="space-y-2">
          <h2 id="factors" className="text-sm font-medium uppercase tracking-wide text-muted">
            Five Factors (season to date)
          </h2>
          <table className="w-full text-sm">
            <thead className="text-xs text-muted">
              <tr>
                <th scope="col" className="py-1 text-left font-medium">
                  Factor
                </th>
                <th scope="col" className="py-1 text-right font-medium">
                  Offense
                </th>
                <th scope="col" className="py-1 text-right font-medium">
                  Defense
                </th>
              </tr>
            </thead>
            <tbody>
              {FACTORS.map((f, i) => (
                <tr key={f.label} className="border-t border-line/50">
                  <td className="py-1 pr-2">{f.label}</td>
                  {(["off", "def"] as const).map((side) => (
                    <td key={side} className="py-1 text-right tabular-nums">
                      {fixed(r[f[side]] as number | null, f.digits)}{" "}
                      <span
                        className={`rounded px-1 text-xs text-muted ${rankTone(ranks[i]![side], n)}`}
                      >
                        #{ranks[i]![side] ?? "–"}
                      </span>
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </section>

        <section aria-labelledby="luck" className="space-y-2">
          <h2 id="luck" className="text-sm font-medium uppercase tracking-wide text-muted">
            Luck
          </h2>
          <table className="w-full text-sm">
            <tbody>
              {(
                [
                  ["Wins (ties count half)", (r.wins + r.ties / 2).toString()],
                  ["Expected wins (from game-by-game efficiency)", fixed(r.expectedWins, 1)],
                  ["Pythagorean wins (from points)", fixed(r.pythagWins, 1)],
                  ["Luck: wins − expected", signed(r.luck)],
                  ["One-score games: wins − expected", signed(r.oneScoreLuck)],
                  ["Fumble-recovery luck (EPA)", signed(r.fumbleLuck)],
                  ["Interception luck (EPA)", signed(r.intLuck)],
                  ["Field-goal luck (points)", signed(r.fgLuck)],
                  ["Return and defensive TDs (net)", signed(r.returnTdDiff, 0)],
                ] as const
              ).map(([k, v]) => (
                <tr key={k} className="border-t border-line/50">
                  <td className="py-1 pr-2">{k}</td>
                  <td className="py-1 text-right tabular-nums">{v}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      </div>

      <section aria-labelledby="schedule" className="space-y-2">
        <h2 id="schedule" className="text-sm font-medium uppercase tracking-wide text-muted">
          Schedule
        </h2>
        <div className="overflow-x-auto rounded-lg border border-line bg-surface">
          <table className="w-full min-w-[40rem] text-sm">
            <thead className="border-b border-line text-xs text-muted">
              <tr>
                <th scope="col" className="px-2 py-2 text-left font-medium">
                  Week
                </th>
                <th scope="col" className="px-2 py-2 text-left font-medium">
                  Opponent
                </th>
                <th
                  scope="col"
                  className="px-2 py-2 text-right font-medium"
                  title="Opponent's AdjEM rank before the game / now"
                >
                  Opp rank then / now
                </th>
                <th scope="col" className="px-2 py-2 text-right font-medium">
                  Result
                </th>
                <th
                  scope="col"
                  className="px-2 py-2 text-right font-medium"
                  title="Last model estimate before kickoff (live forward test)"
                >
                  Model estimate
                </th>
              </tr>
            </thead>
            <tbody>
              {games.map((g) => {
                const played = g.teamScore !== null && g.opponentScore !== null;
                const res = played
                  ? g.teamScore! > g.opponentScore!
                    ? "W"
                    : g.teamScore! < g.opponentScore!
                      ? "L"
                      : "T"
                  : null;
                return (
                  <tr key={g.gameId} className="border-b border-line/50 last:border-0">
                    <td className="whitespace-nowrap px-2 py-1">{weekLabel(at.season, g.week)}</td>
                    <td className="whitespace-nowrap px-2 py-1">
                      {g.neutralSite ? "vs" : g.isHome ? "vs" : "at"}{" "}
                      <Link
                        href={`/teams/${g.opponent}?season=${at.season}`}
                        className="hover:text-accent"
                      >
                        {g.opponent}
                      </Link>
                      {g.neutralSite && <span className="text-xs text-subtle"> (neutral)</span>}
                    </td>
                    <td className="px-2 py-1 text-right tabular-nums text-muted">
                      {g.opponentRankThen ?? "–"} / {g.opponentRankNow ?? "–"}
                    </td>
                    <td className="whitespace-nowrap px-2 py-1 text-right tabular-nums">
                      {played ? (
                        `${res} ${g.teamScore}–${g.opponentScore}`
                      ) : (
                        <time dateTime={g.kickoffUtc} className="text-muted">
                          {formatTimestamp(g.kickoffUtc)}
                        </time>
                      )}
                    </td>
                    <td className="whitespace-nowrap px-2 py-1 text-right tabular-nums">
                      {g.modelMargin === null ? (
                        <span className="text-subtle">–</span>
                      ) : (
                        <span title="Model estimate, not a pick">
                          {g.modelTeamScore !== null
                            ? `${g.modelTeamScore.toFixed(0)}–${g.modelOpponentScore!.toFixed(0)} · `
                            : ""}
                          {signed(g.modelMargin)} · {Math.round(g.modelWinProb! * 100)}%
                        </span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <p className="text-xs text-subtle">
          Model estimates are the last ones made before kickoff by the live forward test (from
          2026-10-18); they are estimates with a typical miss of about 10 points, not picks.
        </p>
      </section>

      {staff.length > 0 && (
        <section aria-labelledby="staff" className="space-y-2">
          <h2 id="staff" className="text-sm font-medium uppercase tracking-wide text-muted">
            Coaching staff, {at.season}
          </h2>
          <ul className="grid gap-1 text-sm sm:grid-cols-2">
            {staff.map((s) => (
              <li key={`${s.role}-${s.coachName}-${s.fromWeek}`}>
                <span className="text-muted">{ROLE[s.role] ?? s.role}:</span> {s.coachName}
                {(s.fromWeek > 1 || s.toWeek < 18) && (
                  <span className="text-xs text-subtle">
                    {" "}
                    (weeks {s.fromWeek}–{s.toWeek})
                  </span>
                )}
                {s.offensePlaycaller && (
                  <span className="ml-1 rounded bg-surface-raised px-1 text-xs">calls offense</span>
                )}
                {s.defensePlaycaller && (
                  <span className="ml-1 rounded bg-surface-raised px-1 text-xs">calls defense</span>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
