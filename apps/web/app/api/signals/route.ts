import type { NextRequest } from "next/server";
import { listSignals } from "@marketscope/db";
import { SIGNAL_DEFINITIONS } from "@marketscope/shared";
import { signalsQuerySchema } from "@/lib/params";
import { handleUnexpected, invalidParams, ok, searchParamsObject } from "@/lib/server/api";
import { getDb } from "@/lib/server/db";

/**
 * GET /api/signals?type&from&to&event&limit
 *
 * Versioned signal detections with their evidence observation ids, newest first.
 * Signals describe observable market behavior; they are not betting recommendations.
 */
export async function GET(request: NextRequest) {
  const parsed = signalsQuerySchema(new Date()).safeParse(searchParamsObject(request.url));
  if (!parsed.success) return invalidParams(parsed.error);
  const { type, from, to, event, limit } = parsed.data;
  try {
    const rows = await listSignals(getDb(), { types: type, from, to, eventId: event, limit });
    return ok(rows, {
      count: rows.length,
      from,
      to: to ?? null,
      limit,
      definitions: SIGNAL_DEFINITIONS,
      disclaimer: "Signals describe observed market behavior only. They are not betting advice.",
    });
  } catch (err) {
    return handleUnexpected(err, "GET /api/signals");
  }
}
