import { describe, expect, it, vi } from "vitest";
import {
  createTheOddsApiClient,
  estimateOddsCost,
  parseUsageHeaders,
  ProviderError,
} from "./client";

const API_KEY = "test-secret-key-123";

function jsonResponse(body: unknown, status = 200, headers: Record<string, string> = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json", ...headers },
  });
}

function makeClient(responses: (Response | Error)[]) {
  const fetchImpl = vi.fn(async () => {
    const next = responses.shift();
    if (!next) throw new Error("no more responses");
    if (next instanceof Error) throw next;
    return next;
  });
  const sleep = vi.fn(async () => {});
  const client = createTheOddsApiClient({
    apiKey: API_KEY,
    fetchImpl: fetchImpl as unknown as typeof fetch,
    sleep,
  });
  return { client, fetchImpl, sleep };
}

async function captureError(promise: Promise<unknown>): Promise<ProviderError> {
  try {
    await promise;
  } catch (err) {
    if (err instanceof ProviderError) return err;
    throw err;
  }
  throw new Error("expected ProviderError");
}

const odds = { sportKey: "americanfootball_nfl", bookmakers: ["draftkings"], markets: ["h2h"] };

describe("parseUsageHeaders", () => {
  it("reads the three quota headers", () => {
    const usage = parseUsageHeaders(
      new Headers({
        "x-requests-remaining": "497",
        "x-requests-used": "3",
        "x-requests-last": "3",
      }),
    );
    expect(usage).toEqual({ requestsRemaining: 497, requestsUsed: 3, requestsLast: 3 });
  });

  it("returns nulls when headers are absent or malformed", () => {
    expect(parseUsageHeaders(new Headers({ "x-requests-used": "abc" }))).toEqual({
      requestsRemaining: null,
      requestsUsed: null,
      requestsLast: null,
    });
  });
});

describe("estimateOddsCost", () => {
  it("charges one region-equivalent per 10 named bookmakers", () => {
    const five = ["a", "b", "c", "d", "e"];
    expect(estimateOddsCost(["h2h", "spreads", "totals"], five)).toBe(3);
    expect(
      estimateOddsCost(
        ["h2h"],
        Array.from({ length: 11 }, (_, i) => `b${i}`),
      ),
    ).toBe(2);
  });
});

describe("createTheOddsApiClient", () => {
  it("sends the request params and returns data with usage", async () => {
    const { client, fetchImpl } = makeClient([
      jsonResponse([], 200, { "x-requests-remaining": "497", "x-requests-last": "3" }),
    ]);
    const res = await client.fetchOdds({
      ...odds,
      bookmakers: ["draftkings", "fanduel"],
      markets: ["h2h", "spreads"],
    });

    expect(res.data).toEqual([]);
    expect(res.usage.requestsRemaining).toBe(497);
    expect(res.attempts).toBe(1);
    const url = new URL(String((fetchImpl.mock.calls[0] as unknown[])[0]));
    expect(url.pathname).toBe("/v4/sports/americanfootball_nfl/odds/");
    expect(url.searchParams.get("bookmakers")).toBe("draftkings,fanduel");
    expect(url.searchParams.get("markets")).toBe("h2h,spreads");
    expect(url.searchParams.get("oddsFormat")).toBe("american");
    expect(url.searchParams.get("dateFormat")).toBe("iso");
  });

  it("does not retry auth failures and never leaks the key", async () => {
    const { client, fetchImpl } = makeClient([
      jsonResponse({ message: `API key ${API_KEY} is not valid`, error_code: "INVALID_KEY" }, 401),
    ]);
    const err = await captureError(client.fetchOdds(odds));

    expect(err.code).toBe("AUTH");
    expect(err.retryable).toBe(false);
    expect(fetchImpl).toHaveBeenCalledTimes(1);
    expect(err.message).not.toContain(API_KEY);
    expect(err.message).toContain("[REDACTED]");
    expect(err.message).not.toContain("apiKey");
  });

  it("retries a 429 with backoff, then succeeds", async () => {
    const { client, fetchImpl, sleep } = makeClient([
      jsonResponse({ message: "rate limited" }, 429),
      jsonResponse([], 200),
    ]);
    const res = await client.fetchOdds(odds);

    expect(res.attempts).toBe(2);
    expect(fetchImpl).toHaveBeenCalledTimes(2);
    expect(sleep).toHaveBeenCalledTimes(1);
  });

  it("gives up after maxAttempts on persistent 5xx", async () => {
    const { client, fetchImpl } = makeClient([
      jsonResponse({}, 503),
      jsonResponse({}, 502),
      jsonResponse({}, 500),
    ]);
    const err = await captureError(client.fetchOdds(odds));

    expect(err.code).toBe("UPSTREAM_5XX");
    expect(err.httpStatus).toBe(500);
    expect(fetchImpl).toHaveBeenCalledTimes(3);
  });

  it("classifies thrown fetch errors as retryable network errors without the URL", async () => {
    const { client } = makeClient([
      new TypeError(`fetch failed for https://api.the-odds-api.com/?apiKey=${API_KEY}`),
      new TypeError("fetch failed"),
      new TypeError("fetch failed"),
    ]);
    const err = await captureError(client.fetchOdds(odds));

    expect(err.code).toBe("NETWORK");
    expect(err.message).not.toContain(API_KEY);
  });

  it("does not retry 4xx client errors", async () => {
    const { client, fetchImpl } = makeClient([jsonResponse({ message: "Invalid market" }, 422)]);
    const err = await captureError(client.fetchOdds(odds));

    expect(err.code).toBe("BAD_REQUEST");
    expect(err.message).toContain("Invalid market");
    expect(fetchImpl).toHaveBeenCalledTimes(1);
  });

  it("validates the /events response shape", async () => {
    const { client } = makeClient([jsonResponse([{ id: 123 }])]);
    const err = await captureError(client.fetchEvents("americanfootball_nfl"));
    expect(err.code).toBe("VALIDATION");
  });
});
