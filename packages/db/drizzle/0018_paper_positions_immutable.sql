-- Paper positions are immutable once placed (ADR-056): only the grading columns may change, and live
-- positions can never be deleted. TRUNCATE (test resets) does not fire row triggers.
CREATE OR REPLACE FUNCTION paper_positions_guard() RETURNS trigger
LANGUAGE plpgsql SET search_path = '' AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    IF OLD.mode = 'live' THEN
      RAISE EXCEPTION 'live paper positions cannot be deleted (id %)', OLD.id;
    END IF;
    RETURN OLD;
  END IF;
  IF (NEW.strategy, NEW.mode, NEW.game_id, NEW.season, NEW.week, NEW.kickoff_utc, NEW.market, NEW.side,
      NEW.line, NEW.teased_line, NEW.price, NEW.bookmaker_key, NEW.quote_observed_at, NEW.placed_at)
     IS DISTINCT FROM
     (OLD.strategy, OLD.mode, OLD.game_id, OLD.season, OLD.week, OLD.kickoff_utc, OLD.market, OLD.side,
      OLD.line, OLD.teased_line, OLD.price, OLD.bookmaker_key, OLD.quote_observed_at, OLD.placed_at) THEN
    RAISE EXCEPTION 'paper position placement is immutable (id %); only grading columns may change', OLD.id;
  END IF;
  RETURN NEW;
END;
$$;
--> statement-breakpoint
CREATE TRIGGER paper_positions_guard
  BEFORE UPDATE OR DELETE ON paper_positions
  FOR EACH ROW EXECUTE FUNCTION paper_positions_guard();
