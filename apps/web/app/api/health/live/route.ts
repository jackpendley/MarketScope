/**
 * GET /api/health/live — liveness only: the server process is up. Deliberately does not
 * touch the database (that's /api/health/data), so it's safe for process supervisors and
 * test runners that start the app before its dependencies are ready.
 */
export function GET() {
  return Response.json({ status: "ok" });
}

export const dynamic = "force-dynamic";
