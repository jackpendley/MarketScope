import { describe, expect, it } from "vitest";
import type { Market, Selection } from "./domain";
import {
  computeSignals,
  SIGNAL_DEFINITIONS,
  SIGNAL_TYPES,
  type SignalObservation,
} from "./signals";

const H = 3_600_000;
const t0 = Date.parse("2026-10-14T00:00:00Z");
const at = (h: number) => new Date(t0 + h * H).toISOString();
let nextId = 1;
function o(
  book: string,
  h: number,
  point: number | null,
  price = -110,
  market: Market = "spreads",
  selection: Selection = "HOME",
  isLive = false,
): SignalObservation {
  return {
    id: nextId++,
    bookmakerKey: book,
    observedAt: at(h),
    point,
    americanPrice: price,
    bookmakerUpdatedAt: null,
    isLive,
    market,
    selection,
  };
}
const ofType = (signals: ReturnType<typeof computeSignals>, type: string) =>
  signals.filter((s) => s.type === type);

describe("signal definitions", () => {
  it("defines every type with a version, definition, and limitations", () => {
    for (const type of SIGNAL_TYPES) {
      expect(SIGNAL_DEFINITIONS[type]).toMatchObject({ type, version: 1 });
      expect(SIGNAL_DEFINITIONS[type].definition.length).toBeGreaterThan(40);
      expect(SIGNAL_DEFINITIONS[type].limitations.length).toBeGreaterThan(20);
    }
  });
});

describe("A/B/C: per-feed line, price, and key-number signals", () => {
  const first = o("draftkings", 0, -2.5, -110);
  const second = o("draftkings", 6, -3.5, -105); // line + price: crosses -3
  const third = o("draftkings", 12, -3.5, -120); // price only
  const signals = computeSignals([third, first, second]); // any input order

  it("emits a line move with home-orientation delta and both observations as evidence", () => {
    expect(ofType(signals, "line_move")).toEqual([
      expect.objectContaining({
        bookmakerKey: "draftkings",
        market: "spreads",
        selection: "HOME",
        value: -1,
        windowStart: at(0),
        windowEnd: at(6),
        detectedAt: at(6),
        evidence: [first.id, second.id],
        details: expect.objectContaining({ direction: "toward-home", acrossGap: false }),
      }),
    ]);
  });

  it("emits price moves only when the line is unchanged, in cents", () => {
    expect(ofType(signals, "price_move")).toEqual([
      expect.objectContaining({
        value: -15,
        windowStart: at(6),
        windowEnd: at(12),
        evidence: [second.id, third.id],
      }),
    ]);
  });

  it("emits a key-number signal for the crossing", () => {
    expect(ofType(signals, "key_number")).toEqual([
      expect.objectContaining({
        value: -3,
        details: expect.objectContaining({ kind: "crossed", key: 3 }),
      }),
    ]);
  });

  it("ignores in-play observations", () => {
    const live = computeSignals([
      o("fanduel", 0, -3),
      o("fanduel", 6, -7, -110, "spreads", "HOME", true),
    ]);
    expect(live).toEqual([]);
  });

  it("tracks totals on the Over side and moneylines on the home side", () => {
    const s = computeSignals([
      o("fanduel", 0, 44.5, -110, "totals", "OVER"),
      o("fanduel", 6, 45.5, -110, "totals", "OVER"),
      o("fanduel", 0, null, -150, "h2h", "HOME"),
      o("fanduel", 6, null, -170, "h2h", "HOME"),
      o("fanduel", 0, 44.5, -110, "totals", "UNDER"),
      o("fanduel", 6, 45.5, -110, "totals", "UNDER"),
    ]);
    expect(ofType(s, "line_move").map((x) => [x.market, x.value])).toEqual([["totals", 1]]);
    expect(ofType(s, "price_move").map((x) => [x.market, x.value])).toEqual([["h2h", -20]]);
  });
});

describe("D: book divergence", () => {
  it("flags a book 0.5+ from the snapshot consensus, only when the divergence begins", () => {
    const snapshot = (h: number, dk: number) => [
      o("draftkings", h, dk),
      o("fanduel", h, -3),
      o("betmgm", h, -3),
      o("hardrockbet_az", h, -3),
    ];
    const signals = ofType(
      computeSignals([
        ...snapshot(0, -3),
        ...snapshot(6, -3.5),
        ...snapshot(12, -3.5),
        ...snapshot(18, -3),
        ...snapshot(24, -4),
      ]),
      "book_divergence",
    );
    expect(signals.map((s) => [s.detectedAt, s.bookmakerKey, s.value])).toEqual([
      [at(6), "draftkings", -0.5],
      [at(24), "draftkings", -1],
    ]);
    expect(signals[0]!.evidence).toHaveLength(4);
    expect(signals[0]!.details).toMatchObject({ consensus: -3 });
  });

  it("needs at least three books in the same snapshot", () => {
    expect(
      ofType(computeSignals([o("draftkings", 0, -4), o("fanduel", 0, -3)]), "book_divergence"),
    ).toEqual([]);
  });

  it("never compares books from different snapshots", () => {
    const s = computeSignals([o("draftkings", 0, -4), o("fanduel", 6, -3), o("betmgm", 6, -3)]);
    expect(ofType(s, "book_divergence")).toEqual([]);
  });

  it("uses one Hard Rock feed so a book can't outvote itself", () => {
    const s = computeSignals([
      o("draftkings", 0, -3),
      o("fanduel", 0, -3),
      o("hardrockbet_az", 0, -4),
      o("hardrockbet", 0, -4),
    ]);
    // HR counted once (AZ): DK -3, FD -3, HR -4 → consensus -3, HR diverges by -1. Counting the
    // IN feed as well would pull the median to -3.5 and flag DK and FD instead.
    expect(ofType(s, "book_divergence").map((x) => [x.bookmakerKey, x.value])).toEqual([
      ["hardrockbet_az", -1],
    ]);
  });
});

