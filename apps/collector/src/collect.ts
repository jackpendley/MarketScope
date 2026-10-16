// Persistent NFL odds collection (MS-005).
//
// Flow — each step is safe to retry:
//   1. CLAIM the run by job_key (idempotency): a completed key never re-runs; a failed,
//      skipped, or stale (crashed) key is reclaimed with attempt + 1.
//   2. BUDGET GUARD before any paid request: monthly spend, per-run cap, remaining floor.
//   3. FETCH from the provider with NO database transaction open (HTTP can be slow).
//   4. NORMALIZE (pure) and then persist everything in ONE TRANSACTION:
//      bookmakers + events upsert, raw payload, observations, run → completed.
//      Either all of it lands or none of it does.
//   5. On any failure: mark the run failed in a separate statement, keeping the
//      provider's credit headers (credits are spent even if persistence fails).

import {
  bookmakers,
  events,
  ingestionPayloads,
  ingestionRuns,
  oddsObservations,
  type Database,
} from "@marketscope/db";
import {
  BOARD_BOOKS,
  COLLECTED_BOOKMAKERS,
  COLLECTED_BOOKMAKER_KEYS,
  MARKETS,
  nflSeasonForKickoff,
  normalizeEventOdds,
  parseOddsResponse,
  type NormalizedEventOdds,
} from "@marketscope/shared";
import { and, desc, eq, gte, inArray, isNotNull, lt, or, sql } from "drizzle-orm";
import type { CollectorConfig } from "./config";
import { silentLogger, type Logger } from "./log";
import {
  estimateOddsCost,
  ProviderError,
  type ProviderResponse,
  type ProviderUsage,
  type TheOddsApiClient,
} from "./providers/the-odds-api/client";

export const PROVIDER = "the-odds-api";
export const NFL_SPORT_KEY = "americanfootball_nfl";
/** A run still marked "started" after this long is assumed to have crashed. */
export const STALE_CLAIM_MINUTES = 15;
const INSERT_CHUNK_SIZE = 1_000;

export interface CollectDeps {
  db: Database;
  client: Pick<TheOddsApiClient, "fetchOdds">;
  config: Pick<
    CollectorConfig,
    "MONTHLY_CREDIT_BUDGET" | "MAX_CREDITS_PER_RUN" | "MIN_CREDITS_REMAINING"
  >;
  log?: Logger;
}

export type CollectOutcome =
  | {
      status: "completed";
      runId: string;
      attempt: number;
      eventsSeen: number;
      quotesInserted: number;
      creditsUsed: number | null;
      creditsRemaining: number | null;
      issueCounts: Record<string, number>;
    }
  | { status: "already-completed"; runId: string }
  | { status: "in-progress"; runId: string }
  | { status: "skipped"; runId: string; reason: string }
  | { status: "failed"; runId: string; errorCode: string; errorMessage: string };

/** Deterministic job key for a scheduled slot, e.g. live:nfl:2026-10-16T06:00:00.000Z. */
export function scheduledJobKey(now: Date, slotMinutes: number): string {
  const slotMs = slotMinutes * 60_000;
  return `live:nfl:${new Date(Math.floor(now.getTime() / slotMs) * slotMs).toISOString()}`;
}

export function manualJobKey(): string {
  return `manual:${crypto.randomUUID()}`;
}

