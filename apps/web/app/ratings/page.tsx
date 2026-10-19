import type { Metadata } from "next";
import Link from "next/link";
import { connection } from "next/server";
import { ratingsForWeek, ratingVersion, ratingWeeks, type RatingRow } from "@marketscope/db";
import { DataUnavailable, Notice } from "@/components/data-states";
import {
  fixed,
  isSyntheticVersion,
  parseRatingsQuery,
  rankTone,
  rankText,
  record,
  resolveWeek,
  signed,
  sortRatings,
  weekLabel,
  type SortKey,
} from "@/lib/ratings-view";
import { isConnectionError } from "@/lib/server/api";
import { DatabaseNotConfiguredError, getDb } from "@/lib/server/db";

export const metadata: Metadata = { title: "Ratings" };

const COLUMNS: { key: SortKey | null; label: string; title: string }[] = [
  { key: "team", label: "Team", title: "Sort by team name" },
  { key: null, label: "W-L", title: "Record to date (playoffs included)" },
  {
    key: "adjEm",
    label: "AdjEM",
    title: "Expected margin vs an average team on a neutral field (points), ± 1 SE",
  },
  { key: "adjO", label: "AdjO", title: "Points per drive vs an average defense" },
  {
    key: "adjD",
    label: "AdjD",
    title: "Points per drive allowed vs an average offense (lower is better)",
  },
  { key: "adjSt", label: "AdjST", title: "Special-teams points per game vs average" },
  { key: "adjPace", label: "AdjPace", title: "Drives per team-game vs an average opponent" },
  { key: "luck", label: "Luck", title: "Wins minus expected wins" },
  { key: "sos", label: "SOS", title: "Average current AdjEM of opponents played (venue-adjusted)" },
  { key: null, label: "Opp O / D", title: "Average AdjO and AdjD of opponents played" },
];

function Ranked({ value, rank, n }: { value: string; rank: number | null; n: number }) {
  return (
    <td className="whitespace-nowrap px-2 py-1 text-right tabular-nums">
      <span>{value}</span>{" "}
      <span
        className={`inline-block min-w-7 rounded px-1 text-xs ${rankText(rank, n)} ${rankTone(rank, n)}`}
      >
        {rank ?? "–"}
      </span>
    </td>
  );
}

