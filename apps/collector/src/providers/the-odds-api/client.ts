// HTTP client for The Odds API v4. Server-side only: the API key travels in the
// query string, so request URLs are never logged, thrown, or persisted.

import {
  eventSchema,
  sportSchema,
  type ProviderEvent,
  type ProviderSport,
} from "@marketscope/shared";
import { z } from "zod";

export interface ProviderUsage {
  /** Credits left in the current billing period (x-requests-remaining). */
  requestsRemaining: number | null;
  /** Credits used in the current billing period (x-requests-used). */
  requestsUsed: number | null;
  /** Credits this request cost (x-requests-last). */
  requestsLast: number | null;
}

export interface ProviderResponse<T> {
  data: T;
  usage: ProviderUsage;
  httpStatus: number;
  durationMs: number;
  /** When the final (successful) response arrived. ISO 8601. */
  receivedAt: string;
  attempts: number;
}

export type ProviderErrorCode =
  | "AUTH"
  | "RATE_LIMIT"
  | "BAD_REQUEST"
  | "UPSTREAM_5XX"
  | "NETWORK"
  | "VALIDATION"
  | "UNEXPECTED_STATUS";

export class ProviderError extends Error {
  override name = "ProviderError";
  constructor(
    readonly code: ProviderErrorCode,
    message: string,
    readonly httpStatus: number | null,
    readonly retryable: boolean,
    readonly usage: ProviderUsage | null = null,
  ) {
    super(message);
  }
}

export interface ClientOptions {
  apiKey: string;
  baseUrl?: string;
  timeoutMs?: number;
  maxAttempts?: number;
  /** Injected for tests. */
  fetchImpl?: typeof fetch;
  sleep?: (ms: number) => Promise<void>;
  baseBackoffMs?: number;
}

export interface FetchOddsParams {
  sportKey: string;
  bookmakers: readonly string[];
  markets: readonly string[];
}

export function createTheOddsApiClient(options: ClientOptions) {
  const {
    apiKey,
    baseUrl = "https://api.the-odds-api.com",
    timeoutMs = 15_000,
    maxAttempts = 3,
    fetchImpl = fetch,
    sleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms)),
    baseBackoffMs = 1_000,
  } = options;

  async function request(
    path: string,
    params: Record<string, string>,
  ): Promise<ProviderResponse<unknown>> {
    const url = new URL(path, baseUrl);
    for (const [k, v] of Object.entries(params)) url.searchParams.set(k, v);
    url.searchParams.set("apiKey", apiKey);
    // Safe description for errors/logs: path only, no query string.
    const label = `GET ${path}`;

    let lastError: ProviderError | undefined;
    for (let attempt = 1; attempt <= maxAttempts; attempt++) {
      const started = performance.now();
      try {
        const res = await fetchImpl(url, { signal: AbortSignal.timeout(timeoutMs) });
        const usage = parseUsageHeaders(res.headers);
        const durationMs = Math.round(performance.now() - started);

        if (res.ok) {
          let data: unknown;
          try {
            data = await res.json();
          } catch {
            throw new ProviderError(
              "VALIDATION",
              `${label}: response body is not JSON`,
              res.status,
              false,
              usage,
            );
          }
          return {
            data,
            usage,
            httpStatus: res.status,
            durationMs,
            receivedAt: new Date().toISOString(),
            attempts: attempt,
          };
        }

        const detail = redact(await safeErrorMessage(res), apiKey);
        lastError = classifyHttpError(
          res.status,
          `${label} failed: HTTP ${res.status}${detail ? ` (${detail})` : ""}`,
          usage,
        );
      } catch (err) {
        if (err instanceof ProviderError) throw err;
        const reason =
          err instanceof Error && err.name === "TimeoutError"
            ? `timed out after ${timeoutMs}ms`
            : "network error";
        lastError = new ProviderError("NETWORK", `${label} failed: ${reason}`, null, true);
      }

      if (!lastError.retryable || attempt === maxAttempts) break;
      // Exponential backoff with jitter: ~1s, ~2s, ~4s...
      await sleep(baseBackoffMs * 2 ** (attempt - 1) + Math.random() * 250);
    }
    throw lastError!;
  }

  function validate<T>(
    schema: z.ZodType<T>,
    response: ProviderResponse<unknown>,
    label: string,
  ): ProviderResponse<T> {
    const parsed = schema.safeParse(response.data);
    if (!parsed.success) {
      throw new ProviderError(
        "VALIDATION",
        `${label}: unexpected response shape: ${z.prettifyError(parsed.error)}`,
        response.httpStatus,
        false,
        response.usage,
      );
    }
    return { ...response, data: parsed.data };
  }

  return {
    /** Free: does not count against quota. */
    async fetchSports(): Promise<ProviderResponse<ProviderSport[]>> {
      return validate(z.array(sportSchema), await request("/v4/sports/", {}), "GET /v4/sports");
    },

    /** Free: does not count against quota. */
    async fetchEvents(sportKey: string): Promise<ProviderResponse<ProviderEvent[]>> {
      const path = `/v4/sports/${sportKey}/events/`;
      return validate(
        z.array(eventSchema),
        await request(path, { dateFormat: "iso" }),
        `GET ${path}`,
      );
    },

    /**
     * Costs credits: markets × ceil(bookmakers / 10). Returns the raw payload;
     * callers parse it with parseOddsResponse() so one bad event can't sink the batch.
     */
    async fetchOdds({
      sportKey,
      bookmakers,
      markets,
    }: FetchOddsParams): Promise<ProviderResponse<unknown>> {
      return request(`/v4/sports/${sportKey}/odds/`, {
        bookmakers: bookmakers.join(","),
        markets: markets.join(","),
        oddsFormat: "american",
        dateFormat: "iso",
      });
    },
  };
}

export type TheOddsApiClient = ReturnType<typeof createTheOddsApiClient>;

export function parseUsageHeaders(headers: Headers): ProviderUsage {
  const num = (name: string) => {
    const raw = headers.get(name);
    if (raw === null || raw.trim() === "") return null;
    const n = Number(raw);
    return Number.isFinite(n) ? n : null;
  };
  return {
    requestsRemaining: num("x-requests-remaining"),
    requestsUsed: num("x-requests-used"),
    requestsLast: num("x-requests-last"),
  };
}

/** Credit cost of an /odds request per provider docs (verified 2026-10-15). */
export function estimateOddsCost(
  markets: readonly string[],
  bookmakers: readonly string[],
): number {
  return markets.length * Math.max(1, Math.ceil(bookmakers.length / 10));
}

function classifyHttpError(status: number, message: string, usage: ProviderUsage): ProviderError {
  if (status === 401 || status === 403)
    return new ProviderError("AUTH", message, status, false, usage);
  if (status === 429) return new ProviderError("RATE_LIMIT", message, status, true, usage);
  if (status >= 500) return new ProviderError("UPSTREAM_5XX", message, status, true, usage);
  if (status >= 400) return new ProviderError("BAD_REQUEST", message, status, false, usage);
  return new ProviderError("UNEXPECTED_STATUS", message, status, false, usage);
}

async function safeErrorMessage(res: Response): Promise<string> {
  try {
    const body: unknown = await res.json();
    if (
      typeof body === "object" &&
      body !== null &&
      "message" in body &&
      typeof body.message === "string"
    ) {
      return body.message.slice(0, 200);
    }
  } catch {
    // Non-JSON error body: report status only.
  }
  return "";
}

function redact(text: string, secret: string): string {
  return secret ? text.split(secret).join("[REDACTED]") : text;
}
