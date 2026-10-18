import type { Metadata } from "next";
import Link from "next/link";
import { connection } from "next/server";
import {
  DEFAULT_MODEL_VERSION,
  forwardTest,
  modelRunRecords,
  ratingVersion,
} from "@marketscope/db";
import { DataUnavailable, Notice } from "@/components/data-states";
import {
  favoriteText,
  MIN_CALIBRATION_GAMES,
  MIN_CI_GAMES,
  percent,
  scorecard,
  spreadText,
  testRecordRows,
  type Estimate,
  type PairedMetric,
} from "@/lib/model-view";
import { isSyntheticVersion, signed, weekLabel } from "@/lib/ratings-view";
import { isConnectionError } from "@/lib/server/api";
import { DatabaseNotConfiguredError, getDb } from "@/lib/server/db";
import { formatTimestamp } from "@/lib/time";

export const metadata: Metadata = { title: "Model scorecard" };

const ci = (lo: number | null, hi: number | null, digits: number, sign = false) =>
  lo === null || hi === null
    ? null
    : `${sign ? signed(lo, digits) : lo.toFixed(digits)} to ${sign ? signed(hi, digits) : hi.toFixed(digits)}`;

function EstimateCell({
  e,
  digits = 2,
  sign = false,
}: {
  e: Estimate | null;
  digits?: number;
  sign?: boolean;
}) {
  if (!e) return <td className="px-3 py-1.5 text-right text-subtle">–</td>;
  const range = ci(e.lo, e.hi, digits, sign);
  return (
    <td className="whitespace-nowrap px-3 py-1.5 text-right tabular-nums">
      {sign ? signed(e.value, digits) : e.value.toFixed(digits)}
      {range && <span className="block text-xs text-subtle">{range}</span>}
    </td>
  );
}

function MetricRow({
  label,
  m,
  digits,
  note,
}: {
  label: string;
  m: PairedMetric | null;
  digits: number;
  note: string;
}) {
  return (
    <tr className="border-t border-line/60">
      <th scope="row" className="px-4 py-2 text-left font-normal">
        {label}
        <span className="block text-xs text-subtle">{note}</span>
      </th>
      {m ? (
        <>
          <td className="px-3 py-2 text-right tabular-nums">{m.model.toFixed(digits)}</td>
          <td className="px-3 py-2 text-right tabular-nums">{m.close.toFixed(digits)}</td>
          <td className="whitespace-nowrap px-3 py-2 text-right tabular-nums">
            {signed(m.diff, digits)}
            <span className="block text-xs text-subtle">
              {m.ci ? ci(m.ci[0], m.ci[1], digits, true) : `CI after ${MIN_CI_GAMES} games`}
            </span>
          </td>
          <td className="px-3 py-2 text-right tabular-nums text-muted">{m.games}</td>
        </>
      ) : (
        <td colSpan={4} className="px-3 py-2 text-right text-subtle">
          not available yet
        </td>
      )}
    </tr>
  );
}

