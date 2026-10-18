CREATE TABLE "model_predictions" (
	"model_version" text NOT NULL,
	"game_id" text NOT NULL,
	"predicted_at" timestamp with time zone NOT NULL,
	"kickoff_utc" timestamp with time zone NOT NULL,
	"home_team" text NOT NULL,
	"away_team" text NOT NULL,
	"expected_margin" double precision NOT NULL,
	"expected_total" double precision,
	"home_score" double precision,
	"away_score" double precision,
	"p_home" double precision NOT NULL,
	"home_qb" text,
	"away_qb" text,
	"home_qb_p" double precision,
	"away_qb_p" double precision,
	"contributions" jsonb NOT NULL,
	CONSTRAINT "model_predictions_model_version_game_id_predicted_at_pk" PRIMARY KEY("model_version","game_id","predicted_at"),
	CONSTRAINT "model_predictions_before_kickoff" CHECK ("model_predictions"."predicted_at" < "model_predictions"."kickoff_utc"),
	CONSTRAINT "model_predictions_p_range" CHECK ("model_predictions"."p_home" >= 0 AND "model_predictions"."p_home" <= 1)
);
--> statement-breakpoint
ALTER TABLE "model_predictions" ENABLE ROW LEVEL SECURITY;--> statement-breakpoint
CREATE TABLE "model_runs" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"model_version" text NOT NULL,
	"run_kind" text NOT NULL,
	"seasons" text NOT NULL,
	"games" integer NOT NULL,
	"metrics" jsonb NOT NULL,
	"params_sha256" text NOT NULL,
	"code_sha" text NOT NULL,
	"notes" text,
	"ran_at" timestamp with time zone NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	CONSTRAINT "model_runs_kind" CHECK ("model_runs"."run_kind" IN ('validation', 'test', 'forward'))
);
--> statement-breakpoint
ALTER TABLE "model_runs" ENABLE ROW LEVEL SECURITY;--> statement-breakpoint
ALTER TABLE "model_predictions" ADD CONSTRAINT "model_predictions_game_id_nfl_games_game_id_fk" FOREIGN KEY ("game_id") REFERENCES "public"."nfl_games"("game_id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
CREATE INDEX "model_predictions_game_idx" ON "model_predictions" USING btree ("game_id");--> statement-breakpoint
CREATE UNIQUE INDEX "model_runs_one_test_per_version" ON "model_runs" USING btree ("model_version") WHERE "model_runs"."run_kind" = 'test';