CREATE TABLE "nfl_games" (
	"game_id" text PRIMARY KEY NOT NULL,
	"season" integer NOT NULL,
	"game_type" text NOT NULL,
	"week" integer NOT NULL,
	"kickoff_utc" timestamp with time zone NOT NULL,
	"home_team" text NOT NULL,
	"away_team" text NOT NULL,
	"neutral_site" boolean NOT NULL,
	"division_game" boolean NOT NULL,
	"home_rest_days" integer,
	"away_rest_days" integer,
	"home_score" integer,
	"away_score" integer,
	"overtime" boolean,
	"final_observed_at" timestamp with time zone,
	"stadium_id" text,
	"stadium" text,
	"roof" text,
	"surface" text,
	"observed_temp_f" integer,
	"observed_wind_mph" integer,
	"referee" text,
	"home_coach" text,
	"away_coach" text,
	"home_qb_id" text,
	"away_qb_id" text,
	"nflverse_close_home_spread" numeric(4, 1),
	"nflverse_close_total" numeric(4, 1),
	"nflverse_close_home_moneyline" integer,
	"nflverse_close_away_moneyline" integer,
	"event_id" uuid,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL,
	CONSTRAINT "nfl_games_eventId_unique" UNIQUE("event_id"),
	CONSTRAINT "nfl_games_teams_differ" CHECK ("nfl_games"."home_team" <> "nfl_games"."away_team"),
	CONSTRAINT "nfl_games_scores_together" CHECK (("nfl_games"."home_score" IS NULL) = ("nfl_games"."away_score" IS NULL))
);
--> statement-breakpoint
ALTER TABLE "nfl_games" ENABLE ROW LEVEL SECURITY;--> statement-breakpoint
CREATE TABLE "nfl_ingest_runs" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"job_key" text NOT NULL,
	"dataset" text NOT NULL,
	"started_at" timestamp with time zone DEFAULT now() NOT NULL,
	"finished_at" timestamp with time zone,
	"status" "ingestion_status" DEFAULT 'started' NOT NULL,
	"attempt" integer DEFAULT 1 NOT NULL,
	"rows_upserted" integer DEFAULT 0 NOT NULL,
	"source_version" text,
	"error_message" text,
	CONSTRAINT "nfl_ingest_runs_jobKey_unique" UNIQUE("job_key")
);
--> statement-breakpoint
ALTER TABLE "nfl_ingest_runs" ENABLE ROW LEVEL SECURITY;--> statement-breakpoint
CREATE TABLE "nfl_teams" (
	"abbr" text PRIMARY KEY NOT NULL,
	"franchise" text NOT NULL,
	"full_name" text NOT NULL,
	"nickname" text NOT NULL,
	"conference" text NOT NULL,
	"division" text NOT NULL,
	"odds_api_name" text
);
--> statement-breakpoint
ALTER TABLE "nfl_teams" ENABLE ROW LEVEL SECURITY;--> statement-breakpoint
ALTER TABLE "nfl_games" ADD CONSTRAINT "nfl_games_home_team_nfl_teams_abbr_fk" FOREIGN KEY ("home_team") REFERENCES "public"."nfl_teams"("abbr") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "nfl_games" ADD CONSTRAINT "nfl_games_away_team_nfl_teams_abbr_fk" FOREIGN KEY ("away_team") REFERENCES "public"."nfl_teams"("abbr") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "nfl_games" ADD CONSTRAINT "nfl_games_event_id_events_id_fk" FOREIGN KEY ("event_id") REFERENCES "public"."events"("id") ON DELETE set null ON UPDATE no action;--> statement-breakpoint
CREATE INDEX "nfl_games_season_week_idx" ON "nfl_games" USING btree ("season","week");--> statement-breakpoint
CREATE INDEX "nfl_games_kickoff_idx" ON "nfl_games" USING btree ("kickoff_utc");--> statement-breakpoint
CREATE INDEX "nfl_ingest_runs_started_at_idx" ON "nfl_ingest_runs" USING btree ("started_at" DESC NULLS FIRST);