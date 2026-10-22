ALTER TABLE "model_predictions" ADD COLUMN "params_sha256" text;--> statement-breakpoint
ALTER TABLE "model_predictions" ADD COLUMN "feature_schema_sha256" text;--> statement-breakpoint
ALTER TABLE "model_predictions" ADD COLUMN "code_sha" text;--> statement-breakpoint
ALTER TABLE "model_predictions" ADD COLUMN "input_sha256" text;