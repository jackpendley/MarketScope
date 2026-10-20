import type { Metadata } from "next";
import Link from "next/link";
import { connection } from "next/server";
import { listPaperPositions, paperSeasons, type PaperPositionRow } from "@marketscope/db";
import { formatPoint } from "@marketscope/shared";
import { DataUnavailable, Notice } from "@/components/data-states";
import { PortfolioCharts } from "@/components/portfolio-charts";
import { isConnectionError } from "@/lib/server/api";
import { DatabaseNotConfiguredError, getDb } from "@/lib/server/db";
import {
  equityByDay,
  isModeKey,
  MODES,
  signed,
  STRATEGIES,
  strategyInfo,
  summarise,
  TEASER_PRICE,
  type ModeKey,
} from "@/lib/portfolio-view";
import { formatTimestamp } from "@/lib/time";

export const metadata: Metadata = { title: "Paper Portfolio" };

const first = (v: string | string[] | undefined) => (Array.isArray(v) ? v[0] : v);
const RECENT = 60;
const BOOKS: Record<string, string> = { williamhill_us: "Caesars", draftkings: "DraftKings" };

function describe(p: PaperPositionRow): string {
  if (p.market === "total") return `${p.side === "under" ? "Under" : "Over"} ${p.line}`;
  const line = formatPoint(p.line, "spreads");
  return p.market === "teaser_leg"
    ? `${p.side} ${line} → ${formatPoint(p.teasedLine, "spreads")} (teaser leg)`
    : `${p.side} ${line}`;
}

