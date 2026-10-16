import "server-only";
import { getGame, selectionHistory, type Database, type GameRow } from "@marketscope/db";
import {
  buildSeriesByBook,
  describeMovement,
  getBookmakerInfo,
  SELECTIONS_BY_MARKET,
  type HistoryObservation,
  type Market,
  type Movement,
  type Selection,
} from "@marketscope/shared";
import type { NamedSeries } from "@/lib/server/history";

export const REPLAY_GAP_MINUTES = 12 * 60;

export interface ReplaySelectionData {
  selection: Selection;
  label: string;
  observations: HistoryObservation[];
}

export interface NamedMovement extends Movement {
  displayName: string;
}

export interface MarketReplayData {
  game: GameRow;
  market: Market;
  chartSelection: Selection;
  selections: ReplaySelectionData[];
  /** Per-book series for the charted side (every observation, so replay state is exact). */
  series: NamedSeries[];
  movements: NamedMovement[];
  sources: string[];
  truncated: boolean;
}

export function selectionLabel(selection: Selection, game: Pick<GameRow, "homeTeam" | "awayTeam">) {
  return selection === "HOME"
    ? game.homeTeam
    : selection === "AWAY"
      ? game.awayTeam
      : selection === "OVER"
        ? "Over"
        : "Under";
}

/** Movements for one selection's per-book series, oldest first, with direction and key numbers. */
export function toMovements(
  series: readonly NamedSeries[],
  market: Market,
  selection: Selection,
): NamedMovement[] {
  return series
    .flatMap((s) =>
      s.changes.map((c) => ({
        ...describeMovement(c, market, selection),
        displayName: s.displayName,
      })),
    )
    .sort(
      (a, b) =>
        a.intervalEnd.localeCompare(b.intervalEnd) || a.bookmakerKey.localeCompare(b.bookmakerKey),
    );
}

export async function loadMarketReplay(
  db: Database,
  gameId: string,
  { market, chartSelection, from }: { market: Market; chartSelection: Selection; from?: string },
): Promise<MarketReplayData | null> {
  const game = await getGame(db, gameId);
  if (!game) return null;

  const results = await Promise.all(
    SELECTIONS_BY_MARKET[market].map(async (selection) => ({
      selection,
      ...(await selectionHistory(db, {
        eventId: game.id,
        market,
        selection,
        from,
        includeLive: false,
      })),
    })),
  );

  const selections: ReplaySelectionData[] = results.map((r) => ({
    selection: r.selection,
    label: selectionLabel(r.selection, game),
    observations: r.rows.map(
      ({ bookmakerKey, observedAt, point, americanPrice, bookmakerUpdatedAt, isLive }) => ({
        bookmakerKey,
        observedAt,
        point,
        americanPrice,
        bookmakerUpdatedAt,
        isLive,
      }),
    ),
  }));
  const charted = selections.find((s) => s.selection === chartSelection) ?? selections[0]!;
  const series = buildSeriesByBook(charted.observations, {
    gapMinutes: REPLAY_GAP_MINUTES,
    resolution: "all",
  }).map((s) => ({
    ...s,
    displayName: getBookmakerInfo(s.bookmakerKey)?.displayName ?? s.bookmakerKey,
  }));

  return {
    game,
    market,
    chartSelection: charted.selection,
    selections,
    series,
    movements: toMovements(series, market, charted.selection),
    sources: [...new Set(results.flatMap((r) => r.rows.map((row) => row.source)))].sort(),
    truncated: results.some((r) => r.truncated),
  };
}
