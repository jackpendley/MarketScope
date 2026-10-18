DROP INDEX "market_signals_detected_at_idx";--> statement-breakpoint
DROP INDEX "ingestion_runs_started_at_idx";--> statement-breakpoint
DROP INDEX "odds_observations_history_idx";--> statement-breakpoint
CREATE INDEX "market_signals_recent_idx" ON "market_signals" USING btree ("detected_at" DESC NULLS FIRST,"id");--> statement-breakpoint
CREATE INDEX "ingestion_runs_started_at_idx" ON "ingestion_runs" USING btree ("started_at" DESC NULLS FIRST);--> statement-breakpoint
CREATE INDEX "odds_observations_history_idx" ON "odds_observations" USING btree ("event_id","market_type","selection","bookmaker_key","observed_at" DESC NULLS FIRST);