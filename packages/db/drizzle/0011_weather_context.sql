CREATE TABLE "nfl_game_context" (
	"game_id" text NOT NULL,
	"team" text NOT NULL,
	"opponent" text NOT NULL,
	"season" integer NOT NULL,
	"week" integer NOT NULL,
	"is_home" boolean NOT NULL,
	"neutral_site" boolean NOT NULL,
	"division_game" boolean NOT NULL,
	"venue_key" text NOT NULL,
	"roof_type" text NOT NULL,
	"rest_days" integer,
	"rest_diff" integer,
	"bye_before" boolean,
	"short_week" boolean,
	"home_venue_key" text NOT NULL,
	"travel_km" double precision NOT NULL,
	"tz_shift_hours" double precision NOT NULL,
	"body_clock_kickoff_hour" double precision NOT NULL,
	"venue_local_kickoff_hour" double precision NOT NULL,
	"altitude_m" integer NOT NULL,
	"altitude_change_m" integer NOT NULL,
	"road_streak" integer NOT NULL,
	"hc_coach" text,
	"off_playcaller" text,
	"def_playcaller" text,
	"hc_tenure_games" integer,
	"off_playcaller_tenure_games" integer,
	"def_playcaller_tenure_games" integer,
	"new_off_playcaller" boolean,
	"new_def_playcaller" boolean,
	CONSTRAINT "nfl_game_context_game_id_team_pk" PRIMARY KEY("game_id","team")
);
--> statement-breakpoint
ALTER TABLE "nfl_game_context" ENABLE ROW LEVEL SECURITY;--> statement-breakpoint
CREATE TABLE "nfl_weather_forecasts" (
	"game_id" text NOT NULL,
	"lead_days" integer NOT NULL,
	"forecast_hour_utc" timestamp with time zone NOT NULL,
	"temperature_f" double precision NOT NULL,
	"wind_mph" double precision NOT NULL,
	"gust_mph" double precision NOT NULL,
	"precip_in" double precision NOT NULL,
	"source" text NOT NULL,
	"fetched_at" timestamp with time zone DEFAULT now() NOT NULL,
	CONSTRAINT "nfl_weather_forecasts_game_id_lead_days_pk" PRIMARY KEY("game_id","lead_days"),
	CONSTRAINT "nfl_weather_forecasts_lead" CHECK ("nfl_weather_forecasts"."lead_days" BETWEEN 0 AND 7)
);
--> statement-breakpoint
ALTER TABLE "nfl_weather_forecasts" ENABLE ROW LEVEL SECURITY;--> statement-breakpoint
ALTER TABLE "nfl_game_context" ADD CONSTRAINT "nfl_game_context_game_id_nfl_games_game_id_fk" FOREIGN KEY ("game_id") REFERENCES "public"."nfl_games"("game_id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "nfl_game_context" ADD CONSTRAINT "nfl_game_context_team_nfl_teams_abbr_fk" FOREIGN KEY ("team") REFERENCES "public"."nfl_teams"("abbr") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "nfl_game_context" ADD CONSTRAINT "nfl_game_context_opponent_nfl_teams_abbr_fk" FOREIGN KEY ("opponent") REFERENCES "public"."nfl_teams"("abbr") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "nfl_weather_forecasts" ADD CONSTRAINT "nfl_weather_forecasts_game_id_nfl_games_game_id_fk" FOREIGN KEY ("game_id") REFERENCES "public"."nfl_games"("game_id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
CREATE INDEX "nfl_game_context_team_season_idx" ON "nfl_game_context" USING btree ("team","season","week");