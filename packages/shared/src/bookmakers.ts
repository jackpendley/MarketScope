export interface BookmakerInfo {
  /** The Odds API bookmaker key. */
  key: string;
  displayName: string;
  /** Provider region the book is listed under. Informational: the `bookmakers` request param ignores regions. */
  regionHint: string;
  /** Per provider docs (verified 2026-10-15): only available on paid Odds API plans. */
  paidPlanOnly: boolean;
}

/** The five books on the personalized odds board, in display order. */
export const TARGET_BOOKMAKERS: readonly BookmakerInfo[] = [
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
];

export const TARGET_BOOKMAKER_KEYS: readonly string[] = TARGET_BOOKMAKERS.map((b) => b.key);
