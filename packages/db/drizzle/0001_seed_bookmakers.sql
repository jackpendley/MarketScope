-- Seed the provider feeds MarketScope collects (mirrors COLLECTED_BOOKMAKERS in
-- packages/shared/src/bookmakers.ts; the collector also upserts these on every run).
-- is_primary = the preferred feed of a board column; hardrockbet is the Hard Rock
-- fallback when the AZ feed is empty (ADR-012).
INSERT INTO "bookmakers" ("key", "display_name", "region_hint", "is_primary", "enabled") VALUES
  ('draftkings',     'DraftKings',              'us',  true,  true),
  ('fanduel',        'FanDuel',                 'us',  true,  true),
  ('betmgm',         'BetMGM',                  'us',  true,  true),
  ('williamhill_us', 'Caesars',                 'us',  true,  true),
  ('hardrockbet_az', 'Hard Rock Bet (AZ)',      'us2', true,  true),
  ('hardrockbet',    'Hard Rock Bet (IN feed)', 'us2', false, true)
ON CONFLICT ("key") DO NOTHING;
