// Parses /nfl search params into validated filter values. Pure; unknown values fall back
// to defaults instead of erroring (it's a UI filter, not an API).
import { BOARD_BOOKS, isMarket } from "@marketscope/shared";
import type { BoardFilterValues } from "@/components/board-filters";
import type { EventBoard } from "@/lib/odds-board";

type SearchParams = Record<string, string | string[] | undefined>;

const first = (v: string | string[] | undefined) => (Array.isArray(v) ? v[0] : v);
const all = (v: string | string[] | undefined) =>
  v === undefined ? [] : Array.isArray(v) ? v : [v];

export function parseBoardFilters(sp: SearchParams): BoardFilterValues {
  const market = first(sp.market) ?? "";
  const validBookIds = new Set(BOARD_BOOKS.map((b) => b.id));
  const books = all(sp.books).filter((b) => validBookIds.has(b));
  const days = Number(first(sp.days));
  return {
    q: (first(sp.q) ?? "").trim().slice(0, 50),
    market: isMarket(market) ? market : null,
    // No books selected means "show all": an empty board helps no one.
    books: new Set(books.length > 0 ? books : validBookIds),
    days: [1, 3, 7, 14].includes(days) ? days : 7,
  };
}

export function matchesTeamSearch(
  board: Pick<EventBoard, "homeTeam" | "awayTeam">,
  q: string,
): boolean {
  if (!q) return true;
  const needle = q.toLowerCase();
  return (
    board.homeTeam.toLowerCase().includes(needle) || board.awayTeam.toLowerCase().includes(needle)
  );
}
