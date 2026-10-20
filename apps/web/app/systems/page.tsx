import type { Metadata } from "next";
import { EquityChart } from "@/components/equity-chart";
import {
  PREREGISTRATION,
  PRICES,
  REPORT,
  VARIANT_KEYS,
  WONG,
  Y2026_SOURCES,
  equityRows,
  pct,
  signedPct,
  signedUnits,
  versusBreakEven,
  y2026,
} from "@/lib/systems-view";

export const metadata: Metadata = { title: "Systems" };

const COLORS = { V0: "#3987e5", V1: "#2fb3a6", V2: "#c98500" } as const;

export default function SystemsPage() {
  const { primary, primaryPrice, breakEven, variants } = WONG;
  const be = breakEven[String(primaryPrice) as keyof typeof breakEven];
  const where = versusBreakEven(primary.low, primary.high, be);
  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <h1 className="text-xl font-semibold tracking-tight">Systems</h1>
        <p className="max-w-3xl text-sm text-muted">
          Backtests of published market systems on closing lines, with the rules{" "}
          <a href={PREREGISTRATION} className="text-accent underline">
            pre-registered
          </a>{" "}
          (Addendum E) before any result was computed. Every number on this page is{" "}
          <strong className="text-fg">hypothetical</strong>: what the rule would have returned at
          the closing line and a fixed price, not a record of real wagers. Analysis, not betting
          advice.
        </p>
      </div>

      <section aria-labelledby="wong" className="space-y-4">
        <div className="space-y-1">
          <h2 id="wong" className="text-lg font-semibold tracking-tight">
            Wong teasers (2016–25)
          </h2>
          <p className="max-w-3xl text-sm text-muted">
            A six-point, two-team teaser using teams that close at −7.5 to −8.5 (teased to −1.5 to
            −2.5) or +1.5 to +2.5 (teased to +7.5 to +8.5), so each leg crosses both 3 and 7, the
            most common NFL margins. A two-team teaser at {primaryPrice} needs each leg to win{" "}
            {pct(be)} of the time to break even.
          </p>
        </div>

        <div className="rounded-lg border border-line bg-surface px-4 py-3">
          <p className="text-xs text-muted">
            Primary: leg win rate, every Wong leg, 2016–25 (pushes count as losses)
          </p>
          <p className="text-lg tabular-nums">
            {pct(primary.rate)}{" "}
            <span className="text-sm text-muted">
              (95% CI {pct(primary.low)}–{pct(primary.high)}, {primary.legs} legs)
            </span>
          </p>
          <p className="text-sm">
            {where === "above"
              ? `Above the ${primaryPrice} break-even of ${pct(be)}.`
              : where === "below"
                ? `Below the ${primaryPrice} break-even of ${pct(be)}.`
                : `The interval includes the ${primaryPrice} break-even of ${pct(be)}, so the result is no claim: over ten seasons the legs won slightly more often than the price requires, but not by a margin distinguishable from luck.`}
          </p>
        </div>

        <div className="relative overflow-x-auto rounded-lg border border-line bg-surface">
          <table className="w-full min-w-[640px] text-sm">
            <caption className="sr-only">Leg win rate and hypothetical return by variant</caption>
            <thead>
              <tr className="text-left text-xs text-muted">
                <th scope="col" className="px-4 py-2 font-medium">
                  Variant
                </th>
                <th scope="col" className="px-3 py-2 text-right font-medium">
                  Legs
                </th>
                <th scope="col" className="px-3 py-2 font-medium">
                  Leg win rate (95% CI)
                </th>
                {PRICES.map((p) => (
                  <th key={p} scope="col" className="px-3 py-2 text-right font-medium">
                    Return at {p}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {VARIANT_KEYS.map((k) => {
                const v = variants[k];
                return (
                  <tr key={k} className="border-t border-line/60">
                    <th scope="row" className="px-4 py-2 text-left font-normal">
                      <span className="text-muted">{k}</span> {v.label}
                    </th>
                    <td className="px-3 py-2 text-right tabular-nums">{v.legs}</td>
                    <td className="whitespace-nowrap px-3 py-2 tabular-nums">
                      {pct(v.value)}{" "}
                      <span className="text-xs text-muted">
                        ({pct(v.low)}–{pct(v.high)})
                      </span>
                    </td>
                    {PRICES.map((p) => (
                      <td key={p} className="px-3 py-2 text-right tabular-nums">
                        {signedPct(v.roi[String(p) as keyof typeof v.roi])}
                      </td>
                    ))}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <p className="max-w-3xl text-xs text-subtle">
          Return per unit staked, teasers paired in date order within each week, a push losing the
          teaser. Break-even leg win rates:{" "}
          {PRICES.map((p) => `${p} ${pct(breakEven[String(p) as keyof typeof breakEven])}`).join(
            " · ",
          )}
          . V1 and V2 are secondary; V2&apos;s rate fell from 2016–23 to 2024–25. The full report
          has intervals for every return, season tables and favourites versus underdogs.
        </p>

        <EquityChart
          series={(["V0", "V1"] as const).map((k) => ({
            key: k,
            label: `${k} ${variants[k].label}`,
            color: COLORS[k],
            rows: equityRows(k),
          }))}
          summary={(["V0", "V1"] as const)
            .map((k) => {
              const rows = equityRows(k);
              return `${k}: ${rows.length} teasers, ending at ${signedUnits(rows.at(-1)?.units ?? 0)} units at ${primaryPrice}`;
            })
            .join("; ")}
        />
      </section>

      <section aria-labelledby="y2026" className="space-y-3">
        <h2 id="y2026" className="text-lg font-semibold tracking-tight">
          2026 so far (hypothetical)
        </h2>
        <p className="max-w-3xl text-sm text-muted">
          The same rules on this season&apos;s finished games at {primaryPrice}, once with the
          nflverse closing line and once with Caesars&apos; own last line before kickoff. About 30
          legs: far too few to say anything about the system, shown because the question is a fair
          one to ask.
        </p>
        <div className="relative overflow-x-auto rounded-lg border border-line bg-surface">
          <table className="w-full min-w-[560px] text-sm">
            <caption className="sr-only">
              2026 hypothetical record by line source and variant
            </caption>
            <thead>
              <tr className="text-left text-xs text-muted">
                <th scope="col" className="px-4 py-2 font-medium">
                  Line
                </th>
                <th scope="col" className="px-3 py-2 font-medium">
                  Variant
                </th>
                <th scope="col" className="px-3 py-2 text-right font-medium">
                  Legs
                </th>
                <th scope="col" className="px-3 py-2 font-medium">
                  Won–lost–pushed
                </th>
                <th scope="col" className="px-3 py-2 text-right font-medium">
                  Teasers
                </th>
                <th scope="col" className="px-3 py-2 text-right font-medium">
                  Units
                </th>
              </tr>
            </thead>
            <tbody>
              {Y2026_SOURCES.flatMap((src) =>
                VARIANT_KEYS.map((k) => {
                  const r = y2026(src, k);
                  return (
                    <tr key={`${src}-${k}`} className="border-t border-line/60">
                      <td className="px-4 py-2">{src}</td>
                      <td className="px-3 py-2">{k}</td>
                      <td className="px-3 py-2 text-right tabular-nums">{r.legs}</td>
                      <td className="px-3 py-2 tabular-nums">{r.record}</td>
                      <td className="px-3 py-2 text-right tabular-nums">{r.teasers}</td>
                      <td className="px-3 py-2 text-right tabular-nums">{signedUnits(r.units)}</td>
                    </tr>
                  );
                }),
              )}
            </tbody>
          </table>
        </div>
      </section>

      <p className="max-w-3xl text-xs text-subtle">
        Not visible here: prices before the close, each book&apos;s own teaser rules, and limits.
        Generated {WONG.generated} from commit {WONG.commit}.{" "}
        <a href={REPORT} className="text-accent underline">
          Full report
        </a>
        .
      </p>
    </div>
  );
}
