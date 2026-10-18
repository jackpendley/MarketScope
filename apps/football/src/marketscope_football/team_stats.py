"""Play-by-play -> one row per team per game (nfl_team_game_stats).

Every row describes the team's OFFENSE (and its own special teams); a team's defense in a
game is its opponent's row. Pure polars over the cached play-by-play, so it is unit-tested on
hand-built plays. Definitions follow nflfastR conventions and the frozen constants in
design.py; docs/DATA_DICTIONARY.md documents each column.
"""

from __future__ import annotations

import polars as pl

from . import design as d

SCRIMMAGE_TYPES = {"pass", "run", "punt", "field_goal", "qb_kneel", "qb_spike"}

# Count columns (0 when the team had no such plays) vs rate columns (NULL without a denominator).
COUNT_COLUMNS = [
    "plays", "dropbacks", "rushes", "early_down_plays", "neutral_plays", "sacks", "interceptions",
    "passes_defensed", "fumbles", "fumbles_lost", "drives", "drive_points", "scoring_opps", "scoring_opp_points",
    "fourth_down_attempts", "fourth_down_conversions", "penalties", "penalty_yards", "st_plays",
    "fg_attempts", "fg_made", "xp_attempts", "xp_made", "return_tds", "defensive_tds",
]
FLOAT_COUNT_COLUMNS = ["adj_weight", "fumble_luck_epa", "int_luck_epa", "st_epa", "fg_expected"]


def scrimmage(pbp: pl.DataFrame) -> pl.DataFrame:
    """Offensive scrimmage plays with an EPA value (passes incl. sacks/scrambles, and runs)."""
    return pbp.filter(
        ((pl.col("pass") == 1) | (pl.col("rush") == 1)) & pl.col("epa").is_not_null() & pl.col("posteam").is_not_null()
    )


def own_fumble() -> pl.Expr:
    """The offense fumbled (not a defender fumbling on an interception return)."""
    return (pl.col("fumble") == 1) & (pl.col("fumbled_1_team") == pl.col("posteam")) & (pl.col("interception") != 1)


def wp_weight() -> pl.Expr:
    lo, hi = d.WP_FULL_WEIGHT
    outside = pl.max_horizontal(lo - pl.col("wp"), pl.col("wp") - hi, pl.lit(0.0))
    w = 1 - outside / lo * (1 - d.WP_WEIGHT_FLOOR)
    return pl.when(pl.col("wp").is_null()).then(1.0).otherwise(w.clip(d.WP_WEIGHT_FLOOR, 1.0))


def fumble_luck() -> pl.Expr:
    delta = d.FUMBLE_EPA_LOST - d.FUMBLE_EPA_RECOVERED
    return pl.when(own_fumble()).then((pl.col("fumble_lost").fill_null(0) - d.FUMBLE_P_LOST) * delta).otherwise(0.0)


def interception_luck() -> pl.Expr:
    delta = d.INT_EPA - d.INT_EPA_DEFENSED
    defensed = (pl.col("pass") == 1) & pl.col("pass_defense_1_player_id").is_not_null()
    return pl.when(defensed).then((pl.col("interception").fill_null(0) - d.INT_P_GIVEN_DEFENSED) * delta).otherwise(0.0)


def neutral() -> pl.Expr:
    lo, hi = d.NEUTRAL_WP
    return (
        pl.col("wp").is_between(lo, hi) & (pl.col("qtr") <= 4)
        & (pl.col("half_seconds_remaining") > d.NEUTRAL_MIN_HALF_SECONDS)
    )


def fg_make_probability(distance: pl.Expr) -> pl.Expr:
    return 1 / (1 + (-(d.FG_INTERCEPT + d.FG_SLOPE * distance)).exp())


def _mean_where(cond: pl.Expr, value: pl.Expr) -> pl.Expr:
    return pl.when(cond).then(value).mean()


def _weighted(cond: pl.Expr) -> pl.Expr:
    num = pl.when(cond).then(pl.col("w") * pl.col("adj_epa")).sum()
    den = pl.when(cond).then(pl.col("w")).sum()
    return pl.when(den > 0).then(num / den)


