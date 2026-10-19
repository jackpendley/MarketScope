// The market-movement ML experiments (MS-024/025 and MS-036), summarised from the committed
// reports research/reports/market-baseline-v1.md and market-football-v1.md (and MODEL_CARD.md).
// Static on purpose, like lib/research-studies.ts: re-running an experiment means updating this file.

import { REPO } from "./research-studies";

export type Verdict = "better" | "not distinguishable" | "worse" | "pending";

export type Experiment = {
  id: string;
  title: string;
  question: string;
  comparison: string;
  verdict: Verdict;
  /** Paired differences (model minus reference; negative = better) with 95% intervals. */
  dBrier: { estimate: string; interval: string } | null;
  dLogLoss: { estimate: string; interval: string } | null;
  auc: { estimate: string; interval: string } | null;
  note: string;
  report: string;
};

export const SETUP = {
  target:
    "Will the betting consensus (median of the board books) move at least 0.5 points in the next 24 hours?",
  data: "2026 season odds snapshots: weeks 1–3 to train, week 4 to tune, week 5 to test once (15 games, 348 snapshots). Live weeks from 6 on are a forward check.",
  rule: "A model counts as better only when the 95% intervals of both its Brier score and log-loss differences lie below zero. Intervals resample games, because snapshots of one game are correlated.",
  leakage:
    "Every feature uses only data available at the snapshot time. A test perturbs everything after that time and checks that no feature changes.",
};

export const EXPERIMENTS: Experiment[] = [
  {
    id: "MS-025a",
    title: "Will it move? Market features only",
    question:
      "Can line-movement features (recent moves, disagreement between books, quote age, key numbers) predict a 0.5-point move within 24 hours?",
    comparison: "Logistic regression vs the constant base rate",
    verdict: "not distinguishable",
    dBrier: { estimate: "−0.0205", interval: "−0.0509 to +0.0040" },
    dLogLoss: { estimate: "−0.062", interval: "−0.148 to +0.009" },
    auc: { estimate: "0.72", interval: "0.57 to 0.86" },
    note: "It ranks snapshots well (AUC 0.72), but on one 15-game test week the calibrated gain is not distinguishable from zero.",
    report: `${REPO}/research/reports/market-baseline-v1.md`,
  },
  {
    id: "MS-025b",
    title: "Which way? Market features only",
    question: "Given that the consensus moves, can the same features say toward which team?",
    comparison: "Logistic regression vs the constant base rate",
    verdict: "not distinguishable",
    dBrier: { estimate: "−0.0144", interval: "−0.0410 to +0.0076" },
    dLogLoss: { estimate: "−0.030", interval: "−0.084 to +0.015" },
    auc: { estimate: "0.54", interval: "0.32 to 0.71" },
    note: "No skill: an AUC of 0.54 is close to a coin flip.",
    report: `${REPO}/research/reports/market-baseline-v1.md`,
  },
  {
    id: "MS-036a",
    title: "Will it move? Adding football features",
    question:
      "Do point-in-time football features (rating gap, in-game injuries, forecast wind, rest and travel) improve the market-only model?",
    comparison: "Market + football features vs market features only",
    verdict: "not distinguishable",
    dBrier: { estimate: "+0.0011", interval: "−0.0015 to +0.0039" },
    dLogLoss: { estimate: "+0.002", interval: "−0.007 to +0.011" },
    auc: null,
    note: "No lift. The injury features alone came closest (Δ Brier −0.0025, −0.0052 to 0.0000): exploratory.",
    report: `${REPO}/research/reports/market-football-v1.md`,
  },
  {
    id: "MS-036b",
    title: "Which way? Adding football features",
    question:
      "Does the gap between MarketScope Ratings and the consensus, or injuries, say which way the line moves?",
    comparison: "Market + football features vs market features only",
    verdict: "worse",
    dBrier: { estimate: "+0.0373", interval: "+0.0045 to +0.0776" },
    dLogLoss: { estimate: "+0.081", interval: "+0.010 to +0.172" },
    auc: null,
    note: "Worse: with 152 training rows from 32 games, the extra signed features fit noise.",
    report: `${REPO}/research/reports/market-football-v1.md`,
  },
];

/** What the market-only "will it move" model leans on (standardized coefficients, final fit). */
export const DRIVERS: { feature: string; meaning: string; coefficient: string }[] = [
  {
    feature: "abs_move_24h",
    meaning: "How far the consensus moved in the last 24 hours",
    coefficient: "+0.16",
  },
  { feature: "range", meaning: "Spread between the highest and lowest book", coefficient: "+0.15" },
  {
    feature: "mean_abs_dev",
    meaning: "Average disagreement between books and the consensus",
    coefficient: "+0.14",
  },
  {
    feature: "totals_abs_move_24h",
    meaning: "How far the totals consensus moved in 24 hours",
    coefficient: "+0.12",
  },
  {
    feature: "half_point",
    meaning: "The consensus sits on a half point (e.g. −3.5)",
    coefficient: "−0.11",
  },
  {
    feature: "median_quote_age_h",
    meaning: "How stale the books' quotes are",
    coefficient: "−0.09",
  },
];

export const FORWARD_CHECK =
  "Pending: 13 live games labelled, 15 needed. The models are then scored on live data they never saw.";
export const MODEL_CARD = `${REPO}/docs/MODEL_CARD.md`;
