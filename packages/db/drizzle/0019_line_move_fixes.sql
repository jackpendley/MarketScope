CREATE TABLE "line_move_fixes" (
	"event_id" uuid NOT NULL,
	"bookmaker_key" text NOT NULL,
	"market_type" "market_type" NOT NULL,
	"changed_at" timestamp with time zone NOT NULL,
	"point" numeric(5, 1),
	"price1" integer,
	"price2" integer,
	"limit1" integer,
	"limit2" integer,
	"source" text NOT NULL,
	"ingested_at" timestamp with time zone DEFAULT now() NOT NULL,
	CONSTRAINT "line_move_fixes_event_id_bookmaker_key_market_type_changed_at_pk" PRIMARY KEY("event_id","bookmaker_key","market_type","changed_at"),
	CONSTRAINT "line_move_fixes_prices_paired" CHECK (("line_move_fixes"."price1" IS NULL) = ("line_move_fixes"."price2" IS NULL)),
	CONSTRAINT "line_move_fixes_point_matches_market" CHECK (CASE WHEN "line_move_fixes"."price1" IS NULL OR "line_move_fixes"."market_type" = 'h2h' THEN "line_move_fixes"."point" IS NULL
        ELSE "line_move_fixes"."point" IS NOT NULL END),
	CONSTRAINT "line_move_fixes_valid_american_prices" CHECK ("line_move_fixes"."price1" IS NULL OR (("line_move_fixes"."price1" <= -100 OR "line_move_fixes"."price1" >= 100)
        AND ("line_move_fixes"."price2" <= -100 OR "line_move_fixes"."price2" >= 100)))
);
--> statement-breakpoint
ALTER TABLE "line_move_fixes" ENABLE ROW LEVEL SECURITY;--> statement-breakpoint
ALTER TABLE "line_move_fixes" ADD CONSTRAINT "line_move_fixes_event_id_events_id_fk" FOREIGN KEY ("event_id") REFERENCES "public"."events"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "line_move_fixes" ADD CONSTRAINT "line_move_fixes_bookmaker_key_bookmakers_key_fk" FOREIGN KEY ("bookmaker_key") REFERENCES "public"."bookmakers"("key") ON DELETE no action ON UPDATE no action;