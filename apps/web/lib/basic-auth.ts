// HTTP Basic authentication for keeping the deployed site private (ADR-022).
// Pure and dependency-free so it can be unit-tested and run inside proxy.ts.
import { createHash, timingSafeEqual } from "node:crypto";

export interface BasicAuthConfig {
  user: string;
  password: string;
}

/** Compare via fixed-length digests so neither content nor length leaks through timing. */
function safeEqual(a: string, b: string): boolean {
  const da = createHash("sha256").update(a).digest();
  const db = createHash("sha256").update(b).digest();
  return timingSafeEqual(da, db);
}

/** True when the Authorization header carries the configured credentials. */
export function isAuthorized(authorization: string | null, config: BasicAuthConfig): boolean {
  if (!authorization?.startsWith("Basic ")) return false;
  let decoded: string;
  try {
    decoded = Buffer.from(authorization.slice(6).trim(), "base64").toString("utf8");
  } catch {
    return false;
  }
  const separator = decoded.indexOf(":");
  if (separator < 0) return false;
  const user = decoded.slice(0, separator);
  const password = decoded.slice(separator + 1);
  // Evaluate both comparisons (no short-circuit) to keep timing uniform.
  const userOk = safeEqual(user, config.user);
  const passwordOk = safeEqual(password, config.password);
  return userOk && passwordOk;
}

/** Auth is enforced only when a password is configured (production); local dev and e2e run open. */
export function basicAuthConfigFromEnv(
  env: Readonly<Record<string, string | undefined>>,
): BasicAuthConfig | null {
  const password = env.BASIC_AUTH_PASSWORD;
  if (!password) return null;
  return { user: env.BASIC_AUTH_USER || "marketscope", password };
}