export default async function PortfolioPage(props: PageProps<"/portfolio">) {
  await connection();
  const sp = await props.searchParams;
  const modeParam = first(sp.mode);
  const mode: ModeKey = isModeKey(modeParam) ? modeParam : "all";
  const strategyParam = first(sp.strategy);
  const strategy = STRATEGIES.some((s) => s.id === strategyParam) ? strategyParam! : null;

  let rows: PaperPositionRow[];
  let season: number;
  try {
    const db = getDb();
    const seasons = await paperSeasons(db);
    season = Number(first(sp.season)) || seasons[0] || new Date().getUTCFullYear();
    rows = await listPaperPositions(db, { season, modes: MODES[mode].modes });
  } catch (err) {
    if (err instanceof DatabaseNotConfiguredError || isConnectionError(err))
      return <DataUnavailable />;
    throw err;
  }

  const summaries = summarise(rows);
  const { points, strategies } = equityByDay(rows);
  const labels = Object.fromEntries(STRATEGIES.map((s) => [s.id, s.label]));
  const synthetic = rows.some((r) => r.mode === "synthetic");
  const reconstructed = rows.some((r) => r.mode === "reconstructed");
  const open = rows.filter((r) => r.result === null && (!strategy || r.strategy === strategy));
  const graded = rows
    .filter((r) => r.result !== null && (!strategy || r.strategy === strategy))
    .slice(-RECENT)
    .reverse();
  const clv = summaries
    .filter((s) => s.meanClv !== null)
    .map((s) => ({
      id: s.info.id,
      label: s.info.label,
      meanClv: Math.round(s.meanClv! * 100) / 100,
      count: s.clvCount,
    }));
  const href = (over: Record<string, string | null>) => {
    const p = new URLSearchParams();
    const next = { mode, strategy, ...over };
    if (next.mode && next.mode !== "all") p.set("mode", next.mode);
    if (next.strategy) p.set("strategy", next.strategy);
    const q = p.toString();
    return q ? `/portfolio?${q}` : "/portfolio";
  };

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <h1 className="text-xl font-semibold tracking-tight">Paper Portfolio</h1>
        <p className="max-w-3xl text-sm text-muted">
          A live, <strong className="text-fg">hypothetical</strong> forward test of every
          pre-registered system on the{" "}
          <Link href="/systems" className="text-accent underline">
            Systems
          </Link>{" "}
          page, whatever its backtest verdict. Before each kickoff the paper job records the
          position at Caesars&apos; posted line and price (DraftKings if Caesars has none), and
          grades it after the game against the result and Pinnacle&apos;s closing line. Wong teaser
          legs are paired in kickoff order each week at {TEASER_PRICE}. No money is wagered; this is
          analysis, not betting advice. {season} season.
        </p>
      </div>

      {synthetic && (
        <Notice tone="warn" title="Synthetic positions: not real odds or results.">
          This database contains generated demo positions for development and testing.
        </Notice>
      )}
      {reconstructed && mode !== "live" && (
        <Notice title="Includes reconstructed positions.">
          Games played before the paper job started were filled in afterwards by the same rules,
          using only snapshots stored at least 10 minutes before kickoff. Live positions are placed
          before kickoff by the scheduled job.
        </Notice>
      )}

      <nav aria-label="Position source" className="flex gap-1 text-sm">
        {(Object.keys(MODES) as ModeKey[]).map((k) => (
          <Link
            key={k}
            href={href({ mode: k })}
            aria-current={mode === k ? "page" : undefined}
            className={`rounded border px-3 py-1 ${mode === k ? "border-accent text-fg" : "border-line text-muted hover:text-fg"}`}
          >
            {MODES[k].label}
          </Link>
        ))}
      </nav>

      {rows.length === 0 ? (
        <Notice title="No paper positions yet.">
          Positions appear once the paper job runs after the next odds collection.
        </Notice>
      ) : (
        <>
          <PortfolioCharts
            points={points}
            strategies={strategies}
            labels={labels}
            initiallyShown={strategies.filter((id) =>
              ["wong-V0", "wong-V1", "F8", "F10"].includes(id),
            )}
            clv={clv}
            equitySummary={summaries
              .filter((s) => s.settled > 0)
              .map((s) => `${s.info.id} ${signed(s.units, 1)} units over ${s.settled}`)
              .join("; ")}
            clvSummary={clv.map((c) => `${c.id} ${signed(c.meanClv)} points`).join("; ")}
          />

          <section aria-labelledby="by-strategy" className="space-y-2">
            <h2 id="by-strategy" className="text-sm font-medium uppercase tracking-wide text-muted">
              By strategy
            </h2>
            <div className="relative overflow-x-auto rounded-lg border border-line bg-surface">
              <table className="w-full min-w-[760px] text-sm">
                <caption className="sr-only">Paper results by strategy</caption>
                <thead>
                  <tr className="text-left text-xs text-muted">
                    <th scope="col" className="px-4 py-2 font-medium">
                      Strategy
                    </th>
                    <th scope="col" className="px-3 py-2 font-medium">
                      Backtest
                    </th>
                    <th scope="col" className="px-3 py-2 text-right font-medium">
                      Positions
                    </th>
                    <th scope="col" className="px-3 py-2 font-medium">
                      Won–lost–pushed
                    </th>
                    <th scope="col" className="px-3 py-2 text-right font-medium">
                      Settled
                    </th>
                    <th scope="col" className="px-3 py-2 text-right font-medium">
                      Units
                    </th>
                    <th scope="col" className="px-3 py-2 text-right font-medium">
                      Return
                    </th>
                    <th scope="col" className="px-3 py-2 text-right font-medium">
                      Mean CLV
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {summaries.map((s) => (
                    <tr key={s.info.id} className="border-t border-line/60">
                      <th scope="row" className="px-4 py-2 text-left font-normal">
                        <Link href={href({ strategy: s.info.id })} className="hover:text-accent">
                          {s.info.label}
                        </Link>
                      </th>
                      <td className="px-3 py-2 text-xs text-muted">{s.info.backtest}</td>
                      <td className="px-3 py-2 text-right tabular-nums">
                        {s.positions}
                        {s.open > 0 && <span className="text-xs text-muted"> ({s.open} open)</span>}
                      </td>
                      <td className="px-3 py-2 tabular-nums">
                        {s.wins}–{s.losses}–{s.pushes}
                      </td>
                      <td className="px-3 py-2 text-right tabular-nums">
                        {s.settled}
                        {s.info.group === "Wong teasers" && (
                          <span className="text-xs text-muted"> teasers</span>
                        )}
                      </td>
                      <td className="px-3 py-2 text-right tabular-nums">{signed(s.units, 1)}</td>
                      <td className="px-3 py-2 text-right tabular-nums">
                        {s.roi === null ? "–" : `${signed(100 * s.roi, 1)}%`}
                      </td>
                      <td className="px-3 py-2 text-right tabular-nums">
                        {s.meanClv === null ? "–" : signed(s.meanClv)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="text-xs text-subtle">
              Won–lost–pushed counts positions (teaser legs for Wong). Return is units per unit
              staked. CLV compares the line taken with Pinnacle&apos;s last line before kickoff, in
              points (the nflverse close where Pinnacle has none). One season is far too short to
              judge a system by its units; CLV settles faster.
            </p>
          </section>

          <section aria-labelledby="positions" className="space-y-2">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <h2 id="positions" className="text-sm font-medium uppercase tracking-wide text-muted">
                Positions{strategy && `: ${strategyInfo(strategy).label}`}
              </h2>
              {strategy && (
                <Link href={href({ strategy: null })} className="text-sm text-accent underline">
                  Show all strategies
                </Link>
              )}
            </div>
            <PositionTable title={`Open (${open.length})`} rows={open} />
            <PositionTable title={`Latest graded (${graded.length})`} rows={graded} />
            <p className="text-xs text-subtle">
              * Teaser legs carry no price of their own: two legs make one teaser at {TEASER_PRICE}.
              Live positions use Caesars where our odds feed has it and DraftKings otherwise.
            </p>
          </section>
        </>
      )}
    </div>
  );
}

function PositionTable({ title, rows }: { title: string; rows: PaperPositionRow[] }) {
  return (
    <div className="space-y-1">
      <h3 className="text-sm font-medium">{title}</h3>
      {rows.length === 0 ? (
        <p className="text-sm text-muted">None.</p>
      ) : (
        <div
          tabIndex={0}
          role="region"
          aria-label={title}
          className="relative max-h-[28rem] overflow-auto rounded-lg border border-line bg-surface"
        >
          <table className="w-full min-w-[760px] text-sm">
            <caption className="sr-only">{title}</caption>
            <thead className="sticky top-0 bg-surface">
              <tr className="text-left text-xs text-muted">
                <th scope="col" className="px-4 py-2 font-medium">
                  Kickoff
                </th>
                <th scope="col" className="px-3 py-2 font-medium">
                  Game
                </th>
                <th scope="col" className="px-3 py-2 font-medium">
                  Strategy
                </th>
                <th scope="col" className="px-3 py-2 font-medium">
                  Position
                </th>
                <th scope="col" className="px-3 py-2 text-right font-medium">
                  Price
                </th>
                <th scope="col" className="px-3 py-2 font-medium">
                  Book (quote time)
                </th>
                <th scope="col" className="px-3 py-2 font-medium">
                  Result
                </th>
                <th scope="col" className="px-3 py-2 text-right font-medium">
                  CLV
                </th>
              </tr>
            </thead>
            <tbody>
              {rows.map((p) => (
                <tr key={p.id} className="border-t border-line/60">
                  <td className="whitespace-nowrap px-4 py-1.5 text-xs text-muted">
                    {formatTimestamp(p.kickoffUtc)}
                  </td>
                  <td className="whitespace-nowrap px-3 py-1.5">
                    {p.awayTeam} <span className="text-muted">@</span> {p.homeTeam}
                  </td>
                  <td className="px-3 py-1.5 text-muted">{p.strategy}</td>
                  <td className="whitespace-nowrap px-3 py-1.5 font-mono tabular-nums">
                    {describe(p)}
                  </td>
                  <td className="px-3 py-1.5 text-right tabular-nums">
                    {p.price === null ? `${TEASER_PRICE}*` : p.price}
                  </td>
                  <td className="whitespace-nowrap px-3 py-1.5 text-xs text-muted">
                    {BOOKS[p.bookmakerKey] ?? p.bookmakerKey} ({formatTimestamp(p.quoteObservedAt)})
                  </td>
                  <td className="px-3 py-1.5">
                    {p.result ?? <span className="text-muted">open</span>}
                  </td>
                  <td className="px-3 py-1.5 text-right tabular-nums">
                    {p.clv === null ? "–" : signed(p.clv)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
