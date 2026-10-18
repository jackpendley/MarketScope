// Minimal OddsPapi v4 client for historical imports. Server-side only: the key travels in
// the query string, so request URLs are never logged or thrown.
//
// Quota (verified 2026-10-17): /v4/historical-odds and /v4/account are free; fixtures,
// markets, bookmakers, sports, etc. count against the plan's monthly request allowance.
// Each endpoint has its own cooldown; we wait it out client-side.

import type { OddsPapiHistory, OddsPapiMarketMeta } from "./transform";

export const ODDSPAPI_NFL_TOURNAMENT_ID = 31;

const COOLDOWN_MS: Record<string, number> = {
  "/v4/historical-odds": 5_000,
  "/v4/fixtures": 2_000,
  "/v4/markets": 1_000,
  "/v4/account": 0,
};

export interface OddsPapiFixture {
  fixtureId: string;
  participant1Name: string;
  participant2Name: string;
  startTime: string;
  statusId: number;
}

export interface OddsPapiAccount {
  requestLimit: number | null;
  requestCount: number | null;
}

export class OddsPapiError extends Error {
  override name = "OddsPapiError";
  constructor(
    message: string,
    readonly status: number | null,
  ) {
    super(message);
  }
}

export interface OddsPapiClientOptions {
  apiKey: string;
  baseUrl?: string;
  fetchImpl?: typeof fetch;
  sleep?: (ms: number) => Promise<void>;
  now?: () => number;
  timeoutMs?: number;
}

export function createOddsPapiClient(options: OddsPapiClientOptions) {
  const {
    apiKey,
    baseUrl = "https://api.oddspapi.io",
    fetchImpl = fetch,
    sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms)),
    now = () => Date.now(),
    timeoutMs = 120_000,
  } = options;
  const lastCall = new Map<string, number>();

  async function request<T>(path: string, params: Record<string, string | number>): Promise<T> {
    for (let attempt = 1; attempt <= 3; attempt++) {
      const wait = (lastCall.get(path) ?? -Infinity) + (COOLDOWN_MS[path] ?? 1_000) - now();
      if (wait > 0) await sleep(wait);
      lastCall.set(path, now());

      const url = new URL(path, baseUrl);
      for (const [k, v] of Object.entries(params)) url.searchParams.set(k, String(v));
      url.searchParams.set("apiKey", apiKey);
      let res: Response;
      try {
        res = await fetchImpl(url, { signal: AbortSignal.timeout(timeoutMs) });
      } catch {
        if (attempt === 3) throw new OddsPapiError(`GET ${path} failed: network error`, null);
        continue;
      }
      if (res.ok) return (await res.json()) as T;
      // 429 can mean a cooldown hit (retry) or an exhausted quota (stop).
      const body = (await res.text()).split(apiKey).join("[REDACTED]").slice(0, 200);
      if (res.status === 429 && !body.includes("REQUEST_LIMIT_EXCEEDED") && attempt < 3) {
        await sleep((COOLDOWN_MS[path] ?? 1_000) * 2);
        continue;
      }
      throw new OddsPapiError(`GET ${path} failed: HTTP ${res.status} ${body}`, res.status);
    }
    throw new OddsPapiError(`GET ${path} failed after retries`, null);
  }

  return {
    /** Free. Monthly allowance and usage for the current plan. */
    async account(): Promise<OddsPapiAccount> {
      const a = await request<{
        subscriptions?: { request_limit?: number; request_count?: number }[];
      }>("/v4/account", {});
      const sub = a.subscriptions?.[0];
      return { requestLimit: sub?.request_limit ?? null, requestCount: sub?.request_count ?? null };
    },
    /** Billable (1 request). */
    fixtures(params: { tournamentId: number; statusId?: number; from: string; to: string }) {
      return request<OddsPapiFixture[]>("/v4/fixtures", params);
    },
    /** Billable (1 request). The full market catalog (all sports). */
    markets() {
      return request<OddsPapiMarketMeta[]>("/v4/markets", {});
    },
    /** Free. Full line-move history for up to 3 bookmakers of one fixture. */
    historicalOdds(fixtureId: string, bookmakers: readonly string[]) {
      if (bookmakers.length > 3)
        throw new RangeError("OddsPapi allows at most 3 bookmakers per call");
      return request<OddsPapiHistory>("/v4/historical-odds", {
        fixtureId,
        bookmakers: bookmakers.join(","),
      });
    },
  };
}

export type OddsPapiClient = ReturnType<typeof createOddsPapiClient>;
