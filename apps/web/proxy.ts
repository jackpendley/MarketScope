import { NextResponse, type NextRequest } from "next/server";
import { basicAuthConfigFromEnv, isAuthorized } from "@/lib/basic-auth";

/**
 * Keeps the deployed site private (ADR-022): every page and API route requires HTTP Basic
 * credentials when BASIC_AUTH_PASSWORD is set. The Odds API terms allow displaying data in
 * a UI but not serving it as a raw-data API to others, so /api/* is protected too.
 */
export function proxy(request: NextRequest) {
  const config = basicAuthConfigFromEnv(process.env);
  if (!config || isAuthorized(request.headers.get("authorization"), config)) {
    return NextResponse.next();
  }
  return new NextResponse("Authentication required.", {
    status: 401,
    headers: { "WWW-Authenticate": 'Basic realm="MarketScope", charset="UTF-8"' },
  });
}

export const config = {
  // Everything except static assets and the dependency-free liveness check.
  matcher: ["/((?!_next/static|_next/image|favicon.ico|api/health/live).*)"],
};
