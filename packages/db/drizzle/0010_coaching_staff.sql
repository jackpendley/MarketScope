CREATE TABLE "nfl_coaching_staff" (
	"id" bigint PRIMARY KEY GENERATED ALWAYS AS IDENTITY (sequence name "nfl_coaching_staff_id_seq" INCREMENT BY 1 MINVALUE 1 MAXVALUE 9223372036854775807 START WITH 1 CACHE 1),
	"season" integer NOT NULL,
	"team" text NOT NULL,
	"role" text NOT NULL,
	"coach_id" text NOT NULL,
	"coach_name" text NOT NULL,
	"from_week" integer NOT NULL,
	"to_week" integer NOT NULL,
	"offense_playcaller" boolean NOT NULL,
	"defense_playcaller" boolean NOT NULL,
	"source_url" text,
	"playcaller_basis" text,
	"playcaller_source_url" text,
	CONSTRAINT "nfl_coaching_staff_span_key" UNIQUE("season","team","role","coach_id","from_week"),
	CONSTRAINT "nfl_coaching_staff_weeks" CHECK ("nfl_coaching_staff"."from_week" <= "nfl_coaching_staff"."to_week"),
	CONSTRAINT "nfl_coaching_staff_role" CHECK ("nfl_coaching_staff"."role" IN ('HC', 'OC', 'DC', 'STC', 'PC'))
);
--> statement-breakpoint
ALTER TABLE "nfl_coaching_staff" ENABLE ROW LEVEL SECURITY;--> statement-breakpoint
ALTER TABLE "nfl_coaching_staff" ADD CONSTRAINT "nfl_coaching_staff_team_nfl_teams_abbr_fk" FOREIGN KEY ("team") REFERENCES "public"."nfl_teams"("abbr") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
CREATE INDEX "nfl_coaching_staff_coach_idx" ON "nfl_coaching_staff" USING btree ("coach_id");