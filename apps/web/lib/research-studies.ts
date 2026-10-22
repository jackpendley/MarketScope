// The pre-registered football studies (MS-035, ADR-043), summarised from the committed reports in
// research/reports/. The study code, not this page, is the source of truth. Cards whose runners record
// results (ADR-072) read their numbers from generated/study-results.json; the rest are still copied
// from the committed reports by hand.

import results from "./generated/study-results.json";

export const REPO = "https://github.com/jackpendley/MarketScope/blob/main";
export const PREREGISTRATION = `${REPO}/research/PREREGISTRATION.md`;

/** "discovery claim": met on the discovery sample, not yet confirmed on the held-out weeks. */
export type StudyStatus =
  "claim" | "discovery claim" | "no claim" | "inconclusive" | "waiting for data";

export type Study = {
  id: string;
  title: string;
  question: string;
  window: string;
  status: StudyStatus;
  /** The primary estimate with its 95% interval, as reported. Null until the study has run. */
  primary: { label: string; estimate: string; interval: string; threshold?: number } | null;
  finding: string;
  /** Exploratory results: labelled as such on the page. */
  exploratory: string[];
  report: string | null;
};

type GeneratedResult = {
  value: number;
  low: number;
  high: number;
  digits: number;
  positions: number | null;
  games: number | null;
  weeks: number | null;
  commit: string;
  dirty: boolean;
  dataset: string | null;
  report: string | null;
};

/** Results written by the research runners (`research/.../results.py`, ADR-072). */
export const GENERATED_RESULTS = results as Record<string, GeneratedResult>;

const signed = (x: number, digits: number) =>
  `${x < 0 ? "−" : "+"}${Math.abs(x).toFixed(digits)}`;

/** A card's primary estimate and interval, taken from the runner's output instead of copied by hand. */
export function generatedPrimary(id: string, label: string): NonNullable<Study["primary"]> {
  const r = GENERATED_RESULTS[id];
  if (!r) throw new Error(`No generated result for study ${id}`);
  return {
    label,
    estimate: signed(r.value, r.digits),
    interval: `${signed(r.low, r.digits)} to ${signed(r.high, r.digits)}`,
  };
}

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

