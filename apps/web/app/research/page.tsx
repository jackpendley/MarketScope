import type { Metadata } from "next";
import Link from "next/link";
import {
  MARKET_STUDIES,
  PREREGISTRATION,
  STUDIES,
  type Study,
  type StudyStatus,
} from "@/lib/research-studies";

export const metadata: Metadata = { title: "Research" };

const STATUS_STYLE: Record<StudyStatus, string> = {
  claim: "border-best/40 bg-best/10 text-best",
  "discovery claim": "border-accent/40 bg-accent/10 text-accent",
  "no claim": "border-line bg-surface-raised text-fg",
  inconclusive: "border-warn/40 bg-warn/10 text-warn",
  "waiting for data": "border-line bg-surface text-subtle",
};

function StudyCard({ s }: { s: Study }) {
  return (
    <article
      aria-labelledby={`study-${s.id}`}
      className="space-y-3 rounded-lg border border-line bg-surface px-4 py-4"
    >
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 id={`study-${s.id}`} className="font-semibold">
          <span className="text-muted">{s.id}</span> {s.title}
        </h3>
        <span className={`rounded border px-2 py-0.5 text-xs ${STATUS_STYLE[s.status]}`}>
          {s.status}
        </span>
      </div>
      <p className="text-sm">{s.question}</p>
      <p className="text-xs text-subtle">{s.window}</p>
      {s.primary && (
        <div className="rounded border border-line/60 bg-canvas/40 px-3 py-2 text-sm">
          <span className="block text-xs text-muted">Primary: {s.primary.label}</span>
          <span className="tabular-nums">
            {s.primary.estimate} <span className="text-muted">(95% CI {s.primary.interval})</span>
          </span>
        </div>
      )}
      <p className="text-sm text-fg/90">{s.finding}</p>
      {s.exploratory.length > 0 && (
        <ul className="list-disc space-y-1 pl-5 text-sm text-muted">
          {s.exploratory.map((e) => (
            <li key={e}>
              <span className="text-xs uppercase tracking-wide text-subtle">Exploratory · </span>
              {e}
            </li>
          ))}
        </ul>
      )}
      {s.report && (
        <a href={s.report} className="inline-block text-sm text-accent hover:underline">
          Full report
        </a>
      )}
    </article>
  );
}

export default function ResearchPage() {
  const counts = [...STUDIES, ...MARKET_STUDIES].reduce<Record<string, number>>(
    (acc, s) => ({ ...acc, [s.status]: (acc[s.status] ?? 0) + 1 }),
    {},
  );
  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <h1 className="text-xl font-semibold tracking-tight">Research</h1>
        <p className="max-w-3xl text-sm text-muted">
          Twelve pre-registered studies, each with one primary question: three on the betting market
          itself and nine on football. The questions, data windows, decision rules and minimum
          sample sizes were{" "}
          <a href={PREREGISTRATION} className="text-accent hover:underline">
            pre-registered
          </a>{" "}
          and committed before any study code was written. A claim needs its 95% interval to exclude
          zero in the stated direction; everything else is published as no claim. Rating studies
          stop at 2024, because 2025 is the model&apos;s one-time test season. Research results, not
          betting advice.
        </p>
        <p className="text-sm text-muted">
          {STUDIES.length + MARKET_STUDIES.length} studies: {counts["claim"] ?? 0} claim
          {(counts["claim"] ?? 0) === 1 ? "" : "s"} met, {counts["discovery claim"] ?? 0} discovery
          claims awaiting confirmation, {counts["no claim"] ?? 0} no claim,{" "}
          {counts["inconclusive"] ?? 0} inconclusive, {counts["waiting for data"] ?? 0} waiting for
          data.
        </p>
      </div>
      <section className="space-y-3" aria-labelledby="sharp-market">
        <h2 id="sharp-market" className="text-lg font-semibold tracking-tight">
          Sharp-market studies
        </h2>
        <p className="max-w-3xl text-sm text-muted">
          Which books change their numbers first, and is a number that is slow to move worth
          anything? Measured on minute-level line moves, including the market makers Pinnacle, Circa
          and Bookmaker.eu, and scored by closing-line value against Pinnacle. Rules were{" "}
          <a href={PREREGISTRATION} className="text-accent underline">
            pre-registered
          </a>{" "}
          (Addenda C and D). These are <strong className="text-fg">discovery</strong> results from
          weeks 1–6; the same code re-runs on weeks 7–14, and a result counts only if it holds there
          too. Timing describes which book changed first, not who placed wagers. Analysis, not
          betting advice.
        </p>
        <div className="grid gap-4 lg:grid-cols-2">
          {MARKET_STUDIES.map((s) => (
            <StudyCard key={s.id} s={s} />
          ))}
        </div>
      </section>
      <section className="space-y-3" aria-labelledby="football">
        <h2 id="football" className="text-lg font-semibold tracking-tight">
          Football studies
        </h2>
        <div className="grid gap-4 lg:grid-cols-2">
          {STUDIES.map((s) => (
            <StudyCard key={s.id} s={s} />
          ))}
        </div>
      </section>
      <p className="max-w-3xl text-sm text-muted">
        What the football studies say together: the closing line already prices what MarketScope
        Ratings measure, including injuries by kickoff (R2h), though the consensus is still moving
        on injury news during the week (R2w). Disagreements between the ratings and the close do not
        predict results (R4), and blending the model into the market makes the forecast worse (R6).
        That is why the{" "}
        <Link href="/model" className="text-accent hover:underline">
          model scorecard
        </Link>{" "}
        compares the model with the close instead of treating differences as opportunities.
      </p>
    </div>
  );
}
