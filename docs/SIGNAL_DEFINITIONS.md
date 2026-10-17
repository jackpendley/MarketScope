# Signal Definitions

Source of truth: `packages/shared/src/signals.ts` (`SIGNAL_DEFINITIONS`, `SIGNAL_THRESHOLDS`, `computeSignals`). Every signal is a pure function of stored pregame observations. Identical inputs give identical output.

**Signals describe observable market behavior.** They do not identify professional ("sharp") betting activity, explain _why_ a line moved, or recommend bets.

## Common rules (algorithm v1)

- **Input:** one game's pregame observations (`is_live = false`), all markets. In-play prices are never used.
- **Snapshot:** all observations sharing one `observed_at`, which is one collection run. _Contemporaneous_ signals (D, E, F) compare only books inside the **same snapshot**. Older quotes are never carried forward.
- **Board books:** contemporaneous signals use one feed per board book, preferring Hard Rock AZ over the IN feed (ADR-012), so a book never counts twice.
- **Changes** are detected by **value** (point or price), never by the provider's `last_update`. A change happened somewhere in `(window_start, window_end]`.
- **Gaps:** consecutive observations more than 12 h apart are a gap. Changes across a gap carry `acrossGap: true`.
- **Orientation:** spreads use the home team's line. A home spread rising (−3.5 → −2.5) moves _toward the away team_.
- **Evidence:** every detection stores the `odds_observations.id` values it was computed from.
- **Storage:** `market_signals`. Recompute replaces rows per (game, type, version) in one transaction, after every scheduled collection.

## Signals

| Type (v1)                      | Definition                                                                                                                                                                         | Value                           | Scope                                         |
| ------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------- | --------------------------------------------- |
| `line_move`                    | A book's home spread or total point differs from its previous observation                                                                                                          | point change (home orientation) | per feed; spreads HOME, totals OVER           |
| `price_move`                   | Same book, same line, different price                                                                                                                                              | change in cents¹                | per feed; spreads HOME, h2h HOME, totals OVER |
| `key_number`                   | A home-spread move crosses or lands on ±3 or ±7 (signed: −3.5 → +3.5 crosses −3 and +3; −1.5 → +1.5 crosses none)                                                                  | signed key                      | per feed                                      |
| `book_divergence`              | In one snapshot, a book's home spread is ≥ 0.5 from the consensus (median of **all** target books in that snapshot, ≥ 3). Emitted at **onset**, the first snapshot of a divergence | book − consensus                | board books                                   |
| `rapid_consensus_move`         | Consensus home spread (median, ≥ 3 books in a snapshot) differs by ≥ 1.0 from the earliest consensus within the previous **6 h**. Each anchor is used once                         | consensus change                | board books                                   |
| `same_line_price_disagreement` | In one snapshot, ≥ 2 books at the identical market, side, and line differ in price by ≥ 10 cents¹. Emitted at onset                                                                | price spread in cents           | board books, every side                       |

¹ **Cents** are measured on a continuous American-odds scale: −110 → −10, +110 → +10, ±100 → 0. So −105 vs +105 is 10 cents apart, not 210.

## Why these choices

- **Divergence uses the full-snapshot median.** A leave-one-out median is unstable with 3 books: the two "others" average, so the _non-outliers_ get flagged. With the full median, DK −3, FD −3, HR −4 flags only HR, and an even 2-vs-2 split flags nobody.
- **Onset-only emission** for D and F stops one persistent condition from producing a signal every snapshot. Persistence isn't tracked in v1.
- **The 6-hour window** for E means a move spanning a long collection gap is never called "rapid". At 4 snapshots a day, only consecutive snapshots qualify.

## Limitations

- **Polling resolution:** movement timing is only known to within one collection interval (about 6 h).
- **Coverage:** only the target books are compared. Caesars is absent on the free data plan, and BetMGM posts only the current week.
- **Correlation, not cause:** injuries, weather, and risk management all move lines. A book moving "first" in our data may only have been _observed_ first.
- **Changing a threshold or rule requires a version bump.** Old and new versions can then coexist in `market_signals` and be compared.