describe("E: rapid consensus move", () => {
  const consensusSnapshot = (h: number, v: number) => [
    o("draftkings", h, v),
    o("fanduel", h, v),
    o("betmgm", h, v),
  ];

  it("flags a 1+ point consensus change within 6 hours", () => {
    const s = ofType(
      computeSignals([...consensusSnapshot(0, -3), ...consensusSnapshot(6, -4)]),
      "rapid_consensus_move",
    );
    expect(s).toEqual([
      expect.objectContaining({
        value: -1,
        windowStart: at(0),
        windowEnd: at(6),
        bookmakerKey: null,
        details: expect.objectContaining({ fromConsensus: -3, toConsensus: -4, minutes: 360 }),
      }),
    ]);
    expect(s[0]!.evidence).toHaveLength(6);
  });

  it("does not call a move across a longer collection gap rapid", () => {
    const s = computeSignals([...consensusSnapshot(0, -3), ...consensusSnapshot(18, -5)]);
    expect(ofType(s, "rapid_consensus_move")).toEqual([]);
  });

  it("requires at least three books for a consensus", () => {
    const s = computeSignals([
      o("draftkings", 0, -3),
      o("fanduel", 0, -3),
      o("draftkings", 6, -4.5),
      o("fanduel", 6, -4.5),
    ]);
    expect(ofType(s, "rapid_consensus_move")).toEqual([]);
  });

  it("ignores moves smaller than a point", () => {
    expect(
      ofType(
        computeSignals([...consensusSnapshot(0, -3), ...consensusSnapshot(6, -3.5)]),
        "rapid_consensus_move",
      ),
    ).toEqual([]);
  });
});

describe("F: same-line price disagreement", () => {
  it("flags 10+ cents between books at the identical line, at onset only", () => {
    const s = ofType(
      computeSignals([
        o("draftkings", 0, -3, -105),
        o("fanduel", 0, -3, -118),
        o("betmgm", 0, -3.5, -130), // different line: never compared with -3
        o("draftkings", 6, -3, -105),
        o("fanduel", 6, -3, -118), // still disagreeing: no new signal
      ]),
      "same_line_price_disagreement",
    );
    expect(s).toEqual([
      expect.objectContaining({
        detectedAt: at(0),
        market: "spreads",
        selection: "HOME",
        value: 13,
        details: expect.objectContaining({
          point: -3,
          best: { bookmakerKey: "draftkings", price: -105 },
          worst: { bookmakerKey: "fanduel", price: -118 },
          books: 2,
        }),
      }),
    ]);
  });

  it("measures across even money without the 200-point jump", () => {
    const s = computeSignals([
      o("draftkings", 0, 3, 105, "spreads", "AWAY"),
      o("fanduel", 0, 3, -105, "spreads", "AWAY"),
    ]);
    expect(ofType(s, "same_line_price_disagreement")[0]!.value).toBe(10);
  });

  it("ignores small differences", () => {
    const s = computeSignals([o("draftkings", 0, -3, -108), o("fanduel", 0, -3, -112)]);
    expect(ofType(s, "same_line_price_disagreement")).toEqual([]);
  });
});

describe("computeSignals", () => {
  it("is deterministic and sorted by time", () => {
    const obs = [
      o("draftkings", 6, -4),
      o("draftkings", 0, -3),
      o("fanduel", 0, -3),
      o("fanduel", 6, -3.5),
    ];
    const a = computeSignals(obs);
    expect(computeSignals([...obs].reverse())).toEqual(a);
    expect(a.map((s) => s.detectedAt)).toEqual([...a.map((s) => s.detectedAt)].sort());
  });
});

describe("D: divergence on a genuine split", () => {
  it("flags no one when books split evenly around the consensus", () => {
    const s = computeSignals([
      o("draftkings", 0, -3),
      o("fanduel", 0, -3),
      o("betmgm", 0, -3.5),
      o("hardrockbet_az", 0, -3.5),
    ]);
    expect(s.filter((x) => x.type === "book_divergence")).toEqual([]);
  });
});
