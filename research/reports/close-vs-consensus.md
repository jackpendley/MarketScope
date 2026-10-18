# Data quality: nflverse closing lines vs MarketScope consensus (MS-026)

_Generated 2026-10-18 04:44 UTC · commit `ab73654` ·
reproduce with `research/src/marketscope_research/run_close_check.py`._

nflverse publishes one closing spread and total per game (`spread_line`, positive = home favored). On ingest
MarketScope stores it as `nfl_games.nflverse_close_home_spread` = −`spread_line`, in our home orientation. This
report compares it with our **last observed pregame** board consensus (median of ≥ 3 board books) for every linked
**completed** game (a future game's nflverse line is not yet a close). The two are not the same quantity: imported games' last snapshot is 5 minutes before kickoff, live games'
can be hours earlier, and nflverse's source and timing differ from our books.

## Verdict

**Sign convention confirmed.**
Correlation 0.996; the same team is favored in 98.7% of
79 games; spreads agree within 1 point in 98.7%.

## Agreement by source

| source   | games | median_hours_before_kickoff | spread_exact | spread_within_0.5 | spread_within_1 | spread_mean_abs_diff | spread_mean_signed_diff | same_favorite | spread_correlation | total_within_1 | total_mean_abs_diff |
| -------- | ----- | --------------------------- | ------------ | ----------------- | --------------- | -------------------- | ----------------------- | ------------- | ------------------ | -------------- | ------------------- |
| oddspapi | 79    | 0.10                        | 65.8%        | 93.7%             | 98.7%           | 0.18                 | 0.03                    | 98.7%         | 1.00               | 100.0%         | 0.12                |
| all      | 79    | 0.10                        | 65.8%        | 93.7%             | 98.7%           | 0.18                 | 0.03                    | 98.7%         | 1.00               | 100.0%         | 0.12                |

## Largest spread differences (game ids only; no prices)

| game_id         | source   | hours_before_kickoff | abs_diff |
| --------------- | -------- | -------------------- | -------- |
| 2026_03_LA_DEN  | oddspapi | 0.10                 | 2.75     |
| 2026_01_ARI_LAC | oddspapi | 0.10                 | 1        |
| 2026_02_WAS_DAL | oddspapi | 0.10                 | 1        |
| 2026_04_KC_LV   | oddspapi | 0.10                 | 1        |
| 2026_01_GB_MIN  | oddspapi | 0.10                 | 1        |