export default async function RatingsPage(props: PageProps<"/ratings">) {
  await connection();
  const q = parseRatingsQuery(await props.searchParams);

  let data;
  try {
    const db = getDb();
    const version = await ratingVersion(db);
    if (!version) data = null;
    else {
      const weeks = await ratingWeeks(db, version);
      const at = resolveWeek(weeks, q);
      const rows = at ? await ratingsForWeek(db, { version, ...at }) : [];
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
        <h1 className="text-xl font-semibold tracking-tight">MarketScope Ratings</h1>
        <Notice title="No ratings yet.">
          The ratings job has not written any snapshots to this database.
        </Notice>
      </div>
    );
  }

  const { version, weeks, at, rows } = data;
  const shown = sortRatings(
    q.conference ? rows.filter((r) => r.conference === q.conference) : rows,
    q.sort,
  );
  const n = rows.length;
  const seasons = [...new Set(weeks.map((w) => w.season))].reverse();
  const seasonWeeks = weeks.filter((w) => w.season === at.season);
  const href = (patch: Record<string, string | number | null>) => {
    const p = new URLSearchParams();
    const merged = { season: at.season, week: at.week, sort: q.sort, conf: q.conference, ...patch };
    for (const [k, v] of Object.entries(merged))
      if (v !== null && v !== "adjEm") p.set(k, String(v));
    return `/ratings?${p.toString()}`;
  };

  return (
    <div className="space-y-5">
      <div className="space-y-1">
        <h1 className="text-xl font-semibold tracking-tight">MarketScope Ratings</h1>
        <p className="max-w-3xl text-sm text-muted">
          Opponent-adjusted offense, defense, special teams and pace, KenPom-style. Every number is
          a <strong className="text-fg">model estimate</strong> from games played by the date shown
          (point-in-time). AdjEM is the expected margin against an average team on a neutral field.
          As a game forecast, the model missed by 10.1 points on average in the 2025 test (the
          market close: 9.7).
        </p>
      </div>

      {isSyntheticVersion(version) && (
        <Notice tone="warn" title="Synthetic ratings: demo data, not real model output.">
          This database holds generated ratings for development and testing.
        </Notice>
      )}

      <form
        method="get"
        action="/ratings"
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
          <span className="text-xs text-muted">Ratings after</span>
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
        {q.sort !== "adjEm" && <input type="hidden" name="sort" value={q.sort} />}
        <button
          type="submit"
          className="rounded border border-line bg-surface-raised px-3 py-1 hover:border-accent"
        >
          Show
        </button>
        <span className="text-xs text-subtle">
          {at.season} · {weekLabel(at.season, at.week)} · model {version}
        </span>
      </form>

      <div className="overflow-x-auto rounded-lg border border-line bg-surface">
        <table
          className="w-full min-w-[56rem] text-sm"
          aria-label={`Ratings, ${at.season} ${weekLabel(at.season, at.week)}`}
        >
          <thead className="border-b border-line text-xs text-muted">
            <tr>
              <th scope="col" className="px-2 py-2 text-right font-medium">
                Rk
              </th>
              {COLUMNS.map((c) => (
                <th
                  key={c.label}
                  scope="col"
                  title={c.title}
                  aria-sort={c.key && c.key === q.sort ? "ascending" : undefined}
                  className={`px-2 py-2 font-medium ${c.key === "team" ? "text-left" : "text-right"}`}
                >
                  {c.key ? (
                    <Link
                      href={href({ sort: c.key })}
                      className={c.key === q.sort ? "text-accent" : "hover:text-fg"}
                    >
                      {c.label}
                    </Link>
                  ) : (
                    c.label
                  )}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {shown.map((r: RatingRow) => (
              <tr
                key={r.team}
                className="border-b border-line/50 last:border-0 hover:bg-surface-raised"
              >
                <td className="px-2 py-1 text-right tabular-nums text-muted">{r.adjEmRank}</td>
                <td className="whitespace-nowrap px-2 py-1">
                  <Link
                    href={`/teams/${r.team}?season=${at.season}&week=${at.week}`}
                    className="hover:text-accent"
                  >
                    {r.fullName}
                  </Link>{" "}
                  <span className="text-xs text-subtle">{r.division}</span>
                </td>
                <td className="px-2 py-1 text-right tabular-nums">{record(r)}</td>
                <td
                  className={`whitespace-nowrap px-2 py-1 text-right font-medium tabular-nums ${rankTone(r.adjEmRank, n)}`}
                  title={`± ${r.adjEmSe.toFixed(1)} (1 SE)`}
                >
                  {signed(r.adjEm)}{" "}
                  <span className={`text-xs font-normal ${rankText(r.adjEmRank, n)}`}>
                    ±{r.adjEmSe.toFixed(1)}
                  </span>
                </td>
                <Ranked value={fixed(r.adjO)} rank={r.adjORank} n={n} />
                <Ranked value={fixed(r.adjD)} rank={r.adjDRank} n={n} />
                <Ranked value={signed(r.adjSt)} rank={r.adjStRank} n={n} />
                <Ranked value={fixed(r.adjPace, 1)} rank={r.adjPaceRank} n={n} />
                <Ranked value={signed(r.luck)} rank={r.luckRank} n={n} />
                <Ranked value={signed(r.sos)} rank={r.sosRank} n={n} />
                <td className="whitespace-nowrap px-2 py-1 text-right tabular-nums text-muted">
                  {fixed(r.oppAdjO)} / {fixed(r.oppAdjD)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <details className="max-w-3xl text-sm text-muted">
        <summary className="cursor-pointer text-fg">How to read this table</summary>
        <ul className="mt-2 list-disc space-y-1 pl-5">
          <li>
            <strong className="text-fg">AdjEM</strong> = (AdjO − AdjD) × drives per game + AdjST. ±
            is one standard error from the model&apos;s uncertainty.
          </li>
          <li>
            <strong className="text-fg">AdjO / AdjD</strong>: points per drive scored and allowed
            against an average opponent, built from opponent-adjusted EPA, success rate and points
            per drive.
          </li>
          <li>
            <strong className="text-fg">Luck</strong>: wins minus the wins expected from how well
            the team played each game. <strong className="text-fg">SOS</strong>: average current
            AdjEM of opponents faced.
          </li>
          <li>
            Small numbers after values are league ranks; shading marks the top and bottom eighths.
            Methodology: <code>docs/RATINGS.md</code>.
          </li>
        </ul>
      </details>
    </div>
  );
}
