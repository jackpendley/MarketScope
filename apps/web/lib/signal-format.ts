// Human-readable descriptions of stored signals. Pure; text only (no recommendations).
import {
  formatAmericanOdds,
  formatPoint,
  getBookmakerInfo,
  SIGNAL_DEFINITIONS,
  type Market,
  type SignalType,
} from "@marketscope/shared";

export interface DescribableSignal {
  type: string;
  market: Market;
  selection: "HOME" | "AWAY" | "OVER" | "UNDER" | null;
  bookmakerKey: string | null;
  value: number;
  details: Record<string, unknown>;
  homeTeam: string;
  awayTeam: string;
}

const short = (team: string) => team.split(" ").at(-1) ?? team;
const book = (key: unknown) =>
  typeof key === "string" ? (getBookmakerInfo(key)?.displayName ?? key) : "Unknown book";
const num = (v: unknown) => (typeof v === "number" ? v : null);
const signed = (n: number, digits = 1) =>
  `${n > 0 ? "+" : n < 0 ? "-" : ""}${Math.abs(n).toFixed(digits)}`;

function side(s: DescribableSignal): string {
  switch (s.selection) {
    case "HOME":
      return short(s.homeTeam);
    case "AWAY":
      return short(s.awayTeam);
    case "OVER":
      return "Over";
    case "UNDER":
      return "Under";
    default:
      return "";
  }
}

export function signalTitle(type: string): string {
  return SIGNAL_DEFINITIONS[type as SignalType]?.title ?? type;
}

export function describeSignal(s: DescribableSignal): string {
  const d = s.details;
  const pt = (v: unknown, market: Market = s.market) => formatPoint(num(v), market);
  switch (s.type) {
    case "line_move": {
      const what = s.market === "totals" ? "total" : `${side(s)} spread`;
      const dir =
        d.direction === "toward-home"
          ? `, toward ${short(s.homeTeam)}`
          : d.direction === "toward-away"
            ? `, toward ${short(s.awayTeam)}`
            : "";
      return `${book(s.bookmakerKey)}: ${what} ${pt(d.fromPoint)} → ${pt(d.toPoint)} (${signed(s.value)} pts${dir})`;
    }
    case "price_move": {
      const line = s.market === "h2h" ? "moneyline" : pt(d.toPoint);
      return `${book(s.bookmakerKey)}: ${side(s)} ${line} price ${formatAmericanOdds(Number(d.fromPrice))} → ${formatAmericanOdds(Number(d.toPrice))} (${signed(s.value, 0)}¢)`;
    }
    case "key_number": {
      const kind = d.kind === "landed-on" ? "landed on" : "crossed";
      return `${book(s.bookmakerKey)}: ${side(s)} spread ${kind} ${formatPoint(s.value, "spreads")} (${pt(d.fromPoint)} → ${pt(d.toPoint)})`;
    }
    case "book_divergence":
      return `${book(s.bookmakerKey)}: ${side(s)} ${pt(d.point)} vs consensus ${pt(d.consensus)} (${signed(s.value)} pts)`;
    case "rapid_consensus_move":
      return `Consensus ${side(s)} spread ${pt(d.fromConsensus)} → ${pt(d.toConsensus)} in ${Math.round(Number(d.minutes) / 60)} h (${signed(s.value)} pts)`;
    case "same_line_price_disagreement": {
      const best = d.best as { bookmakerKey?: string; price?: number } | undefined;
      const worst = d.worst as { bookmakerKey?: string; price?: number } | undefined;
      const line = s.market === "h2h" ? "moneyline" : pt(d.point);
      return `${side(s)} ${line}: ${book(best?.bookmakerKey)} ${formatAmericanOdds(Number(best?.price))} vs ${book(worst?.bookmakerKey)} ${formatAmericanOdds(Number(worst?.price))} (${Math.round(s.value)}¢ apart)`;
    }
    default:
      return `${signalTitle(s.type)} (value ${s.value})`;
  }
}