export async function collectNflOdds(
  deps: CollectDeps,
  { jobKey }: { jobKey: string },
): Promise<CollectOutcome> {
  const { db, client, config } = deps;
  const log = deps.log ?? silentLogger;

  // 1. Claim
  const claim = await claimRun(db, jobKey);
  if (claim.kind !== "claimed") {
    log.info("collect.not_claimed", { jobKey, status: claim.kind, runId: claim.runId });
    return { status: claim.kind, runId: claim.runId };
  }
  const { runId, attempt } = claim;
  log.info("collect.claimed", { jobKey, runId, attempt });

  // 2. Budget guard (no credits spent if it trips)
  const cost = estimateOddsCost(MARKETS, COLLECTED_BOOKMAKER_KEYS);
  const refusal = await checkBudget(db, cost, config);
  if (refusal) {
    await db
      .update(ingestionRuns)
      .set({
        status: "skipped",
        finishedAt: sql`now()`,
        errorCode: "BUDGET",
        errorMessage: refusal,
      })
      .where(eq(ingestionRuns.id, runId));
    log.warn("collect.skipped", { runId, reason: refusal });
    return { status: "skipped", runId, reason: refusal };
  }

  // 3. Fetch (no transaction open)
  let response: ProviderResponse<unknown>;
  try {
    response = await client.fetchOdds({
      sportKey: NFL_SPORT_KEY,
      bookmakers: COLLECTED_BOOKMAKER_KEYS,
      markets: MARKETS,
    });
  } catch (err) {
    return failRun(db, log, runId, err);
  }

  // 4. Normalize, then persist atomically
  try {
    const parsed = parseOddsResponse(response.data);
    const results = parsed.events.map((e) =>
      normalizeEventOdds(e, {
        observedAt: response.receivedAt,
        targetBookmakers: COLLECTED_BOOKMAKER_KEYS,
      }),
    );
    const issueCounts = countIssues(results);
    if (parsed.rejected.length > 0) issueCounts.SCHEMA_REJECTED = parsed.rejected.length;

    const quotesInserted = await db.transaction(async (tx) => {
      await upsertBookmakers(tx);
      const eventIds = await upsertEvents(tx, results, issueCounts);

      await tx.insert(ingestionPayloads).values({
        ingestionRunId: runId,
        receivedAt: response.receivedAt,
        payload: response.data,
      });

      const rows = results.flatMap(({ event, quotes }) => {
        const eventId = eventIds.get(event.providerEventId);
        if (!eventId) return [];
        return quotes.map((q) => ({
          ingestionRunId: runId,
          eventId,
          bookmakerKey: q.bookmakerKey,
          marketType: q.market,
          selection: q.selection,
          point: q.point,
          americanPrice: q.americanPrice,
          bookmakerUpdatedAt: q.bookmakerUpdatedAt,
          observedAt: q.observedAt,
          isLive: q.isLive,
          source: PROVIDER,
        }));
      });
      for (let i = 0; i < rows.length; i += INSERT_CHUNK_SIZE) {
        await tx.insert(oddsObservations).values(rows.slice(i, i + INSERT_CHUNK_SIZE));
      }

      await tx
        .update(ingestionRuns)
        .set({
          status: "completed",
          finishedAt: sql`now()`,
          httpStatus: response.httpStatus,
          durationMs: response.durationMs,
          ...creditFields(response.usage),
          eventsSeen: results.length,
          quotesSeen: rows.length,
          issueCounts,
        })
        .where(eq(ingestionRuns.id, runId));
      return rows.length;
    });

    const outcome: CollectOutcome = {
      status: "completed",
      runId,
      attempt,
      eventsSeen: results.length,
      quotesInserted,
      creditsUsed: response.usage.requestsLast,
      creditsRemaining: response.usage.requestsRemaining,
      issueCounts,
    };
    log.info("collect.completed", { ...outcome });
    return outcome;
  } catch (err) {
    return failRun(db, log, runId, err, response);
  }
}

type Claim =
  | { kind: "claimed"; runId: string; attempt: number }
  | { kind: "already-completed" | "in-progress"; runId: string };

