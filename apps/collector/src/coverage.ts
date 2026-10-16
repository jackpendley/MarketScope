// Coverage reporting for provider verification. Summarizes WHICH books and markets
// were present. It deliberately contains no prices: coverage docs are committed to
// a public repo, and raw odds redistribution is restricted by the provider terms.

import {
  SELECTIONS_BY_MARKET,
  type BookmakerInfo,
  type Market,
  type NormalizationIssueCode,
  type NormalizedEventOdds,
} from "@marketscope/shared";
import type { ProviderUsage } from "./providers/the-odds-api/client";

const MARKET_CODES: Record<Market, string> = { h2h: "M", spreads: "S", totals: "T" };

export interface BookCoverage {
  key: string;
  displayName: string;
  eventsWithData: number;
  completeMarkets: Record<Market, number>;
  latestUpdate: string | null;
}

export interface CoverageReport {
  receivedAt: string;
  durationMs: number;
  usage: ProviderUsage;
  eventsReturned: number;
  eventsRejected: number;
  eventsLive: number;
  books: BookCoverage[];
  issueCounts: Partial<Record<NormalizationIssueCode, number>>;
  /** Per game: "Away @ Home" → per book a market code string like "MST" or "—". */
  matrix: { matchup: string; kickoff: string; isLive: boolean; cells: Record<string, string> }[];
}

export function buildCoverageReport(input: {
  results: NormalizedEventOdds[];
  rejectedCount: number;
  books: readonly BookmakerInfo[];
  markets: readonly Market[];
  usage: ProviderUsage;
  durationMs: number;
  receivedAt: string;
}): CoverageReport {
  const { results, books, markets } = input;

  const bookCoverage: BookCoverage[] = books.map((b) => ({
    key: b.key,
    displayName: b.displayName,
    eventsWithData: 0,
    completeMarkets: { h2h: 0, spreads: 0, totals: 0 },
    latestUpdate: null,
  }));

  const issueCounts: CoverageReport["issueCounts"] = {};
  const matrix: CoverageReport["matrix"] = [];

  for (const { event, quotes, issues } of results) {
    for (const issue of issues) issueCounts[issue.code] = (issueCounts[issue.code] ?? 0) + 1;

    const cells: Record<string, string> = {};
    for (const book of bookCoverage) {
      const bookQuotes = quotes.filter((q) => q.bookmakerKey === book.key);
      if (bookQuotes.length > 0) book.eventsWithData++;

      let code = "";
      for (const m of markets) {
        const complete = SELECTIONS_BY_MARKET[m].every((s) =>
          bookQuotes.some((q) => q.market === m && q.selection === s),
        );
        if (complete) {
          book.completeMarkets[m]++;
          code += MARKET_CODES[m];
        }
      }
      cells[book.key] = code || "—";

      for (const q of bookQuotes) {
        if (
          q.bookmakerUpdatedAt &&
          (!book.latestUpdate || q.bookmakerUpdatedAt > book.latestUpdate)
        ) {
          book.latestUpdate = q.bookmakerUpdatedAt;
        }
      }
    }

    matrix.push({
      matchup: `${event.awayTeam} @ ${event.homeTeam}`,
      kickoff: event.commenceTime,
      isLive: quotes.some((q) => q.isLive),
      cells,
    });
  }

  return {
    receivedAt: input.receivedAt,
    durationMs: input.durationMs,
    usage: input.usage,
    eventsReturned: results.length,
    eventsRejected: input.rejectedCount,
    eventsLive: matrix.filter((m) => m.isLive).length,
    books: bookCoverage,
    issueCounts,
    matrix,
  };
}

export function renderCoverageMarkdown(report: CoverageReport): string {
  const lines: string[] = [];
  const { usage } = report;
  lines.push(`### Live verification — ${report.receivedAt}`, "");
  lines.push(
    `- Events returned: ${report.eventsReturned} (rejected by schema: ${report.eventsRejected}, already started: ${report.eventsLive})`,
    `- Response time: ${report.durationMs} ms`,
    `- Credits: this request ${usage.requestsLast ?? "?"}, used ${usage.requestsUsed ?? "?"}, remaining ${usage.requestsRemaining ?? "?"}`,
    "",
    "| Book | Events with data | Moneyline | Spread | Total | Latest market update |",
    "|---|---|---|---|---|---|",
  );
  for (const b of report.books) {
    lines.push(
      `| ${b.displayName} (\`${b.key}\`) | ${b.eventsWithData} | ${b.completeMarkets.h2h} | ${b.completeMarkets.spreads} | ${b.completeMarkets.totals} | ${b.latestUpdate ?? "—"} |`,
    );
  }

  const issues = Object.entries(report.issueCounts);
  lines.push(
    "",
    `Normalization issues: ${issues.length === 0 ? "none" : issues.map(([c, n]) => `${c} × ${n}`).join(", ")}`,
  );

  lines.push(
    "",
    "<details><summary>Market availability by game (M = moneyline, S = spread, T = total)</summary>",
    "",
  );
  lines.push(`| Game | Kickoff (UTC) | ${report.books.map((b) => b.displayName).join(" | ")} |`);
  lines.push(`|---|---|${report.books.map(() => "---").join("|")}|`);
  for (const row of report.matrix) {
    const live = row.isLive ? " (started)" : "";
    lines.push(
      `| ${row.matchup}${live} | ${row.kickoff} | ${report.books.map((b) => row.cells[b.key]).join(" | ")} |`,
    );
  }
  lines.push("", "</details>", "");
  return lines.join("\n");
}
