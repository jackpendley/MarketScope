import { NextResponse, type NextRequest } from "next/server";
import { isSameOriginMutation } from "@/lib/same-origin";
import { authConfigured, getAuth } from "@/lib/server/auth";

/**
 * Every page and API route requires a signed-in account (ADR-049, replacing the shared Basic-auth
 * password of ADR-022). The Odds API terms allow showing data in a UI but not serving it as a
 * raw-data API to others, so /api/* needs a session too. Signed-out page requests go to /login;
 * API requests get a JSON 401.
 */
const PUBLIC = ["/login", "/api/auth/"];

export async function proxy(request: NextRequest) {
  const { pathname, search } = request.nextUrl;
  if (!authConfigured()) return new NextResponse("Site access is not configured.", { status: 503 });
  if (
    pathname.startsWith("/api/auth/") &&
    !isSameOriginMutation(
      request.method,
      request.headers.get("origin"),
      request.headers.get("host"),
    )
  )
    return NextResponse.json(
      { error: { code: "FORBIDDEN", message: "Cross-origin request refused." } },
      { status: 403 },
    );
  if (PUBLIC.some((p) => pathname === p || pathname.startsWith(p))) return NextResponse.next();

  const session = await getAuth().api.getSession({ headers: request.headers });
  if (session) return NextResponse.next();

  if (pathname.startsWith("/api/"))
    return NextResponse.json(
      { error: { code: "UNAUTHENTICATED", message: "Sign in required." } },
      { status: 401 },
    );
  const login = new URL("/login", request.url);
  if (pathname !== "/") login.searchParams.set("next", `${pathname}${search}`);
  return NextResponse.redirect(login);
}

export const config = {
  // Everything except static assets and the dependency-free liveness check.
  matcher: ["/((?!_next/static|_next/image|favicon.ico|api/health/live).*)"],
};
