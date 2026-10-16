import {
  COLLECTED_BOOKMAKER_KEYS,
  isValidAmericanOdds,
  normalizeEventOdds,
  parseOddsResponse,
} from "@marketscope/shared";
import { describe, expect, it } from "vitest";
import { assertSyntheticTarget, generateSyntheticHistory } from "./synthetic";

const now = new Date("2026-10-16T12:00:00Z");

describe("generateSyntheticHistory", () => {
  const history = generateSyntheticHistory({ now });

  it("is deterministic for a given seed", () => {
    expect(generateSyntheticHistory({ now })).toEqual(history);
    expect(generateSyntheticHistory({ now, seed: 7 })).not.toEqual(history);
  });

  it("skips outage snapshots, leaving a data gap", () => {
    expect(history).toHaveLength(18); // 20 slots minus indexes 7 and 8
    const times = history.map((s) => Date.parse(s.receivedAt));
    const gaps = times.slice(1).map((t, i) => (t - times[i]!) / 3_600_000);
    expect(gaps.filter((h) => h === 18)).toHaveLength(1);
    expect(history.at(-1)!.receivedAt).toBe(now.toISOString());
  });

  it("produces payloads that pass the real parser with valid prices and opposite spreads", () => {
    for (const snap of history) {
      const { events, rejected } = parseOddsResponse(snap.payload);
      expect(rejected).toEqual([]);
      for (const e of events) {
        expect(e.id.startsWith("synthetic-history-")).toBe(true);
        expect(Date.parse(e.commence_time)).toBeGreaterThan(now.getTime());
        const { quotes, issues } = normalizeEventOdds(e, {
          observedAt: snap.receivedAt,
          targetBookmakers: COLLECTED_BOOKMAKER_KEYS,
        });
        expect(quotes.every((q) => isValidAmericanOdds(q.americanPrice))).toBe(true);
        expect(issues.filter((i) => i.code === "INCONSISTENT_SPREAD")).toEqual([]);
      }
    }
  });

  it("drops BetMGM from two snapshots and actually moves some lines", () => {
    const mgmPresent = history.map((s) =>
      (s.payload as { bookmakers: { key: string }[] }[])[0]!.bookmakers.some(
        (b) => b.key === "betmgm",
      ),
    );
    expect(mgmPresent.filter((p) => !p)).toHaveLength(2);
    const homePoints = new Set(
      history.map(
        (s) =>
          (
            s.payload as {
              bookmakers: {
                key: string;
                markets: { key: string; outcomes: { point?: number }[] }[];
              }[];
            }[]
          )[0]!.bookmakers
            .find((b) => b.key === "draftkings")!
            .markets.find((m) => m.key === "spreads")!.outcomes[0]!.point,
      ),
    );
    expect(homePoints.size).toBeGreaterThan(1);
  });
});

describe("assertSyntheticTarget", () => {
  it("only allows demo/e2e databases", () => {
    expect(() => assertSyntheticTarget("postgres://localhost:5432/marketscope_demo")).not.toThrow();
    expect(() =>
      assertSyntheticTarget("postgres://localhost:5432/marketscope_e2e_test"),
    ).not.toThrow();
    expect(() => assertSyntheticTarget("postgres://localhost:5432/marketscope_dev")).toThrow(
      /Refusing/,
    );
    expect(() => assertSyntheticTarget("postgresql://pooler.supabase.com:5432/postgres")).toThrow(
      /Refusing/,
    );
  });
});
