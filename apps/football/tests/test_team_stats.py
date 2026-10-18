"""Unit tests for the play-by-play -> team-game aggregation, on hand-built plays."""

import math

import polars as pl
import pytest

from marketscope_football import design as d
from marketscope_football.pbp import PBP_COLUMNS
from marketscope_football.team_stats import team_game_stats, wp_weight

GAME = "2025_01_SF_LA"

FLOATS = {"pass", "rush", "special", "qb_dropback", "qb_kneel", "qb_spike", "qb_scramble", "sack", "down", "ydstogo",
          "yardline_100", "qtr", "half_seconds_remaining", "game_seconds_remaining", "fixed_drive", "epa", "qb_epa",
          "wp", "success", "yards_gained", "cpoe", "xpass", "shotgun", "no_huddle", "interception", "fumble",
          "fumble_lost", "posteam_score", "posteam_score_post", "fourth_down_converted", "fourth_down_failed",
          "penalty", "penalty_yards", "field_goal_attempt", "kick_distance", "extra_point_attempt",
          "return_touchdown", "play_id"}
INTS = {"season", "week"}


def play(n: int, **kw) -> dict:
    """A plain 1st-and-10 LA run in a neutral game state, overridable field by field."""
    row = {c: None for c in PBP_COLUMNS}
    row.update(game_id=GAME, play_id=float(n), season=2025, season_type="REG", week=1, home_team="LA",
               away_team="SF", posteam="LA", defteam="SF", play_type="run", pass_=0.0, rush=1.0, special=0.0,
               qb_dropback=0.0, sack=0.0, down=1.0, ydstogo=10.0, yardline_100=75.0, qtr=1.0,
               half_seconds_remaining=1500.0 - n, game_seconds_remaining=3300.0 - 30 * n, fixed_drive=1.0,
               epa=0.0, wp=0.5, success=0.0, yards_gained=3.0, shotgun=0.0, no_huddle=0.0, interception=0.0,
               fumble=0.0, fumble_lost=0.0, posteam_score=0.0, posteam_score_post=0.0, penalty=0.0)
    row["pass"] = row.pop("pass_")
    row.update(kw)
    return row


def frame(plays: list[dict]) -> pl.DataFrame:
    schema = {c: pl.Float64 if c in FLOATS else pl.Int32 if c in INTS else pl.String for c in PBP_COLUMNS}
    return pl.DataFrame(plays, schema=schema)


def row(stats: pl.DataFrame, team: str) -> dict:
    return stats.filter(pl.col("team") == team).to_dicts()[0]


def test_one_row_per_team_and_rates_are_null_without_a_denominator():
    stats = team_game_stats(frame([play(1, epa=0.5, success=1.0), play(2, epa=-0.1)]))
    assert stats.height == 2
    la, sf = row(stats, "LA"), row(stats, "SF")
    assert (la["is_home"], la["opponent"], sf["is_home"], sf["opponent"]) == (True, "SF", False, "LA")
    assert la["plays"] == 2 and la["rushes"] == 2 and la["dropbacks"] == 0
    assert la["epa_per_play"] == pytest.approx(0.2)
    assert la["success_rate"] == pytest.approx(0.5)
    assert la["epa_per_dropback"] is None and la["sack_rate"] is None
    # SF never had the ball: counts are 0, rates NULL.
    assert sf["plays"] == 0 and sf["epa_per_play"] is None and sf["drives"] == 0


def test_wp_weight_is_full_inside_10_90_and_floors_at_the_extremes():
    w = pl.DataFrame({"wp": [0.5, 0.1, 0.9, 0.95, 1.0, 0.0, None]}).select(wp_weight())["literal"].to_list()
    assert w == pytest.approx([1, 1, 1, 1 - 0.5 * (1 - d.WP_WEIGHT_FLOOR), d.WP_WEIGHT_FLOOR, d.WP_WEIGHT_FLOOR, 1])


def test_garbage_time_plays_count_less_in_the_model_channel():
    stats = team_game_stats(frame([play(1, epa=1.0, wp=0.5), play(2, epa=-1.0, wp=0.99)]))
    la = row(stats, "LA")
    assert la["epa_per_play"] == pytest.approx(0.0)
    w2 = 1 - 0.09 / 0.10 * (1 - d.WP_WEIGHT_FLOOR)
    assert la["adj_weight"] == pytest.approx(1 + w2)
    assert la["adj_epa_per_play"] == pytest.approx((1.0 - w2) / (1 + w2))


def test_fumble_recovery_luck_is_removed_from_the_model_channel():
    delta = d.FUMBLE_EPA_LOST - d.FUMBLE_EPA_RECOVERED
    lost = play(1, epa=-4.0, fumble=1.0, fumbled_1_team="LA", fumble_lost=1.0)
    kept = play(2, epa=-0.5, fumble=1.0, fumbled_1_team="LA", fumble_lost=0.0)
    la = row(team_game_stats(frame([lost, kept])), "LA")
    luck_lost, luck_kept = (1 - d.FUMBLE_P_LOST) * delta, (0 - d.FUMBLE_P_LOST) * delta
    assert la["fumbles"] == 2 and la["fumbles_lost"] == 1
    assert la["fumble_luck_epa"] == pytest.approx(luck_lost + luck_kept)
    assert la["adj_epa_per_play"] == pytest.approx(((-4.0 - luck_lost) + (-0.5 - luck_kept)) / 2)


