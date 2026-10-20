CREATE TABLE "paper_positions" (
	"id" bigint PRIMARY KEY GENERATED ALWAYS AS IDENTITY (sequence name "paper_positions_id_seq" INCREMENT BY 1 MINVALUE 1 MAXVALUE 9223372036854775807 START WITH 1 CACHE 1),
	"strategy" text NOT NULL,
	"mode" text NOT NULL,
	"game_id" text NOT NULL,
	"season" integer NOT NULL,
	"week" integer NOT NULL,
	"kickoff_utc" timestamp with time zone NOT NULL,
	"market" text NOT NULL,
	"side" text NOT NULL,
	"line" numeric(5, 1) NOT NULL,
	"teased_line" numeric(5, 1),
	"price" integer,
	"bookmaker_key" text NOT NULL,
	"quote_observed_at" timestamp with time zone NOT NULL,
	"placed_at" timestamp with time zone DEFAULT now() NOT NULL,
	"result" text,
	"close_line" numeric(5, 1),
	"close_source" text,
	"clv" double precision,
	"graded_at" timestamp with time zone,
	CONSTRAINT "paper_positions_strategy_game_mode_uq" UNIQUE("strategy","game_id","mode"),
	CONSTRAINT "paper_positions_mode" CHECK ("paper_positions"."mode" IN ('live', 'reconstructed', 'synthetic')),
	CONSTRAINT "paper_positions_market" CHECK ("paper_positions"."market" IN ('spread', 'total', 'teaser_leg')),
	CONSTRAINT "paper_positions_result" CHECK ("paper_positions"."result" IS NULL OR "paper_positions"."result" IN ('win', 'loss', 'push')),
	CONSTRAINT "paper_positions_quote_before_kickoff" CHECK ("paper_positions"."quote_observed_at" < "paper_positions"."kickoff_utc"),
	CONSTRAINT "paper_positions_live_before_kickoff" CHECK ("paper_positions"."mode" <> 'live' OR "paper_positions"."placed_at" < "paper_positions"."kickoff_utc"),
	CONSTRAINT "paper_positions_teaser_shape" CHECK (("paper_positions"."market" = 'teaser_leg') = ("paper_positions"."teased_line" IS NOT NULL)
        AND ("paper_positions"."market" = 'teaser_leg' OR "paper_positions"."price" IS NOT NULL))
);
--> statement-breakpoint
ALTER TABLE "paper_positions" ENABLE ROW LEVEL SECURITY;--> statement-breakpoint
ALTER TABLE "paper_positions" ADD CONSTRAINT "paper_positions_game_id_nfl_games_game_id_fk" FOREIGN KEY ("game_id") REFERENCES "public"."nfl_games"("game_id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "paper_positions" ADD CONSTRAINT "paper_positions_bookmaker_key_bookmakers_key_fk" FOREIGN KEY ("bookmaker_key") REFERENCES "public"."bookmakers"("key") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
CREATE INDEX "paper_positions_season_idx" ON "paper_positions" USING btree ("season","strategy");