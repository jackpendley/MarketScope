/**
 * True when a state-changing request (POST and friends) comes from this site. Browsers always
 * send Origin on cross-origin and on same-origin POSTs; a missing or foreign Origin is refused.
 * Better Auth checks origins only for some endpoints (not the username sign-in), so the proxy
 * applies this to every /api/auth/* mutation (login CSRF, ADR-049).
 */
export function isSameOriginMutation(
  method: string,
  origin: string | null,
  host: string | null,
): boolean {
  if (["GET", "HEAD", "OPTIONS"].includes(method.toUpperCase())) return true;
  if (!origin || !host || origin === "null") return false;
  try {
    return new URL(origin).host === host;
  } catch {
    return false;
  }
}
