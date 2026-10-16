# Fixtures

## `synthetic-nfl-odds.json` — SYNTHETIC, NOT REAL ODDS

Hand-authored on 2026-10-15 in the documented shape of The Odds API v4
`GET /v4/sports/americanfootball_nfl/odds` response. Team names are real NFL
teams so the data reads naturally, but **every matchup, price, line, and
timestamp is invented** for testing. It must never be presented as real market
data; the UI shows a "Synthetic fixture" banner whenever it renders this file.

Normalize it with `observedAt = SYNTHETIC_OBSERVED_AT` (`2026-10-15T18:00:00Z`).

Deliberate edge cases:

| Event                          | Case                                                                                                                                                                                                              |
| ------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `synthetic-evt-001` BUF vs MIA | Caesars (`williamhill_us`) absent; BetMGM has no totals; FanDuel home −3 vs others −3.5 (mismatched points); Hard Rock total 48 vs 47.5                                                                           |
| `synthetic-evt-002` GB vs CHI  | DraftKings price `50` (invalid); FanDuel outcome named `"Green Bay"` (unknown); BetMGM spread −5.5/+6 (inconsistent) and unparseable totals `last_update`; unexpected book `bovada`; Hard Rock and Caesars absent |
| `synthetic-evt-003` DAL vs PHI | Kickoff before `observedAt` (in-play, `isLive = true`)                                                                                                                                                            |

Real provider captures go in the repo-root `fixtures/the-odds-api/local/` folder,
which is gitignored. This repo is public and the provider's terms restrict
redistributing raw data.
