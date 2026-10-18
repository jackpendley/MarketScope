CREATE TABLE "season_projections" (
	"model_version" text NOT NULL,
	"season" integer NOT NULL,
	"week" integer NOT NULL,
	"team" text NOT NULL,
	"sims" integer NOT NULL,
	"games_played" integer NOT NULL,
	"strength" double precision NOT NULL,
	"mean_wins" double precision NOT NULL,
	"win_dist" jsonb NOT NULL,
	"playoff_p" double precision NOT NULL,
	"division_p" double precision NOT NULL,
	"seed1_p" double precision NOT NULL,
	"conf_p" double precision NOT NULL,
	"sb_p" double precision NOT NULL,
	"computed_at" timestamp with time zone DEFAULT now() NOT NULL,
	CONSTRAINT "season_projections_model_version_season_week_team_pk" PRIMARY KEY("model_version","season","week","team"),
	CONSTRAINT "season_projections_p_range" CHECK ("season_projections"."playoff_p" BETWEEN 0 AND 1 AND "season_projections"."division_p" BETWEEN 0 AND 1 AND "season_projections"."seed1_p" BETWEEN 0 AND 1 AND "season_projections"."conf_p" BETWEEN 0 AND 1 AND "season_projections"."sb_p" BETWEEN 0 AND 1)
);
--> statement-breakpoint
ALTER TABLE "season_projections" ENABLE ROW LEVEL SECURITY;--> statement-breakpoint
ALTER TABLE "season_projections" ADD CONSTRAINT "season_projections_team_nfl_teams_abbr_fk" FOREIGN KEY ("team") REFERENCES "public"."nfl_teams"("abbr") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
CREATE INDEX "season_projections_team_idx" ON "season_projections" USING btree ("team","season","week");