export default async function ModelPage() {
  await connection();
  let data;
  try {
    const db = getDb();
    const version = await ratingVersion(db);
    data = version
      ? { version, ft: await forwardTest(db, version), runs: await modelRunRecords(db, version) }
      : null;
  } catch (err) {
    if (err instanceof DatabaseNotConfiguredError || isConnectionError(err))
      return <DataUnavailable />;
    throw err;
  }

  if (!data) {
    return (
      <div className="space-y-4">
        <h1 className="text-xl font-semibold tracking-tight">Model scorecard</h1>
        <Notice title="No model output yet.">
          The football jobs have not written ratings or estimates to this database.
        </Notice>
      </div>
    );
  }

  const { version, ft, runs } = data;
  const s = scorecard(ft.scored);
  const test = runs.find((r) => r.runKind === "test");
  const recent = [...ft.scored].reverse().slice(0, 20);

  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <h1 className="text-xl font-semibold tracking-tight">Model scorecard</h1>
        <p className="max-w-3xl text-sm text-muted">
          How the <strong className="text-fg">model estimates</strong> ({version}) have done. The
          live forward test scores each game&apos;s last estimate made before kickoff (stored
          immutably) against the result and the nflverse closing line. The parameters were frozen
          before the 2025 test and before any live estimate. Lower is better for every metric. Not
          betting advice.
        </p>
      </div>

      {isSyntheticVersion(version) && (
        <Notice tone="warn" title="Synthetic scorecard: demo data, not real model output.">
          This database holds generated games, estimates and evaluation records for development and
          testing.
        </Notice>
      )}

      <section aria-labelledby="live" className="space-y-3">
        <h2 id="live" className="text-sm font-medium uppercase tracking-wide text-muted">
          Live forward test
        </h2>
        <p className="text-sm text-muted">
          {s.games} game{s.games === 1 ? "" : "s"} final, {ft.pending} awaiting a result
          {ft.firstPredictedAt && <> · first estimate {formatTimestamp(ft.firstPredictedAt)}</>}.
          {s.favoriteWon.decided > 0 && (
            <>
              {" "}
              The model&apos;s favorite won {s.favoriteWon.won} of {s.favoriteWon.decided}.
            </>
          )}
        </p>
        {s.games === 0 ? (
          <Notice title="No scored games yet.">
            Estimates are stored before kickoff; they are scored here once the game is final.
          </Notice>
        ) : (
          <>
            <div className="overflow-x-auto rounded-lg border border-line bg-surface">
              <table
                className="w-full min-w-[36rem] text-sm"
                aria-label="Live forward test vs the close"
              >
                <thead className="text-xs text-muted">
                  <tr>
                    <th scope="col" className="px-4 py-2 text-left font-medium">
                      Metric
                    </th>
                    <th scope="col" className="px-3 py-2 text-right font-medium">
                      Model
                    </th>
                    <th scope="col" className="px-3 py-2 text-right font-medium">
                      Close
                    </th>
                    <th scope="col" className="px-3 py-2 text-right font-medium">
                      Model − close (95% CI)
                    </th>
                    <th scope="col" className="px-3 py-2 text-right font-medium">
                      Games
                    </th>
                  </tr>
                </thead>
                <tbody>
                  <MetricRow label="Margin MAE" m={s.margin} digits={2} note="points per game" />
                  <MetricRow
                    label="Win-probability Brier"
                    m={s.brier}
                    digits={3}
                    note="close: no-vig moneylines"
                  />
                  <MetricRow label="Total MAE" m={s.total} digits={2} note="points per game" />
                </tbody>
              </table>
            </div>
            <p className="text-xs text-subtle">
              Differences are paired on the same games; the interval resamples games (2,000 draws,
              fixed seed). An interval that includes zero means the forward test can&apos;t yet tell
              the two apart.
            </p>

            <div className="overflow-x-auto rounded-lg border border-line bg-surface">
              <table className="w-full min-w-[32rem] text-sm" aria-label="Margin error by week">
                <thead className="text-xs text-muted">
                  <tr>
                    <th scope="col" className="px-4 py-2 text-left font-medium">
                      Week
                    </th>
                    <th scope="col" className="px-3 py-2 text-right font-medium">
                      Games
                    </th>
                    <th scope="col" className="px-3 py-2 text-right font-medium">
                      Model MAE
                    </th>
                    <th scope="col" className="px-3 py-2 text-right font-medium">
                      Close MAE
                    </th>
                    <th scope="col" className="px-3 py-2 text-right font-medium">
                      Cumulative model / close
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {s.weeks.map((w) => (
                    <tr key={`${w.season}-${w.week}`} className="border-t border-line/60">
                      <td className="px-4 py-1.5">
                        <Link
                          href={`/matchups?season=${w.season}&week=${w.week}`}
                          className="hover:text-accent"
                        >
                          {w.season} {weekLabel(w.season, w.week)}
                        </Link>
                      </td>
                      <td className="px-3 py-1.5 text-right tabular-nums">{w.games}</td>
                      <td className="px-3 py-1.5 text-right tabular-nums">
                        {w.modelMae.toFixed(2)}
                      </td>
                      <td className="px-3 py-1.5 text-right tabular-nums">
                        {w.closeMae === null ? "–" : w.closeMae.toFixed(2)}
                      </td>
                      <td className="px-3 py-1.5 text-right tabular-nums text-muted">
                        {w.cumulativeModelMae.toFixed(2)} /{" "}
                        {w.cumulativeCloseMae === null ? "–" : w.cumulativeCloseMae.toFixed(2)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {s.calibration ? (
              <div className="overflow-x-auto rounded-lg border border-line bg-surface">
                <table className="w-full min-w-[28rem] text-sm" aria-label="Calibration">
                  <caption className="px-4 pt-2 text-left text-xs text-muted">
                    Calibration: when the model gave the home team X%, how often did it win?
                  </caption>
                  <thead className="text-xs text-muted">
                    <tr>
                      <th scope="col" className="px-4 py-2 text-left font-medium">
                        Home win probability
                      </th>
                      <th scope="col" className="px-3 py-2 text-right font-medium">
                        Games
                      </th>
                      <th scope="col" className="px-3 py-2 text-right font-medium">
                        Average estimate
                      </th>
                      <th scope="col" className="px-3 py-2 text-right font-medium">
                        Home won
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {s.calibration.map((b) => (
                      <tr key={b.label} className="border-t border-line/60">
                        <td className="px-4 py-1.5">{b.label}</td>
                        <td className="px-3 py-1.5 text-right tabular-nums">{b.games}</td>
                        <td className="px-3 py-1.5 text-right tabular-nums">{percent(b.meanP)}</td>
                        <td className="px-3 py-1.5 text-right tabular-nums">
                          {percent(b.homeWinRate)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="text-xs text-subtle">
                A calibration table appears after {MIN_CALIBRATION_GAMES} scored games.
              </p>
            )}

            <div className="overflow-x-auto rounded-lg border border-line bg-surface">
              <table className="w-full min-w-[40rem] text-sm" aria-label="Recent scored games">
                <caption className="px-4 pt-2 text-left text-xs text-muted">
                  Most recent scored games
                </caption>
                <thead className="text-xs text-muted">
                  <tr>
                    <th scope="col" className="px-4 py-2 text-left font-medium">
                      Game
                    </th>
                    <th scope="col" className="px-3 py-2 text-left font-medium">
                      Model estimate
                    </th>
                    <th scope="col" className="px-3 py-2 text-left font-medium">
                      Close
                    </th>
                    <th scope="col" className="px-3 py-2 text-right font-medium">
                      Final
                    </th>
                    <th scope="col" className="px-3 py-2 text-right font-medium">
                      Model / close error
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {recent.map((r) => {
                    const margin = r.homeFinal - r.awayFinal;
                    return (
                      <tr key={r.gameId} className="border-t border-line/60">
                        <td className="whitespace-nowrap px-4 py-1.5">
                          {r.awayTeam} @ {r.homeTeam}{" "}
                          <span className="text-xs text-subtle">{weekLabel(r.season, r.week)}</span>
                        </td>
                        <td className="whitespace-nowrap px-3 py-1.5">
                          {favoriteText(r.homeTeam, r.awayTeam, r.expectedMargin)}
                        </td>
                        <td className="whitespace-nowrap px-3 py-1.5">
                          {r.closeHomeSpread === null
                            ? "–"
                            : spreadText(r.homeTeam, r.awayTeam, r.closeHomeSpread)}
                        </td>
                        <td className="whitespace-nowrap px-3 py-1.5 text-right tabular-nums">
                          {r.awayFinal}–{r.homeFinal}
                        </td>
                        <td className="whitespace-nowrap px-3 py-1.5 text-right tabular-nums">
                          {Math.abs(r.expectedMargin - margin).toFixed(1)} /{" "}
                          {r.closeHomeSpread === null
                            ? "–"
                            : Math.abs(-r.closeHomeSpread - margin).toFixed(1)}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </>
        )}
      </section>

      <section aria-labelledby="test" className="space-y-3">
        <h2 id="test" className="text-sm font-medium uppercase tracking-wide text-muted">
          One-time test{test ? `: ${test.seasons} season` : ""}
        </h2>
        {!test ? (
          <Notice title="No test record loaded.">
            The one-time test record has not been loaded into this database.
          </Notice>
        ) : (
          <>
            <p className="max-w-3xl text-sm text-muted">
              The frozen model was run once on the untouched {test.seasons} season ({test.games}{" "}
              games), walk-forward, next to simple benchmarks and the closing line.
              {version === DEFAULT_MODEL_VERSION &&
                " It beat the naive baseline clearly, finished level with Elo and SRS (intervals include zero), and was less accurate than the close."}
            </p>
            <div className="overflow-x-auto rounded-lg border border-line bg-surface">
              <table
                className="w-full min-w-[48rem] text-sm"
                aria-label={`${test.seasons} test record`}
              >
                <thead className="text-xs text-muted">
                  <tr>
                    <th scope="col" className="px-4 py-2 text-left font-medium">
                      Model
                    </th>
                    <th scope="col" className="px-3 py-2 text-right font-medium">
                      Margin MAE
                    </th>
                    <th scope="col" className="px-3 py-2 text-right font-medium">
                      vs close
                    </th>
                    <th scope="col" className="px-3 py-2 text-right font-medium">
                      {version} vs this
                    </th>
                    <th scope="col" className="px-3 py-2 text-right font-medium">
                      Brier
                    </th>
                    <th scope="col" className="px-3 py-2 text-right font-medium">
                      Log loss
                    </th>
                    <th scope="col" className="px-3 py-2 text-right font-medium">
                      Total MAE
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {testRecordRows(test.metrics, version).map((r) => (
                    <tr
                      key={r.model}
                      className={`border-t border-line/60 ${r.model === version ? "bg-accent/10" : ""}`}
                    >
                      <th
                        scope="row"
                        className="whitespace-nowrap px-4 py-1.5 text-left font-normal"
                      >
                        {r.model}
                      </th>
                      <EstimateCell e={r.marginMae} />
                      <EstimateCell e={r.vsClose} sign />
                      <EstimateCell e={r.versionVs} sign />
                      <EstimateCell e={r.brier} digits={3} />
                      <EstimateCell e={r.logLoss} digits={3} />
                      <EstimateCell e={r.totalMae} />
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="text-xs text-subtle">
              95% intervals from a paired game bootstrap. &ldquo;vs close&rdquo; is that model minus
              the close; &ldquo;{version} vs this&rdquo; is {version} minus that model (negative
              favors {version}). Ran {formatTimestamp(test.ranAt)} · params sha256{" "}
              <code>{test.paramsSha256.slice(0, 12)}</code> · code{" "}
              <code>{test.codeSha.slice(0, 7)}</code>
              {test.notes && <> · {test.notes}</>}. Full report:{" "}
              <code>apps/football/reports/test-2025.md</code>.
            </p>
          </>
        )}
      </section>
    </div>
  );
}
