CREATE TABLE "market_signals" (
	"id" bigint PRIMARY KEY GENERATED ALWAYS AS IDENTITY (sequence name "market_signals_id_seq" INCREMENT BY 1 MINVALUE 1 MAXVALUE 9223372036854775807 START WITH 1 CACHE 1),
	"event_id" uuid NOT NULL,
	"signal_type" text NOT NULL,
	"algorithm_version" integer NOT NULL,
	"market_type" "market_type" NOT NULL,
	"selection" "selection",
	"bookmaker_key" text,
	"detected_at" timestamp with time zone NOT NULL,
	"window_start" timestamp with time zone NOT NULL,
	"window_end" timestamp with time zone NOT NULL,
	"value" double precision NOT NULL,
	"details" jsonb NOT NULL,
	"evidence_observation_ids" bigint[] NOT NULL,
	"computed_at" timestamp with time zone DEFAULT now() NOT NULL,
	CONSTRAINT "market_signals_window_order" CHECK ("market_signals"."window_start" <= "market_signals"."window_end")
);
--> statement-breakpoint
ALTER TABLE "market_signals" ENABLE ROW LEVEL SECURITY;--> statement-breakpoint
ALTER TABLE "market_signals" ADD CONSTRAINT "market_signals_event_id_events_id_fk" FOREIGN KEY ("event_id") REFERENCES "public"."events"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "market_signals" ADD CONSTRAINT "market_signals_bookmaker_key_bookmakers_key_fk" FOREIGN KEY ("bookmaker_key") REFERENCES "public"."bookmakers"("key") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
CREATE INDEX "market_signals_detected_at_idx" ON "market_signals" USING btree ("detected_at" DESC NULLS LAST);--> statement-breakpoint
CREATE INDEX "market_signals_event_idx" ON "market_signals" USING btree ("event_id","signal_type","algorithm_version");