def test_interception_luck_uses_passes_defensed_and_epa_is_capped():
    delta = d.INT_EPA - d.INT_EPA_DEFENSED
    pick = play(1, play_type="pass", rush=0.0, qb_dropback=1.0, epa=-9.0, interception=1.0,
                pass_defense_1_player_id="X", **{"pass": 1.0})
    breakup = play(2, play_type="pass", rush=0.0, qb_dropback=1.0, epa=-0.8, pass_defense_1_player_id="Y",
                   **{"pass": 1.0})
    la = row(team_game_stats(frame([pick, breakup])), "LA")
    l1, l2 = (1 - d.INT_P_GIVEN_DEFENSED) * delta, -d.INT_P_GIVEN_DEFENSED * delta
    assert la["interceptions"] == 1 and la["passes_defensed"] == 2
    assert la["int_luck_epa"] == pytest.approx(l1 + l2)
    capped = max(-d.EPA_CAP, -9.0 - l1)
    assert la["adj_epa_per_dropback"] == pytest.approx((capped + (-0.8 - l2)) / 2)


def test_drive_points_starting_field_position_and_scoring_opportunities():
    plays = [
        play(1, play_type="kickoff", rush=0.0, special=1.0, epa=0.2, fixed_drive=1.0),  # not part of a drive
        play(2, yardline_100=75.0, fixed_drive=1.0),
        play(3, yardline_100=30.0, fixed_drive=1.0),
        play(4, yardline_100=5.0, fixed_drive=1.0, posteam_score=0.0, posteam_score_post=6.0),
        play(5, play_type="extra_point", rush=0.0, special=1.0, epa=0.1, extra_point_attempt=1.0,
             extra_point_result="good", fixed_drive=1.0, posteam_score=6.0, posteam_score_post=7.0),
        play(6, yardline_100=80.0, fixed_drive=2.0),
        play(7, play_type="punt", rush=0.0, special=1.0, epa=-0.3, yardline_100=78.0, fixed_drive=2.0),
    ]
    la = row(team_game_stats(frame(plays)), "LA")
    assert la["drives"] == 2 and la["drive_points"] == 7
    assert la["avg_start_yardline"] == pytest.approx(((100 - 75) + (100 - 80)) / 2)
    assert la["scoring_opps"] == 1 and la["scoring_opp_points"] == 7
    assert la["xp_attempts"] == 1 and la["xp_made"] == 1


def test_pace_counts_neutral_gaps_within_a_drive_only():
    plays = [
        play(1, game_seconds_remaining=3000.0),
        play(2, game_seconds_remaining=2970.0),
        play(3, game_seconds_remaining=2940.0, wp=0.95),  # not neutral: its gap is not measured
        play(4, game_seconds_remaining=2850.0),  # 90 s gap from play 3 would be excluded anyway
        play(5, game_seconds_remaining=2800.0, fixed_drive=2.0),
    ]
    la = row(team_game_stats(frame(plays)), "LA")
    # Gaps measured: 1->2 (30 s), 2->3 (30 s); 4->5 crosses drives; 5 has no next snap.
    assert la["neutral_seconds_per_play"] == pytest.approx(30.0)


def test_special_teams_epa_is_zero_sum_and_field_goals_have_expectations():
    fg = play(1, play_type="field_goal", rush=0.0, special=1.0, epa=1.2, field_goal_attempt=1.0,
              field_goal_result="made", kick_distance=50.0)
    punt = play(2, play_type="punt", rush=0.0, special=1.0, epa=-0.4, posteam="SF", defteam="LA")
    stats = team_game_stats(frame([fg, punt]))
    la, sf = row(stats, "LA"), row(stats, "SF")
    assert la["st_epa"] == pytest.approx(1.6) and sf["st_epa"] == pytest.approx(-1.6)
    assert la["st_plays"] == 2 and sf["st_plays"] == 2
    p50 = 1 / (1 + math.exp(-(d.FG_INTERCEPT + d.FG_SLOPE * 50)))
    assert (la["fg_attempts"], la["fg_made"]) == (1, 1) and la["fg_expected"] == pytest.approx(p50)


def test_return_and_defensive_touchdowns_and_penalties_are_credited_to_the_right_team():
    pick_six = play(1, play_type="pass", rush=0.0, qb_dropback=1.0, epa=-7.0, interception=1.0,
                    return_touchdown=1.0, td_team="SF", pass_defense_1_player_id="X", **{"pass": 1.0})
    punt_return = play(2, play_type="punt", rush=0.0, special=1.0, epa=-5.0, return_touchdown=1.0, td_team="SF")
    flag = play(3, play_type="no_play", penalty=1.0, penalty_team="SF", penalty_yards=15.0, epa=0.9)
    stats = team_game_stats(frame([pick_six, punt_return, flag]))
    sf = row(stats, "SF")
    assert (sf["defensive_tds"], sf["return_tds"], sf["penalties"], sf["penalty_yards"]) == (1, 1, 1, 15)
    assert row(stats, "LA")["plays"] == 2  # the run flagged for an SF penalty still counts (nflfastR)
