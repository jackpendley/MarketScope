import type { Metadata } from "next";
import Link from "next/link";
import {
  DRIVERS,
  EXPERIMENTS,
  FORWARD_CHECK,
  MODEL_CARD,
  SETUP,
  type Experiment,
  type Verdict,
} from "@/lib/ml-lab";

export const metadata: Metadata = { title: "ML Lab" };

const VERDICT_STYLE: Record<Verdict, string> = {
  better: "border-best/40 bg-best/10 text-best",
  "not distinguishable": "border-line bg-surface-raised text-fg",
  worse: "border-danger/40 bg-danger/10 text-fg",
  pending: "border-line bg-surface text-subtle",
};

function Metric({ label, m }: { label: string; m: Experiment["dBrier"] }) {
  if (!m) return null;
  return (
    <div>
      <dt className="text-xs text-muted">{label}</dt>
      <dd className="tabular-nums">
        {m.estimate} <span className="text-xs text-muted">({m.interval})</span>
      </dd>
    </div>
  );
}

function ExperimentCard({ e }: { e: Experiment }) {
  return (
    <article
      aria-labelledby={`exp-${e.id}`}
      className="space-y-3 rounded-lg border border-line bg-surface px-4 py-4"
    >
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 id={`exp-${e.id}`} className="font-semibold">
          <span className="text-muted">{e.id}</span> {e.title}
        </h2>
        <span className={`rounded border px-2 py-0.5 text-xs ${VERDICT_STYLE[e.verdict]}`}>
          {e.verdict}
        </span>
      </div>
      <p className="text-sm">{e.question}</p>
      <p className="text-xs text-subtle">{e.comparison}</p>
      <dl className="grid grid-cols-1 gap-2 rounded border border-line/60 bg-canvas/40 px-3 py-2 text-sm sm:grid-cols-3">
        <Metric label="Δ Brier" m={e.dBrier} />
        <Metric label="Δ log loss" m={e.dLogLoss} />
        <Metric label="AUC" m={e.auc} />
      </dl>
      <p className="text-sm text-fg/90">{e.note}</p>
      <a href={e.report} className="inline-block text-sm text-accent hover:underline">
        Full report
      </a>
    </article>
  );
}

export default function MlLabPage() {
  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <h1 className="text-xl font-semibold tracking-tight">ML Lab</h1>
        <p className="max-w-3xl text-sm text-muted">
          Can a model tell when the NFL betting consensus is about to move? These experiments use
          MarketScope&apos;s own odds history. Each design was pre-registered before any model was
          fitted, and the results are published whether or not they help. They describe market
          behaviour; predicting a line move is not evidence of profit after the bookmaker&apos;s
          margin. Not betting advice.
        </p>
      </div>

      <section aria-labelledby="setup" className="space-y-2">
        <h2 id="setup" className="text-sm font-medium uppercase tracking-wide text-muted">
          Setup
        </h2>
        <dl className="grid gap-3 rounded-lg border border-line bg-surface px-4 py-3 text-sm md:grid-cols-2">
          {(
            [
              ["Target", SETUP.target],
              ["Data and split", SETUP.data],
              ["What counts as better", SETUP.rule],
              ["No peeking", SETUP.leakage],
            ] as const
          ).map(([k, v]) => (
            <div key={k}>
              <dt className="text-xs text-muted">{k}</dt>
              <dd>{v}</dd>
            </div>
          ))}
        </dl>
      </section>

      <section className="grid gap-4 lg:grid-cols-2" aria-label="Experiments">
        {EXPERIMENTS.map((e) => (
          <ExperimentCard key={e.id} e={e} />
        ))}
      </section>
      <p className="text-xs text-subtle">
        Δ = model minus reference on the test week, paired by game; negative is better. Brier and
        log loss score the probabilities; AUC (0.5 = coin flip) scores the ranking only.
      </p>

      <section aria-labelledby="drivers" className="space-y-2">
        <h2 id="drivers" className="text-sm font-medium uppercase tracking-wide text-muted">
          What the market-only model leans on
        </h2>
        <div className="overflow-x-auto rounded-lg border border-line bg-surface">
          <table className="w-full min-w-[32rem] text-sm" aria-label="Largest model coefficients">
            <thead className="text-xs text-muted">
              <tr>
                <th scope="col" className="px-4 py-2 text-left font-medium">
                  Feature
                </th>
                <th scope="col" className="px-4 py-2 text-left font-medium">
                  Meaning
                </th>
                <th scope="col" className="px-4 py-2 text-right font-medium">
                  Coefficient
                </th>
              </tr>
            </thead>
            <tbody>
              {DRIVERS.map((d) => (
                <tr key={d.feature} className="border-t border-line/60">
                  <td className="px-4 py-1.5 font-mono text-xs">{d.feature}</td>
                  <td className="px-4 py-1.5">{d.meaning}</td>
                  <td className="px-4 py-1.5 text-right tabular-nums">{d.coefficient}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="text-xs text-subtle">
          Standardized logistic-regression coefficients: positive means a move is more likely. Moves
          cluster: a line that just moved, or that books disagree on, tends to keep moving.
        </p>
      </section>

      <section aria-labelledby="forward" className="space-y-2">
        <h2 id="forward" className="text-sm font-medium uppercase tracking-wide text-muted">
          Forward check
        </h2>
        <p className="text-sm">{FORWARD_CHECK}</p>
      </section>

      <p className="max-w-3xl text-sm text-muted">
        Taken with the{" "}
        <Link href="/research" className="text-accent hover:underline">
          research studies
        </Link>
        , the picture is consistent: with one season of odds history, football information adds
        nothing detectable to what the market itself shows. Details are in the{" "}
        <a href={MODEL_CARD} className="text-accent hover:underline">
          model card
        </a>
        .
      </p>
    </div>
  );
}