async function claimRun(db: Database, jobKey: string): Promise<Claim> {
  const [inserted] = await db
    .insert(ingestionRuns)
    .values({ jobKey, provider: PROVIDER, requestType: "live" })
    .onConflictDoNothing({ target: ingestionRuns.jobKey })
    .returning({ id: ingestionRuns.id, attempt: ingestionRuns.attempt });
  if (inserted) return { kind: "claimed", runId: inserted.id, attempt: inserted.attempt };

  // The key exists. Reclaim it only if it failed, was skipped, or looks crashed. The
  // conditional UPDATE is atomic: if two workers race, only one matches the WHERE.
  const [reclaimed] = await db
    .update(ingestionRuns)
    .set({
      status: "started",
      attempt: sql`${ingestionRuns.attempt} + 1`,
      startedAt: sql`now()`,
      finishedAt: null,
      errorCode: null,
      errorMessage: null,
      httpStatus: null,
      durationMs: null,
    })
    .where(
      and(
        eq(ingestionRuns.jobKey, jobKey),
        or(
          inArray(ingestionRuns.status, ["failed", "skipped"]),
          and(
            eq(ingestionRuns.status, "started"),
            lt(ingestionRuns.startedAt, sql`now() - make_interval(mins => ${STALE_CLAIM_MINUTES})`),
          ),
        ),
      ),
    )
    .returning({ id: ingestionRuns.id, attempt: ingestionRuns.attempt });
  if (reclaimed) return { kind: "claimed", runId: reclaimed.id, attempt: reclaimed.attempt };

  const [existing] = await db
    .select({ id: ingestionRuns.id, status: ingestionRuns.status })
    .from(ingestionRuns)
    .where(eq(ingestionRuns.jobKey, jobKey));
  return {
    kind: existing!.status === "completed" ? "already-completed" : "in-progress",
    runId: existing!.id,
  };
}

async function checkBudget(
  db: Database,
  cost: number,
  config: CollectDeps["config"],
): Promise<string | null> {
  if (cost > config.MAX_CREDITS_PER_RUN) {
    return `estimated cost ${cost} exceeds MAX_CREDITS_PER_RUN=${config.MAX_CREDITS_PER_RUN}`;
  }

  // Calendar month in UTC. The provider's billing cycle may not align with it, which is
  // why the remaining-credits floor below uses the provider's own number.
  const [spent] = await db
    .select({ credits: sql<number>`coalesce(sum(${ingestionRuns.creditsUsed}), 0)::int` })
    .from(ingestionRuns)
    .where(
      and(
        eq(ingestionRuns.provider, PROVIDER),
        gte(
          ingestionRuns.startedAt,
          sql`date_trunc('month', now() at time zone 'UTC') at time zone 'UTC'`,
        ),
      ),
    );
  if (spent!.credits + cost > config.MONTHLY_CREDIT_BUDGET) {
    return `monthly budget: ${spent!.credits} spent + ${cost} would exceed MONTHLY_CREDIT_BUDGET=${config.MONTHLY_CREDIT_BUDGET}`;
  }

  const [latest] = await db
    .select({ remaining: ingestionRuns.creditsRemaining })
    .from(ingestionRuns)
    .where(and(eq(ingestionRuns.provider, PROVIDER), isNotNull(ingestionRuns.creditsRemaining)))
    .orderBy(desc(ingestionRuns.startedAt))
    .limit(1);
  if (latest?.remaining != null && latest.remaining - cost < config.MIN_CREDITS_REMAINING) {
    return `only ${latest.remaining} credits remain; would go below MIN_CREDITS_REMAINING=${config.MIN_CREDITS_REMAINING}`;
  }
  return null;
}

type Tx = Parameters<Parameters<Database["transaction"]>[0]>[0];

async function upsertBookmakers(tx: Tx): Promise<void> {
  const primaryFeeds = new Set(BOARD_BOOKS.map((b) => b.feeds[0]));
  await tx
    .insert(bookmakers)
    .values(
      COLLECTED_BOOKMAKERS.map((b) => ({
        key: b.key,
        displayName: b.displayName,
        regionHint: b.regionHint,
        isPrimary: primaryFeeds.has(b.key),
      })),
    )
    .onConflictDoUpdate({
      target: bookmakers.key,
      set: {
        displayName: sql`excluded.display_name`,
        regionHint: sql`excluded.region_hint`,
        isPrimary: sql`excluded.is_primary`,
      },
    });
}

