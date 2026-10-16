import "server-only";
import { z } from "zod";
import { DatabaseNotConfiguredError } from "./db";

// Every API response uses one of two envelopes:
//   success: { data, meta }            error: { error: { code, message, details? } }

export type ApiErrorCode =
  "INVALID_PARAMETERS" | "NOT_FOUND" | "DATA_SOURCE_UNAVAILABLE" | "INTERNAL_ERROR";

export function ok<T>(data: T, meta: Record<string, unknown> = {}): Response {
  return Response.json({ data, meta: { generatedAt: new Date().toISOString(), ...meta } });
}

export function apiError(
  status: number,
  code: ApiErrorCode,
  message: string,
  details?: unknown,
): Response {
  return Response.json(
    { error: { code, message, ...(details === undefined ? {} : { details }) } },
    { status },
  );
}

export function invalidParams(error: z.ZodError): Response {
  return apiError(
    400,
    "INVALID_PARAMETERS",
    "One or more query parameters are invalid.",
    error.issues.map((i) => ({ path: i.path.join("."), message: i.message })),
  );
}

/** Map unexpected failures to safe responses: no stack traces, SQL, or connection strings. */
export function handleUnexpected(err: unknown, route: string): Response {
  if (err instanceof DatabaseNotConfiguredError || isConnectionError(err)) {
    console.error(JSON.stringify({ level: "error", event: "api.data_source_unavailable", route }));
    return apiError(
      503,
      "DATA_SOURCE_UNAVAILABLE",
      "The odds database is temporarily unavailable.",
    );
  }
  console.error(
    JSON.stringify({
      level: "error",
      event: "api.unexpected",
      route,
      message: err instanceof Error ? err.message.slice(0, 300) : String(err),
    }),
  );
  return apiError(500, "INTERNAL_ERROR", "Unexpected server error.");
}

export function isConnectionError(err: unknown): boolean {
  const codes = new Set([
    "ECONNREFUSED",
    "ENOTFOUND",
    "ETIMEDOUT",
    "CONNECTION_CLOSED",
    "CONNECT_TIMEOUT",
    "57P01",
    "3D000",
  ]);
  let current: unknown = err;
  for (let depth = 0; current && depth < 4; depth++) {
    const code = (current as { code?: string }).code;
    if (code && codes.has(code)) return true;
    current = (current as { cause?: unknown }).cause;
  }
  return false;
}

/** Search params → plain object (repeated keys keep the last value). */
export function searchParamsObject(url: string): Record<string, string> {
  return Object.fromEntries(new URL(url).searchParams.entries());
}
