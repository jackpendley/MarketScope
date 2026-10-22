import { describe, expect, it, vi } from "vitest";
import { createOddsPapiClient } from "./client";

const history = {
  bookmakers: {
    kalshi: {
      markets: {
        "141": {
          outcomes: {
            "141": {
              players: {
                "0": [{ createdAt: "2026-10-10T08:00:00.000Z", price: 1.9, active: true }],
              },
            },
          },
        },
        "999": { outcomes: { "999": { players: { "0": [] } } } },
      },
    },
  },
};

function client(body: string, status = 200) {
  const fetchImpl = vi.fn(async () => new Response(body, { status }));
  return {
    fetchImpl,
    c: createOddsPapiClient({
      apiKey: "secret-key",
      fetchImpl,
      sleep: async () => {},
      now: () => 0,
    }),
  };
}

describe("OddsPapi client", () => {
  it("streams historical odds and keeps only the requested markets", async () => {
    const { c } = client(JSON.stringify(history));
    const got = await c.historicalOdds("f1", ["kalshi"], { markets: new Set([141]) });
    expect(Object.keys(got.bookmakers.kalshi!.markets)).toEqual(["141"]);
  });

  it("parses the whole body when no market filter is given", async () => {
    const { c } = client(JSON.stringify(history));
    const got = await c.historicalOdds("f1", ["kalshi"]);
    expect(Object.keys(got.bookmakers.kalshi!.markets)).toEqual(["141", "999"]);
  });

  it("never puts the key in an error", async () => {
    const { c } = client("bad key secret-key", 401);
    await expect(c.historicalOdds("f1", ["kalshi"])).rejects.toThrow(/HTTP 401/);
    await expect(c.historicalOdds("f1", ["kalshi"])).rejects.not.toThrow(/secret-key/);
  });
});
