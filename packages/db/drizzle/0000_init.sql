CREATE TYPE "public"."ingestion_status" AS ENUM('started', 'completed', 'failed', 'skipped');--> statement-breakpoint
CREATE TYPE "public"."market_type" AS ENUM('h2h', 'spreads', 'totals');--> statement-breakpoint
CREATE TYPE "public"."request_type" AS ENUM('live', 'historical');--> statement-breakpoint
CREATE TYPE "public"."selection" AS ENUM('HOME', 'AWAY', 'OVER', 'UNDER');--> statement-breakpoint
CREATE TABLE "bookmakers" (
	"key" text PRIMARY KEY NOT NULL,
	"display_name" text NOT NULL,
	"region_hint" text,
	"is_primary" boolean DEFAULT false NOT NULL,
	"enabled" boolean DEFAULT true NOT NULL
);
--> statement-breakpoint
CREATE TABLE "events" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"provider_event_id" text NOT NULL,
	"sport_key" text NOT NULL,
	"season" integer NOT NULL,
	"week" integer,
	"home_team" text NOT NULL,
	"away_team" text NOT NULL,
	"commence_time_utc" timestamp with time zone NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL,
	CONSTRAINT "events_providerEventId_unique" UNIQUE("provider_event_id")
);
--> statement-breakpoint
CREATE TABLE "ingestion_payloads" (
	"ingestion_run_id" uuid PRIMARY KEY NOT NULL,
	"received_at" timestamp with time zone NOT NULL,
	"payload" jsonb NOT NULL
);
--> statement-breakpoint
CREATE TABLE "ingestion_runs" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"job_key" text NOT NULL,
	"provider" text NOT NULL,
	"request_type" "request_type" NOT NULL,
	"requested_snapshot_at" timestamp with time zone,
	"provider_snapshot_at" timestamp with time zone,
	"started_at" timestamp with time zone DEFAULT now() NOT NULL,
	"finished_at" timestamp with time zone,
	"status" "ingestion_status" DEFAULT 'started' NOT NULL,
	"attempt" integer DEFAULT 1 NOT NULL,
	"http_status" integer,
	"duration_ms" integer,
	"credits_used" integer,
	"credits_remaining" integer,
	"events_seen" integer DEFAULT 0 NOT NULL,
	"quotes_seen" integer DEFAULT 0 NOT NULL,
	"issue_counts" jsonb,
	"error_code" text,
	"error_message" text,
	CONSTRAINT "ingestion_runs_jobKey_unique" UNIQUE("job_key")
);
--> statement-breakpoint
CREATE TABLE "odds_observations" (
	"id" bigint PRIMARY KEY GENERATED ALWAYS AS IDENTITY (sequence name "odds_observations_id_seq" INCREMENT BY 1 MINVALUE 1 MAXVALUE 9223372036854775807 START WITH 1 CACHE 1),
	"ingestion_run_id" uuid NOT NULL,
	"event_id" uuid NOT NULL,
	"bookmaker_key" text NOT NULL,
	"market_type" "market_type" NOT NULL,
	"selection" "selection" NOT NULL,
	"point" numeric(5, 1),
	"american_price" integer NOT NULL,
	"bookmaker_updated_at" timestamp with time zone,
	"observed_at" timestamp with time zone NOT NULL,
	"is_live" boolean NOT NULL,
	"source" text DEFAULT 'the-odds-api' NOT NULL,
	CONSTRAINT "odds_observations_run_selection_uq" UNIQUE("ingestion_run_id","event_id","bookmaker_key","market_type","selection"),
	CONSTRAINT "odds_observations_point_matches_market" CHECK (("odds_observations"."market_type" = 'h2h') = ("odds_observations"."point" IS NULL)),
	CONSTRAINT "odds_observations_selection_matches_market" CHECK (("odds_observations"."market_type" IN ('h2h', 'spreads') AND "odds_observations"."selection" IN ('HOME', 'AWAY'))
        OR ("odds_observations"."market_type" = 'totals' AND "odds_observations"."selection" IN ('OVER', 'UNDER'))),
	CONSTRAINT "odds_observations_valid_american_price" CHECK ("odds_observations"."american_price" <= -100 OR "odds_observations"."american_price" >= 100)
);
--> statement-breakpoint
ALTER TABLE "ingestion_payloads" ADD CONSTRAINT "ingestion_payloads_ingestion_run_id_ingestion_runs_id_fk" FOREIGN KEY ("ingestion_run_id") REFERENCES "public"."ingestion_runs"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "odds_observations" ADD CONSTRAINT "odds_observations_ingestion_run_id_ingestion_runs_id_fk" FOREIGN KEY ("ingestion_run_id") REFERENCES "public"."ingestion_runs"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "odds_observations" ADD CONSTRAINT "odds_observations_event_id_events_id_fk" FOREIGN KEY ("event_id") REFERENCES "public"."events"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "odds_observations" ADD CONSTRAINT "odds_observations_bookmaker_key_bookmakers_key_fk" FOREIGN KEY ("bookmaker_key") REFERENCES "public"."bookmakers"("key") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
CREATE INDEX "events_commence_time_idx" ON "events" USING btree ("commence_time_utc");--> statement-breakpoint
CREATE INDEX "ingestion_runs_started_at_idx" ON "ingestion_runs" USING btree ("started_at" DESC NULLS LAST);--> statement-breakpoint
CREATE INDEX "odds_observations_history_idx" ON "odds_observations" USING btree ("event_id","market_type","selection","bookmaker_key","observed_at" DESC NULLS LAST);