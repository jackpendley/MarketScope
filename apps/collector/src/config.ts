import { z } from "zod";

// Empty strings in .env files ("ODDS_API_KEY=") mean "not set".
const optionalString = z.preprocess(
  (v) => (v === "" ? undefined : v),
  z.string().min(1).optional(),
);

const envSchema = z.object({
  ODDS_API_KEY: optionalString,
  ODDS_API_BASE_URL: z
    .preprocess((v) => (v === "" ? undefined : v), z.url().optional())
    .default("https://api.the-odds-api.com"),
  DATABASE_URL: optionalString,
  MONTHLY_CREDIT_BUDGET: z.coerce.number().int().nonnegative().default(400),
  MAX_CREDITS_PER_RUN: z.coerce.number().int().positive().default(3),
  MIN_CREDITS_REMAINING: z.coerce.number().int().nonnegative().default(25),
  HTTP_TIMEOUT_MS: z.coerce.number().int().positive().default(15_000),
  /** Scheduled runs share one job key per slot; 360 min = 4 slots per day. */
  COLLECT_SLOT_MINUTES: z.coerce.number().int().positive().default(360),
});

export type CollectorConfig = z.infer<typeof envSchema>;

export class ConfigError extends Error {
  override name = "ConfigError";
}

export function loadConfig(env: NodeJS.ProcessEnv = process.env): CollectorConfig {
  const parsed = envSchema.safeParse(env);
  if (!parsed.success) {
    // Report which variables are wrong, never their values.
    const fields = parsed.error.issues.map((i) => i.path.join(".")).join(", ");
    throw new ConfigError(`Invalid collector configuration: ${fields}`);
  }
  return parsed.data;
}

export function requireOddsApiKey(config: CollectorConfig): string {
  if (!config.ODDS_API_KEY) {
    throw new ConfigError(
      [
        "ODDS_API_KEY is not set.",
        "  1. cp apps/collector/.env.example apps/collector/.env.local",
        "  2. Open apps/collector/.env.local in your editor and set ODDS_API_KEY",
        "     (never paste the key into chat or commit it).",
      ].join("\n"),
    );
  }
  return config.ODDS_API_KEY;
}

export function requireDatabaseUrl(config: CollectorConfig): string {
  if (!config.DATABASE_URL) {
    throw new ConfigError(
      "DATABASE_URL is not set. Add it to apps/collector/.env.local " +
        "(local dev: postgres://localhost:5432/marketscope_dev).",
    );
  }
  return config.DATABASE_URL;
}