// The sharp-market studies (MS-043, PREREGISTRATION.md Addenda C and D), from
// research/reports/sharp-market-discovery.md. Discovery = 2026 weeks 1–6; the same code re-runs on
// weeks 7–14 before any result counts as established.
export const MARKET_STUDIES: Study[] = [
  {
    id: "S1",
    title: "Who moves first?",
    question:
      "When Pinnacle and a US retail book make the same spread change within an hour, which one changes first?",
    window: "2026 weeks 1–6, 91 games, 216 matched Pinnacle–retail changes",
    status: "discovery claim",
    primary: {
      label: "Share of matched changes where Pinnacle moved first (claim if above 0.5)",
      estimate: "0.741",
      interval: "0.680 to 0.798",
      threshold: 0.5,
    },
    finding:
      "Pinnacle changed its number first about three times in four. Circa led about as often (0.735). Retail books seldom followed quickly: 4–15% of Pinnacle's changes were matched within an hour, and 43–83% never before kickoff.",
    exploratory: [
      "Pinnacle led more often more than 48 hours before kickoff (83%) than in the final 6 hours (63%).",
      "Bookmaker.eu led retail in 0.637 of its matched changes (0.525 to 0.744).",
    ],
    report: `${REPO}/research/reports/sharp-market-discovery.md`,
  },
  {
    id: "S2",
    title: "Stale retail numbers",
    question:
      "A minute after Pinnacle moves, a retail book still shows the old number on the side Pinnacle moved toward. Does taking it beat Pinnacle's close?",
    window: "2026 weeks 1–6, 1,450 cases in 89 games",
    status: "discovery claim",
    primary: {
      label: "Mean closing-line value (points)",
      estimate: "+0.44",
      interval: "+0.36 to +0.52",
    },
    finding:
      "Yes, in points, but mostly by construction: the old number starts half a point ahead of Pinnacle's new one (+0.54), and Pinnacle then gives back a little of its move (−0.10). Points ignore what the retail book charged for the old number, so whether it was worth taking depends on price.",
    exploratory: [
      "Hypothetical cover rate 53.7% against a 52.9% break-even at the posted prices: not distinguishable from break-even over one season.",
      "Counting the price (MS-046): −2.0% per unit against Pinnacle's no-vig close (−2.7% to −1.3%). The books keep the old number but charge for it, so the points overstate it.",
      "At standard prices (−110 or better): −0.6% (−1.5% to +0.3%), close to break-even. Found after the fact, so it is pre-registered (Addenda D and H) for the held-out weeks.",
      "Totals, same rule: +0.55 points (+0.43 to +0.68).",
    ],
    report: `${REPO}/research/reports/sharp-market-discovery.md`,
  },
  {
    id: "S3",
    title: "Steam",
    question:
      "When three of seven books move the spread the same way within ten minutes, does Pinnacle keep moving that way until kickoff?",
    window: "2026 weeks 1–6, 120 episodes",
    status: "discovery claim",
    primary: {
      label: "Pinnacle's further move to the close, in the steam direction (points)",
      estimate: "+0.17",
      interval: "+0.01 to +0.34",
    },
    finding:
      "A little, and only just: the interval barely clears zero. A reference book was among the first three movers in 92% of episodes.",
    exploratory: [
      "Retail books that had not yet moved were +0.82 points (+0.56 to +1.07) better than Pinnacle's close, at −125 or better.",
      "Totals: +0.24 points (+0.12 to +0.37).",
      "Limits and key numbers (S4, S5): Pinnacle changes at higher limits reversed more often (45% vs 37%); key-number changes reversed less (33% vs 41%). Descriptive only.",
    ],
    report: `${REPO}/research/reports/sharp-market-discovery.md`,
  },
  {
    id: "M1",
    title: "Machine learning: Pinnacle's next move",
    question:
      "From the market's state 48, 24, 6 or 1 hours before kickoff, can a model predict which way Pinnacle's line goes by the close?",
    window:
      "2026 weeks 3–6, walk-forward (each week predicted from earlier weeks), 244 game-horizons",
    status: "no claim",
    primary: {
      label: "Log loss, model minus class-frequency baseline (negative = better)",
      estimate: "+0.417",
      interval: "+0.153 to +0.697",
    },
    finding:
      "No. The model did worse than simply predicting how often lines move at each horizon: with a few dozen games per week it fitted noise. Pinnacle's own direction looks unpredictable from this data, which is what an efficient sharp market would show.",
    exploratory: [
      "Pinnacle's line did not change at all from the decision time to the close in 52% of cases.",
    ],
    report: `${REPO}/research/reports/market-ml-discovery.md`,
  },
  {
    id: "M2",
    title: "Machine learning: retail numbers worth taking",
    question:
      "Can a model find retail numbers whose price beats Pinnacle's no-vig close, once the value of each half-point (3 and 7 above all) is counted?",
    window: "2026 weeks 3–6, walk-forward, 1,892 book-side-horizons",
    status: "no claim",
    primary: {
      label: "Mean value per unit of the model's selections (Pinnacle's no-vig close)",
      estimate: "+0.000",
      interval: "−0.019 to +0.020",
    },
    finding:
      "The model found numbers worth about break-even, not more. Every retail number averaged −4.6% (the books' margin); a simple rule, a better number than Pinnacle's at −125 or better, averaged −2.0%. Selecting by model closed that gap but did not open a positive one.",
    exploratory: ["Value rose with the number's head start over Pinnacle and with a better price."],
    report: `${REPO}/research/reports/market-ml-discovery.md`,
  },
  {
    id: "I1",
    title: "Injury news: the official report",
    question:
      "When teams file game-status designations (by 4 pm ET, two days before most games), does Pinnacle move on starters newly ruled Out?",
    window: "2026 weeks 2–6, 76 games, 95 newly-out starters",
    status: "no claim",
    primary: {
      label: "Pinnacle's move inside the report window per net newly-out starter (points)",
      estimate: "+0.02",
      interval: "−0.00 to +0.05",
    },
    finding:
      "Barely. By the time the designation is filed, the market has already moved: about two-thirds of the injury-driven move happens by four days before kickoff, around the midweek practice reports, and the filing window itself holds almost none of it.",
    exploratory: [
      "The move toward the healthier side reached +0.24 points four days out and +0.36 at the close (29 games with net news; noisy).",
    ],
    report: `${REPO}/research/reports/injury-windows-discovery.md`,
  },
  {
    id: "I2",
    title: "Injury news: slow retail books?",
    question:
      "When Pinnacle moves on injury news inside the report window, are the retail numbers left behind worth taking at their price?",
    window: "2026 weeks 2–6, 18 cases (gate: 50)",
    status: "inconclusive",
    primary: {
      label: "Mean price-aware value per unit of the lagging numbers",
      estimate: "−0.003",
      interval: "−0.029 to +0.025",
    },
    finding:
      "Too few cases to say: because Pinnacle rarely moves in the report window, only 18 qualified. The confirmation weeks add more.",
    exploratory: [
      "Those 18 numbers stayed up for a median of about 32 hours, against about 5 hours for other stale numbers.",
    ],
    report: `${REPO}/research/reports/injury-windows-discovery.md`,
  },
  {
    id: "O1",
    title: "Retail openers",
    question:
      "When a retail book first posts a game at a better number than Pinnacle's at that moment, is it worth taking at its price?",
    window: "2026 weeks 1–6, 21 openers (books mostly open at Pinnacle's number)",
    status: "no claim",
    primary: {
      label: "Mean value per unit against Pinnacle's no-vig close",
      estimate: "−0.023",
      interval: "−0.063 to +0.018",
    },
    finding:
      "No. Retail books rarely open off Pinnacle's number, and the few that did were not worth taking at their price.",
    exploratory: [
      "Openers more than a week before kickoff: −5.7% (8 cases); 2–7 days out: −0.2% (13 cases).",
    ],
    report: `${REPO}/research/reports/openers-totals-discovery.md`,
  },
  {
    id: "T1",
    title: "Stale totals",
    question:
      "A minute after Pinnacle moves a total, a retail book still shows the old one. Is it worth taking at its price?",
    window: "2026 weeks 1–6, 1,286 cases",
    status: "no claim",
    primary: {
      label: "Mean value per unit against Pinnacle's no-vig close",
      estimate: "−0.018",
      interval: "−0.025 to −0.011",
    },
    finding:
      "No, and the interval is below zero. In points the old total looks half a point better (+0.55), but the books charge for it, exactly as with spreads.",
    exploratory: [
      "At −110 or better: −1.0% (−1.8% to −0.1%). Retail totals better than Pinnacle's at fixed times before kickoff: −3.0%.",
    ],
    report: `${REPO}/research/reports/openers-totals-discovery.md`,
  },
  {
    id: "X1",
    title: "Stale exchange prices",
    question:
      "On Novig, ProphetX and Kalshi, where other traders set the price and margins are thin, is an old line left up after Pinnacle moves worth taking after fees?",
    window: "2026 weeks 1–6, 1,715 cases with at least 100 available",
    status: "no claim",
    primary: {
      label: "Mean value per unit after fees (Pinnacle's no-vig close)",
      estimate: "−0.012",
      interval: "−0.016 to −0.008",
    },
    finding:
      "No, and the interval is below zero: exchange traders also price the lag in, and fees take the rest. Novig, which charges no fee, came closest at +0.4% (−0.2% to +0.9%), but only on thin quotes; with at least 1,000 available it was −0.1%. Its own test is pre-registered for the held-out weeks.",
    exploratory: [
      "Kalshi −2.6%, ProphetX −1.4% (its old line lasted a median of 32 minutes, against about five hours elsewhere).",
      "Exchange prices better than Pinnacle's at fixed times before kickoff: −3.0%.",
    ],
    report: `${REPO}/research/reports/exchanges-discovery.md`,
  },
  {
    id: "M3",
    title: "Does the market move toward our model?",
    question:
      "Six days before kickoff, when MarketScope's ratings disagree with Pinnacle's line, does Pinnacle move toward the ratings by the close?",
    window: "2026 weeks 1–6, 66 games",
    status: "discovery claim",
    primary: generatedPrimary("M3", "Pinnacle's move to the close per point of disagreement (points)"),
    finding:
      "Yes: for each point the ratings disagreed, Pinnacle's line moved about an eighth of a point their way by kickoff. The ratings hold information early-week lines have not yet absorbed. Not enough to pay yet: taking the model's side at Pinnacle's early line averaged −1.0% (−2.8% to +0.8%) against its close.",
    exploratory: [
      "No clear pattern by size of disagreement (9–15 positions per group).",
      "Is it the model or the early line? Both are measured from Pinnacle's line 6 days out, so noise in that line alone would give a positive slope. Shuffling model lines within weeks gives +0.020 (−0.006 to +0.046), far below +0.116. Against the market's own earlier closes, the model's coefficient is +0.100 (−0.008 to +0.238, 50 games): suggestive, not yet established (Addenda V and W).",
      "If weeks 7–14 confirm the slope, this is the case for buying earlier seasons of history to test it at scale.",
    ],
    report: `${REPO}/research/reports/model-open-discovery.md`,
  },
  {
    id: "W2",
    title: "Model-priced teaser legs (Wong 2.0)",
    question:
      "If each six-point teaser leg is priced with the fair-value model instead of Wong's fixed ranges, do the selected legs clear the −125 break-even (74.5%)?",
    window: "2023–25 out of sample, 243 legs (model fitted on earlier seasons only)",
    status: "no claim",
    primary: {
      label: "Win rate of model-selected legs (claim if above 0.745)",
      estimate: "0.745",
      interval: "0.687 to 0.798",
      threshold: 0.745,
    },
    finding:
      "Exactly at break-even. The model mostly re-selects Wong's legs, and it was slightly overconfident (it expected 76.7%). Tracked forward in the paper portfolio as Wong 2.0.",
    exploratory: [
      "Underdog legs (+1.5 to +3) won about 77–80% and favourite legs about 69–71%, as in the Wong backtest; seen twice in the same seasons, so only the 2026 forward record can test it.",
    ],
    report: `${REPO}/research/reports/teasers-model.md`,
  },
  {
    id: "C1",
    title: "Moneylines priced off the book's own spread",
    question:
      "When a retail book's moneyline is worth more than its own spread implies, is it worth more than the sharp books' closing moneyline?",
    window: "2026 weeks 1–6, 51 positions",
    status: "no claim",
    primary: generatedPrimary("C1", "Mean value per unit at the sharp-consensus close"),
    finding:
      "No, the opposite. When a book's moneyline and spread disagreed, the sharp books sided with the moneyline's price, not the spread's: the spread was the number out of line. Every retail book was below zero.",
    exploratory: [],
    report: `${REPO}/research/reports/cross-market-discovery.md`,
  },
  {
    id: "C2",
    title: "Retail prices above the sharp consensus",
    question:
      "When a retail book's spread, total or moneyline is worth more than the sharp-consensus fair price at the same line (Pinnacle, Circa, Bookmaker.eu, Novig), is it still worth more at the close?",
    window: "2026 weeks 1–6, 131 positions",
    status: "inconclusive",
    primary: generatedPrimary("C2", "Mean value per unit at the sharp-consensus close (as registered)"),
    finding:
      "Positive as registered, but checks after the run weakened it. The odds feed sometimes shows a dead sportsbook market as live: a Caesars −10 last updated on 1 September was still listed at kickoff on 18 October, when the real line was −7. The strongest positions sat on prices unchanged for days. With dead markets removed and prices scored against the sharp books' own numbers at the same line, the value is +2.2% (−0.1% to +4.3%). The held-out weeks decide, counting only prices our own collector also saw.",
    exploratory: [
      "Hard Rock +3.1% (+0.6% to +5.1%) on 16 positions scored against the sharp books' own prices; seen after the run, so not evidence.",
    ],
    report: `${REPO}/research/reports/cross-market-discovery.md`,
  },
  {
    id: "A1",
    title: "Alternate lines above the sharp consensus",
    question:
      "Are retail alternate spreads and totals priced better than the sharp-consensus fair price at their exact line worth more at the close?",
    window: "2026 weeks 1–6, 6,278 alternates",
    status: "no claim",
    primary: generatedPrimary("A1", "Mean value per unit at the sharp-consensus close (as registered)"),
    finding:
      "Withdrawn: a measurement artifact. Our fair-value engine moves a sharp price to another line by adding the same probability shift at every line, which overstates the chances far from the main line, so the same model found the same value at the close. Scored against Pinnacle's, Circa's and Bookmaker.eu's own prices at the same alternate line, these candidates are worth −3.6% (−4.9% to −2.3%), and −5.1% beyond 3 points from the main line.",
    exploratory: [
      "Within 1 point of the main line: +1.6% (+0.4% to +2.8%) against the sharp books' own prices, 115 alternates; registered for the held-out weeks only.",
      "With engine v3, whose line conversion is fitted to the sharp books' own alternate prices (post hoc): 3,049 candidates, +2.3% engine-scored and −1.1% (−2.7% to +0.6%) against the sharp books' own prices. The gap narrows from 7.9 to 3.4 points.",
    ],
    report: `${REPO}/research/reports/alt-ladders-discovery.md`,
  },
  {
    id: "F1",
    title: "Weather-forecast revisions and totals",
    question:
      "When a new weather-model run raises or lowers a game's wind forecast, do totals lag a forecast that is already public?",
    window: "2026 weeks 1–6, 77 outdoor games; 2 games with a qualifying revision, 15 positions",
    status: "no claim",
    primary: generatedPrimary("F1", "Mean value per unit at the sharp-consensus close, forecast side taken 10 minutes after the run is public"),
    finding:
      "Inconclusive despite the interval: only 2 games had a qualifying revision (early-season wind was calm), and a game bootstrap over 2 games cannot support a conclusion. The same positions 3 hours before the run existed were just as negative, so those lines moved for other reasons. Across all 908 model runs, Pinnacle's total did not visibly react to ECMWF wind revisions (+0.004 points per mph within 6 hours, −0.008 to +0.016). Confirmation covers weeks 7–18, where more wind is expected.",
    exploratory: [
      "Forecasts are archived ECMWF runs (Open-Meteo, CC BY 4.0), counted as public 6 hours after each run starts, rebuilt after the fact for every game.",
    ],
    report: `${REPO}/research/reports/weather-timing-discovery.md`,
  },
];
