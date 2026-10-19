/**
 * Where to go after signing in. Only same-site paths are allowed, so a crafted
 * `/login?next=https://evil.example` link can't send someone off-site (open redirect).
 */
export function safeNext(next: string | string[] | undefined | null, fallback = "/nfl"): string {
  const value = Array.isArray(next) ? next[0] : next;
  if (!value || !value.startsWith("/") || value.startsWith("//") || value.startsWith("/\\"))
    return fallback;
  if (value.startsWith("/login") || value.startsWith("/api/")) return fallback;
  return value;
}
