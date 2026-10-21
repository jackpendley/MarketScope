// Bookmakers come in two layers:
// - Feeds: provider bookmaker keys we request and store separately (never merged).
// - Board books: the five columns on the odds board. Each column lists its feeds in
//   preference order and displays the first one present for a given event.
//
// Hard Rock: the Arizona feed returned no NFL games on 2026-10-16, while the
// multi-state `hardrockbet` feed did. We collect both (6 keys still count as one
// region-equivalent, so it costs nothing extra) and show AZ whenever it exists.
// See ADR-012.

export interface BookmakerInfo {
  /** The Odds API bookmaker key. */
  key: string;
  displayName: string;
  /** Provider region the book is listed under. Informational: the `bookmakers` request param ignores regions. */
  regionHint: string;
  /** Per provider docs (verified 2026-10-15): only available on paid Odds API plans. */
  paidPlanOnly: boolean;
}

/** Every feed the collector requests. Keep ≤ 10 so a request costs one region-equivalent. */
export const COLLECTED_BOOKMAKERS: readonly BookmakerInfo[] = [
  { key: "draftkings", displayName: "DraftKings", regionHint: "us", paidPlanOnly: false },
  { key: "fanduel", displayName: "FanDuel", regionHint: "us", paidPlanOnly: false },
  { key: "betmgm", displayName: "BetMGM", regionHint: "us", paidPlanOnly: false },
  { key: "williamhill_us", displayName: "Caesars", regionHint: "us", paidPlanOnly: true },
  {
    key: "hardrockbet_az",
    displayName: "Hard Rock Bet (AZ)",
    regionHint: "us2",
    paidPlanOnly: false,
  },
  {
    key: "hardrockbet",
    displayName: "Hard Rock Bet (IN feed)",
    regionHint: "us2",
    paidPlanOnly: false,
  },
];

export const COLLECTED_BOOKMAKER_KEYS: readonly string[] = COLLECTED_BOOKMAKERS.map((b) => b.key);

/**
 * Reference books: stored for research (e.g. a sharp market for comparison) but never part
 * of the five-book board, its consensus, or contemporaneous signals (spec 2.6, 4.1).
 * Currently sourced from OddsPapi historical imports only.
 */
export const REFERENCE_BOOKMAKERS: readonly BookmakerInfo[] = [
  {
    key: "pinnacle",
    displayName: "Pinnacle (reference)",
    regionHint: "oddspapi",
    paidPlanOnly: false,
  },
];

/**
 * Books stored only as minute-level line moves (MS-042, `line_moves`), never as snapshots:
 * market makers used as references for the sharp-market studies. Sourced from OddsPapi.
 */
export const LINE_MOVE_ONLY_BOOKMAKERS: readonly BookmakerInfo[] = [
  { key: "circa", displayName: "Circa (reference)", regionHint: "oddspapi", paidPlanOnly: false },
  {
    key: "bookmaker_eu",
    displayName: "Bookmaker.eu (reference)",
    regionHint: "oddspapi",
    paidPlanOnly: false,
  },
  // Exchanges (MS-051): top-of-book prices set by other traders, low margin.
  { key: "novig", displayName: "Novig (exchange)", regionHint: "oddspapi", paidPlanOnly: false },
  {
    key: "prophetx",
    displayName: "ProphetX (exchange)",
    regionHint: "oddspapi",
    paidPlanOnly: false,
  },
  { key: "kalshi", displayName: "Kalshi (exchange)", regionHint: "oddspapi", paidPlanOnly: false },
];

export interface BoardBook {
  id: string;
  displayName: string;
  /** Feed keys in preference order; the first one present for an event is displayed. */
  feeds: readonly string[];
}

/** The five columns of the personalized odds board, in display order. */
export const BOARD_BOOKS: readonly BoardBook[] = [
  { id: "draftkings", displayName: "DraftKings", feeds: ["draftkings"] },
  { id: "fanduel", displayName: "FanDuel", feeds: ["fanduel"] },
  { id: "betmgm", displayName: "BetMGM", feeds: ["betmgm"] },
  { id: "caesars", displayName: "Caesars", feeds: ["williamhill_us"] },
  { id: "hardrock", displayName: "Hard Rock Bet", feeds: ["hardrockbet_az", "hardrockbet"] },
];

export function getBookmakerInfo(key: string): BookmakerInfo | undefined {
  return (
    COLLECTED_BOOKMAKERS.find((b) => b.key === key) ??
    REFERENCE_BOOKMAKERS.find((b) => b.key === key) ??
    LINE_MOVE_ONLY_BOOKMAKERS.find((b) => b.key === key)
  );
}