/**
 * Upserts events and returns providerEventId → internal id. Kickoff times are updated
 * (flexed games, actual kickoff). Home/away are NEVER rewritten: if the provider ever
 * flips orientation for an existing event, its quotes are dropped and reported, because
 * silently accepting them would invert that game's whole spread history.
 */
async function upsertEvents(
  tx: Tx,
  results: NormalizedEventOdds[],
  issueCounts: Record<string, number>,
): Promise<Map<string, string>> {
  if (results.length === 0) return new Map();

  await tx
    .insert(events)
    .values(
      results.map(({ event }) => ({
        providerEventId: event.providerEventId,
        sportKey: event.sportKey,
        season: nflSeasonForKickoff(event.commenceTime),
        homeTeam: event.homeTeam,
        awayTeam: event.awayTeam,
        commenceTimeUtc: event.commenceTime,
      })),
    )
    .onConflictDoUpdate({
      target: events.providerEventId,
      set: { commenceTimeUtc: sql`excluded.commence_time_utc`, updatedAt: sql`now()` },
      setWhere: sql`${events.commenceTimeUtc} IS DISTINCT FROM excluded.commence_time_utc`,
    });

  const stored = await tx
    .select({
      id: events.id,
      providerEventId: events.providerEventId,
      homeTeam: events.homeTeam,
      awayTeam: events.awayTeam,
    })
    .from(events)
    .where(
      inArray(
        events.providerEventId,
        results.map((r) => r.event.providerEventId),
      ),
    );

  const ids = new Map<string, string>();
  for (const row of stored) {
    const incoming = results.find((r) => r.event.providerEventId === row.providerEventId)!.event;
    if (incoming.homeTeam !== row.homeTeam || incoming.awayTeam !== row.awayTeam) {
      issueCounts.EVENT_TEAMS_CHANGED = (issueCounts.EVENT_TEAMS_CHANGED ?? 0) + 1;
      continue;
    }
    ids.set(row.providerEventId, row.id);
  }
  return ids;
}

function countIssues(results: NormalizedEventOdds[]): Record<string, number> {
  const counts: Record<string, number> = {};
  for (const { issues } of results) {
    for (const issue of issues) counts[issue.code] = (counts[issue.code] ?? 0) + 1;
  }
  return counts;
}

function creditFields(usage: ProviderUsage | null | undefined) {
  return {
    creditsUsed: usage?.requestsLast ?? null,
    creditsRemaining: usage?.requestsRemaining ?? null,
  };
}

async function failRun(
  db: Database,
  log: Logger,
  runId: string,
  err: unknown,
  response?: ProviderResponse<unknown>,
): Promise<CollectOutcome> {
  const errorCode =
    err instanceof ProviderError ? err.code : response ? "PERSISTENCE" : "UNEXPECTED";
  const errorMessage = sanitizeErrorMessage(err);
  const usage = err instanceof ProviderError ? err.usage : response?.usage;
  await db
    .update(ingestionRuns)
    .set({
      status: "failed",
      finishedAt: sql`now()`,
      errorCode,
      errorMessage,
      httpStatus: err instanceof ProviderError ? err.httpStatus : (response?.httpStatus ?? null),
      ...creditFields(usage),
    })
    .where(eq(ingestionRuns.id, runId));
  log.error("collect.failed", { runId, errorCode, errorMessage });
  return { status: "failed", runId, errorCode, errorMessage };
}

/**
 * Keep error messages short and free of query text: Drizzle errors embed the failed SQL
 * and its parameters (which would include the whole payload), so prefer the driver's cause.
 * Provider errors are already sanitized by the client (no URLs, key redacted).
 */
function sanitizeErrorMessage(err: unknown): string {
  if (err instanceof ProviderError) return err.message.slice(0, 500);
  const cause = (err as { cause?: unknown })?.cause;
  const source = cause instanceof Error ? cause : err;
  const message = source instanceof Error ? source.message : String(source);
  return message.slice(0, 500);
}