def _offense(sc: pl.DataFrame) -> pl.DataFrame:
    drop, rush = pl.col("qb_dropback") == 1, pl.col("rush") == 1
    early = pl.col("down").is_in([1.0, 2.0])
    ok = pl.lit(True)
    sc = sc.with_columns(
        w=wp_weight(),
        fumble_luck=fumble_luck(),
        int_luck=interception_luck(),
        is_neutral=neutral().fill_null(False),
        explosive=((pl.col("pass") == 1) & (pl.col("yards_gained") >= d.EXPLOSIVE_PASS_YARDS))
        | (rush & (pl.col("yards_gained") >= d.EXPLOSIVE_RUSH_YARDS)),
    ).with_columns(adj_epa=(pl.col("epa") - pl.col("fumble_luck") - pl.col("int_luck")).clip(-d.EPA_CAP, d.EPA_CAP))
    # Seconds to the next snap of the same drive (pace), measured from neutral snaps only.
    sc = sc.sort("game_id", "play_id").with_columns(
        gap=pl.col("game_seconds_remaining")
        - pl.col("game_seconds_remaining").shift(-1).over("game_id", "posteam", "fixed_drive")
    )
    pace_ok = pl.col("is_neutral") & (pl.col("gap") > 0) & (pl.col("gap") <= d.PACE_MAX_GAP_SECONDS)
    neutral_xpass = pl.col("is_neutral") & pl.col("xpass").is_not_null()
    return sc.group_by("game_id", pl.col("posteam").alias("team")).agg(
        plays=pl.len(),
        dropbacks=drop.sum(),
        rushes=rush.sum(),
        early_down_plays=early.sum(),
        neutral_plays=pl.col("is_neutral").sum(),
        epa_per_play=pl.col("epa").mean(),
        epa_per_dropback=_mean_where(drop, pl.col("epa")),
        epa_per_rush=_mean_where(rush, pl.col("epa")),
        early_down_epa_per_play=_mean_where(early, pl.col("epa")),
        adj_epa_per_play=_weighted(ok),
        adj_epa_per_dropback=_weighted(drop),
        adj_epa_per_rush=_weighted(rush),
        adj_weight=pl.col("w").sum(),
        success_rate=pl.col("success").mean(),
        dropback_success_rate=_mean_where(drop, pl.col("success")),
        rush_success_rate=_mean_where(rush, pl.col("success")),
        explosive_rate=pl.col("explosive").cast(pl.Float64).mean(),
        epa_per_success=_mean_where(pl.col("success") == 1, pl.col("epa")),
        cpoe=pl.col("cpoe").mean(),
        sacks=pl.col("sack").fill_null(0).sum(),
        sack_rate=pl.when(drop.sum() > 0).then(pl.col("sack").fill_null(0).sum() / drop.sum()),
        neutral_pass_rate=_mean_where(pl.col("is_neutral"), pl.col("pass")),
        proe=_mean_where(neutral_xpass, pl.col("pass") - pl.col("xpass")),
        neutral_seconds_per_play=_mean_where(pace_ok, pl.col("gap")),
        shotgun_rate=pl.col("shotgun").mean(),
        no_huddle_rate=pl.col("no_huddle").mean(),
        interceptions=pl.col("interception").fill_null(0).sum(),
        passes_defensed=((pl.col("pass") == 1) & pl.col("pass_defense_1_player_id").is_not_null()).sum(),
        fumbles=own_fumble().fill_null(False).sum(),
        fumbles_lost=pl.when(own_fumble()).then(pl.col("fumble_lost").fill_null(0)).sum(),
        fumble_luck_epa=pl.col("fumble_luck").sum(),
        int_luck_epa=pl.col("int_luck").sum(),
        fourth_down_attempts=(pl.col("fourth_down_converted").fill_null(0) + pl.col("fourth_down_failed").fill_null(0)).sum(),
        fourth_down_conversions=pl.col("fourth_down_converted").fill_null(0).sum(),
    )


