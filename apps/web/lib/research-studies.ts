// The pre-registered football studies (MS-035, ADR-043), summarised from the committed reports in
// research/reports/. Static on purpose: each number is copied from a generated report, and the
// study code, not this page, is the source of truth. Re-running a study means updating this file.

export const REPO = "https://github.com/jackpendley/MarketScope/blob/main";
export const PREREGISTRATION = `${REPO}/research/PREREGISTRATION.md`;

export type StudyStatus = "claim" | "no claim" | "inconclusive" | "waiting for data";

export type Study = {
  id: string;
  title: string;
  question: string;
  window: string;
  status: StudyStatus;
  /** The primary estimate with its 95% interval, as reported. Null until the study has run. */
  primary: { label: string; estimate: string; interval: string } | null;
  finding: string;
  /** Exploratory results: labelled as such on the page. */
  exploratory: string[];
  report: string | null;
};

export const STUDIES: Study[] = [
  {
    id: "R1",
    title: "Market accuracy over time",
    question: "Is the market consensus more accurate at kickoff than six days out?",
    window: "2026 regular season, 77 games",
    status: "no claim",
    primary: {
      label: "Error 6 days out minus error at the close (points)",
      estimate: "+0.03",
      interval: "−0.26 to +0.28",
    },
    finding:
      "The consensus six days before kickoff was as accurate as the closing consensus on these games. No sportsbook's closing line was more accurate than the consensus.",
    exploratory: [],
    report: `${REPO}/research/reports/football-studies-v1.md`,
  },
  {
    id: "R2",
    title: "Injury news",
    question:
      "How far does the consensus move after a starter is newly listed Out, and is a QB different?",
    window: "2026 live injury snapshots",
    status: "waiting for data",
    primary: null,
    finding:
      "Needs at least 30 qualifying injury events from the daily injury snapshots, which began on 2026-10-18. R2h and R2w answer the question with historical data in the meantime.",
    exploratory: [],
    report: null,
  },
  {
    id: "R2h",
    title: "Are injuries priced? (history)",
    question:
      "Does the injury part of the model's estimate, from final injury reports, predict results against the closing line?",
    window: "2016–24 regular seasons, 2,367 games",
    status: "no claim",
    primary: {
      label: "Result vs the close, per point of the model's injury adjustment",
      estimate: "+0.11",
      interval: "−0.27 to +0.50",
    },
    finding:
      "Not distinguishable from zero: by kickoff the closing line already carries what the final injury report says, as valued by the model.",
    exploratory: [
      "Neither the QB part (−0.16) nor the non-QB part (+0.41) is distinguishable from zero on its own.",
    ],
    report: `${REPO}/research/reports/r2h-injuries-priced.md`,
  },
  {
    id: "R2w",
    title: "Injury news during the week",
    question:
      "Does the consensus move between six days out and kickoff when a starter who played last week is ruled Out?",
    window: "2026 weeks 1–6, 77 games, 80 events",
    status: "claim",
    primary: {
      label: "Line move toward the opponent, per newly-out starter (points)",
      estimate: "+0.40",
      interval: "+0.14 to +0.73",
    },
    finding:
      "Yes: the consensus moved about 0.4 points toward the opponent for each starter newly ruled Out. With R2h, the picture is that the market absorbs absences during the week and has priced them by kickoff.",
    exploratory: [
      "Counting non-QB starters only, a check added after seeing the result: +0.30 (+0.12 to +0.51).",
      "Only 5 QB events, short of the 10 a QB claim needs.",
    ],
    report: `${REPO}/research/reports/r2w-injury-moves.md`,
  },
  {
    id: "R3",
    title: "Wind and totals",
    question: "Is forecast wind under- or over-priced in closing totals?",
    window: "2024–26, 534 outdoor games",
    status: "inconclusive",
    primary: {
      label: "Actual minus closing total, per mph of forecast wind",
      estimate: "−0.08",
      interval: "−0.38 to +0.20",
    },
    finding:
      "The gate needs 30 games with forecast wind of at least 15 mph; there are 29. The study is re-run once the gate is met.",
    exploratory: [
      "The market lowers closing totals by about 0.19 points per mph of forecast wind.",
    ],
    report: `${REPO}/research/reports/football-studies-v1.md`,
  },
  {
    id: "R4",
    title: "Is performance priced?",
    question:
      "When MarketScope Ratings disagree with the closing line, does the result lean toward the ratings?",
    window: "2016–24 regular seasons",
    status: "no claim",
    primary: {
      label: "Result vs the close, per point of rating gap",
      estimate: "+0.12",
      interval: "−0.05 to +0.29",
    },
    finding:
      "Not distinguishable from zero, and negative (−0.11) on 2023–24, the seasons the ratings were not fitted on. The closing line already prices what the ratings measure.",
    exploratory: [
      "In 2026 the consensus moved toward the ratings between six days out and kickoff (+0.10 per point of gap, 0.03 to 0.18). This may reflect shared news rather than the ratings leading the market.",
    ],
    report: `${REPO}/research/reports/football-studies-v1.md`,
  },
  {
    id: "R5",
    title: "Luck",
    question: "Does the market overrate teams that have won more than their play deserved?",
    window: "2016–24, from week 5",
    status: "no claim",
    primary: {
      label: "Result vs the close, per win of luck difference",
      estimate: "−0.02",
      interval: "−0.50 to +0.47",
    },
    finding: "No sign that the closing line overrates lucky teams.",
    exploratory: [
      "Luck does not persist: luck through week 9 does not predict luck over the rest of the season.",
    ],
    report: `${REPO}/research/reports/football-studies-v1.md`,
  },
  {
    id: "R6",
    title: "Model + market blend",
    question:
      "Does blending the model's win probability with the closing market beat the market alone?",
    window: "2023–24, 570 games (walk-forward)",
    status: "no claim",
    primary: {
      label: "Blend Brier minus close Brier",
      estimate: "+0.0026",
      interval: "+0.0006 to +0.0047",
    },
    finding:
      "The blend was slightly less accurate than the close, so the published nfelo result does not replicate for this model. The weight rule, fitted each week on the previous four, mostly chose a weight of 0, meaning the market alone.",
    exploratory: [
      "A fixed 35% model weight (nfelo's setting) was also worse than the close: +0.0027 (+0.0005 to +0.0047).",
    ],
    report: `${REPO}/research/reports/r6-model-market-blend.md`,
  },
  {
    id: "R7",
    title: "Play-caller continuity",
    question:
      "Does an offense keep more of its level into next season when its play-caller stays, holding the QB fixed?",
    window: "2016–24, 256 team-season pairs",
    status: "no claim",
    primary: {
      label: "Extra carryover with the same play-caller",
      estimate: "+0.02",
      interval: "−0.23 to +0.25",
    },
    finding:
      "Once QB continuity is accounted for, keeping the play-caller adds no measurable carryover. Keeping the main QB does (+0.33, 0.04 to 0.60). Re-run after the MS-035c coaching corrections: unchanged.",
    exploratory: [
      "Defense: no continuity effect for the defensive play-caller (+0.01, −0.24 to +0.27).",
      "Scheme: across 20 play-callers who moved teams, neither pass rate over expected nor pace clearly followed them.",
    ],
    report: `${REPO}/research/reports/r7-play-caller.md`,
  },
];
