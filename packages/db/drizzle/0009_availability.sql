CREATE TABLE "nfl_injury_reports" (
	"id" bigint PRIMARY KEY GENERATED ALWAYS AS IDENTITY (sequence name "nfl_injury_reports_id_seq" INCREMENT BY 1 MINVALUE 1 MAXVALUE 9223372036854775807 START WITH 1 CACHE 1),
	"season" integer NOT NULL,
	"week" integer NOT NULL,
	"game_type" text NOT NULL,
	"team" text NOT NULL,
	"game_id" text,
	"gsis_id" text NOT NULL,
	"full_name" text NOT NULL,
	"position" text,
	"report_status" text,
	"report_primary_injury" text,
	"report_secondary_injury" text,
	"practice_status" text,
	"practice_primary_injury" text,
	"content_hash" text NOT NULL,
	"first_seen_at" timestamp with time zone,
	"last_seen_at" timestamp with time zone,
	CONSTRAINT "nfl_injury_reports_live_key" UNIQUE("season","week","team","gsis_id","first_seen_at")
);
--> statement-breakpoint
ALTER TABLE "nfl_injury_reports" ENABLE ROW LEVEL SECURITY;--> statement-breakpoint
CREATE TABLE "nfl_player_game_snaps" (
	"game_id" text NOT NULL,
	"season" integer NOT NULL,
	"week" integer NOT NULL,
	"pfr_player_id" text NOT NULL,
	"gsis_id" text,
	"player" text NOT NULL,
	"position" text,
	"team" text NOT NULL,
	"offense_snaps" integer NOT NULL,
	"offense_pct" double precision,
	"defense_snaps" integer NOT NULL,
	"defense_pct" double precision,
	"st_snaps" integer NOT NULL,
	"st_pct" double precision,
	CONSTRAINT "nfl_player_game_snaps_game_id_pfr_player_id_pk" PRIMARY KEY("game_id","pfr_player_id")
);
--> statement-breakpoint
ALTER TABLE "nfl_player_game_snaps" ENABLE ROW LEVEL SECURITY;--> statement-breakpoint
ALTER TABLE "nfl_injury_reports" ADD CONSTRAINT "nfl_injury_reports_team_nfl_teams_abbr_fk" FOREIGN KEY ("team") REFERENCES "public"."nfl_teams"("abbr") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "nfl_injury_reports" ADD CONSTRAINT "nfl_injury_reports_game_id_nfl_games_game_id_fk" FOREIGN KEY ("game_id") REFERENCES "public"."nfl_games"("game_id") ON DELETE set null ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "nfl_player_game_snaps" ADD CONSTRAINT "nfl_player_game_snaps_game_id_nfl_games_game_id_fk" FOREIGN KEY ("game_id") REFERENCES "public"."nfl_games"("game_id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "nfl_player_game_snaps" ADD CONSTRAINT "nfl_player_game_snaps_team_nfl_teams_abbr_fk" FOREIGN KEY ("team") REFERENCES "public"."nfl_teams"("abbr") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
CREATE INDEX "nfl_injury_reports_week_idx" ON "nfl_injury_reports" USING btree ("season","week","team");--> statement-breakpoint
CREATE INDEX "nfl_injury_reports_player_idx" ON "nfl_injury_reports" USING btree ("gsis_id");--> statement-breakpoint
CREATE UNIQUE INDEX "nfl_injury_reports_backfill_key" ON "nfl_injury_reports" USING btree ("season","week","team","gsis_id") WHERE "nfl_injury_reports"."first_seen_at" IS NULL;--> statement-breakpoint
CREATE INDEX "nfl_player_game_snaps_gsis_idx" ON "nfl_player_game_snaps" USING btree ("gsis_id","season","week");