def _drives(pbp: pl.DataFrame) -> pl.DataFrame:
    plays = pbp.filter(
        pl.col("posteam").is_not_null() & pl.col("fixed_drive").is_not_null() & (pl.col("play_type") != "kickoff")
    ).sort("game_id", "play_id")
    per_drive = plays.group_by("game_id", "posteam", "fixed_drive").agg(
        real=pl.col("play_type").is_in(list(SCRIMMAGE_TYPES)).any(),
        start=pl.col("yardline_100").drop_nulls().first(),
        closest=pl.col("yardline_100").min(),
        points=(pl.col("posteam_score_post") - pl.col("posteam_score")).fill_null(0).clip(0, None).sum(),
    ).filter(pl.col("real"))
    opp = pl.col("closest") <= d.SCORING_OPP_YARDLINE
    return per_drive.group_by("game_id", pl.col("posteam").alias("team")).agg(
        drives=pl.len(),
        drive_points=pl.col("points").sum(),
        avg_start_yardline=(100 - pl.col("start")).mean(),
        scoring_opps=opp.sum(),
        scoring_opp_points=pl.when(opp).then(pl.col("points")).sum(),
    )


def _special_teams(pbp: pl.DataFrame) -> pl.DataFrame:
    st = pbp.filter((pl.col("special") == 1) & pl.col("epa").is_not_null() & pl.col("posteam").is_not_null())
    both = pl.concat([
        st.select("game_id", pl.col("posteam").alias("team"), pl.col("epa")),
        st.select("game_id", pl.col("defteam").alias("team"), -pl.col("epa")),
    ])
    net = both.group_by("game_id", "team").agg(st_plays=pl.len(), st_epa=pl.col("epa").sum())
    fg = pbp.filter((pl.col("field_goal_attempt") == 1) & pl.col("posteam").is_not_null()).group_by(
        "game_id", pl.col("posteam").alias("team")
    ).agg(
        fg_attempts=pl.len(),
        fg_made=(pl.col("field_goal_result") == "made").sum(),
        fg_expected=fg_make_probability(pl.col("kick_distance").cast(pl.Float64)).sum(),
    )
    xp = pbp.filter((pl.col("extra_point_attempt") == 1) & pl.col("posteam").is_not_null()).group_by(
        "game_id", pl.col("posteam").alias("team")
    ).agg(xp_attempts=pl.len(), xp_made=(pl.col("extra_point_result") == "good").sum())
    ret = pbp.filter((pl.col("special") == 1) & (pl.col("return_touchdown") == 1) & pl.col("td_team").is_not_null())
    ret = ret.group_by("game_id", pl.col("td_team").alias("team")).agg(return_tds=pl.len())
    defensive = scrimmage(pbp).filter((pl.col("return_touchdown") == 1) & (pl.col("td_team") == pl.col("defteam")))
    defensive = defensive.group_by("game_id", pl.col("defteam").alias("team")).agg(defensive_tds=pl.len())
    # Flags thrown against the team (accepted, declined or offsetting), as nflverse counts them.
    pen = pbp.filter((pl.col("penalty") == 1) & pl.col("penalty_team").is_not_null())
    pen = pen.group_by("game_id", pl.col("penalty_team").alias("team")).agg(
        penalties=pl.len(), penalty_yards=pl.col("penalty_yards").fill_null(0).sum()
    )
    out = net
    for frame in (fg, xp, ret, defensive, pen):
        out = out.join(frame, on=["game_id", "team"], how="full", coalesce=True)
    return out


def team_game_stats(pbp: pl.DataFrame) -> pl.DataFrame:
    """One row per (game_id, team) for every team appearing in `pbp` as home or away."""
    games = pbp.group_by("game_id").agg(
        pl.col("season").first(), pl.col("season_type").first(), pl.col("week").first(),
        pl.col("home_team").first(), pl.col("away_team").first(),
    )
    base = pl.concat([
        games.select("game_id", "season", "season_type", "week", pl.col("home_team").alias("team"),
                     pl.col("away_team").alias("opponent"), pl.lit(True).alias("is_home")),
        games.select("game_id", "season", "season_type", "week", pl.col("away_team").alias("team"),
                     pl.col("home_team").alias("opponent"), pl.lit(False).alias("is_home")),
    ])
    out = base
    for frame in (_offense(scrimmage(pbp)), _drives(pbp), _special_teams(pbp)):
        out = out.join(frame, on=["game_id", "team"], how="left")
    out = out.with_columns(
        [pl.col(c).fill_null(0).cast(pl.Int64) for c in COUNT_COLUMNS]
        + [pl.col(c).fill_null(0.0).cast(pl.Float64) for c in FLOAT_COUNT_COLUMNS]
    )
    return out.sort("game_id", "is_home")
