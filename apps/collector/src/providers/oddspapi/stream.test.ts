import { describe, expect, it } from "vitest";
import { parseHistoryStream } from "./stream";

const entry = (createdAt: string, price: number) => ({
  createdAt,
  price,
  active: true,
  limit: null,
});

const response = {
  fixtureId: "f",
  bookmakers: {
    "novig.us": {
      markets: {
        "141": {
          outcomes: { "141": { players: { "0": [entry("2026-10-10T08:00:00.000Z", 1.9)] } } },
        },
        "999": {
          outcomes: { "999": { players: { "0": [entry("2026-10-10T08:00:00.000Z", 3.0)] } } },
        },
      },
    },
    pinnacle: {
      markets: {
        "141": {
          outcomes: {
            "141": {
              players: {
                "0": [
                  entry("2026-10-10T08:00:00.000Z", 1.95),
                  entry("2026-10-10T09:00:00.000Z", 1.91),
                ],
              },
            },
            "142": { players: { "0": [entry("2026-10-10T08:00:00.000Z", 1.95)] } },
          },
        },
      },
    },
  },
};

/** The body as a byte stream, cut into small, awkward chunks (splitting tokens and UTF-8). */
function chunked(text: string, size = 7): ReadableStream<Uint8Array> {
  const bytes = new TextEncoder().encode(text);
  let i = 0;
  return new ReadableStream({
    pull(controller) {
      if (i >= bytes.length) return controller.close();
      controller.enqueue(bytes.slice(i, (i += size)));
    },
  });
}

describe("parseHistoryStream", () => {
  it("rebuilds exactly the kept markets from a chunked stream", async () => {
    const got = await parseHistoryStream(chunked(JSON.stringify(response)), new Set([141]));
    const expected = structuredClone(response.bookmakers);
    delete (expected["novig.us"].markets as Record<string, unknown>)["999"];
    expect(got).toEqual({ bookmakers: expected });
  });

  it("keeps dotted book slugs and drops books with no kept market", async () => {
    const got = await parseHistoryStream(chunked(JSON.stringify(response)), new Set([999]));
    expect(Object.keys(got.bookmakers)).toEqual(["novig.us"]);
  });

  it("accepts any async iterable of bytes", async () => {
    async function* parts() {
      yield new TextEncoder().encode(JSON.stringify(response).slice(0, 50));
      yield new TextEncoder().encode(JSON.stringify(response).slice(50));
    }
    const got = await parseHistoryStream(parts(), new Set([141]));
    expect(got.bookmakers.pinnacle!.markets["141"]!.outcomes["141"]!.players["0"]).toHaveLength(2);
  });

  it("fails on a truncated body instead of returning partial data", async () => {
    const text = JSON.stringify(response);
    await expect(
      parseHistoryStream(chunked(text.slice(0, text.length - 10)), new Set([141])),
    ).rejects.toThrow();
  });
});
