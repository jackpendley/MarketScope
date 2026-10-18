"""Team-game observations for the rating filters, built from the cached play-by-play.

`channel_frame` recomputes the pass and rush channels under switchable adjustments (luck, cap,
WP weighting), so ablations refit on exactly the same plays. With all three on it equals
`adj_epa_per_dropback` / `adj_epa_per_rush` in nfl_team_game_stats (tested).
"""

from __future__ import annotations

import csv
from pathlib import Path

import pandas as pd
import polars as pl

from .. import design as d
from ..pbp import load_season
from ..schedules import FRANCHISE
from ..team_stats import fumble_luck, interception_luck, scrimmage, team_game_stats, wp_weight

# Team-game columns carried along for luck decomposition and the Five Factors (outputs.py).
EXTRA_COLUMNS = ["plays", "fumble_luck_epa", "int_luck_epa", "fg_made", "fg_expected", "return_tds", "defensive_tds",
                 "success_rate", "epa_per_success", "avg_start_yardline", "scoring_opps", "scoring_opp_points",
                 "interceptions", "fumbles_lost"]
CACHE_DIR = Path(__file__).resolve().parents[3] / ".cache" / "ratings"
STAFF_CSV = Path(__file__).resolve().parents[3] / "data" / "coaching_staff.csv"


def channel_frame(pbp: pl.DataFrame, luck: bool = True, cap: bool = True, wp: bool = True) -> pl.DataFrame:
    """(game_id, team) -> pass/rush mean EPA under the chosen adjustments, and success rate over all
    scrimmage plays (column `succ_epa` so every unit channel has the same shape), with Kish n_eff."""
    epa = pl.col("epa")
    if luck:
        epa = epa - fumble_luck() - interception_luck()
    if cap:
        epa = epa.clip(-d.EPA_CAP, d.EPA_CAP)
    sc = scrimmage(pbp).with_columns(v=epa, w=wp_weight() if wp else pl.lit(1.0))
    out = []
    for name, cond in (("pass", pl.col("qb_dropback") == 1), ("rush", pl.col("rush") == 1)):
        g = sc.filter(cond).group_by("game_id", pl.col("posteam").alias("team")).agg(
            (pl.col("w") * pl.col("v")).sum().alias("num"), pl.col("w").sum().alias("sw"),
            (pl.col("w") ** 2).sum().alias("sw2"), pl.len().alias("plays"))
        out.append(g.select("game_id", "team", (pl.col("num") / pl.col("sw")).alias(f"{name}_epa"),
                            (pl.col("sw") ** 2 / pl.col("sw2")).alias(f"{name}_n"),
                            pl.col("plays").alias(f"{name}_plays")))
    succ = sc.group_by("game_id", pl.col("posteam").alias("team")).agg(
        ((pl.col("w") * pl.col("success")).sum() / pl.col("w").sum()).alias("succ_epa"),
        (pl.col("w").sum() ** 2 / (pl.col("w") ** 2).sum()).alias("succ_n"))
    return out[0].join(out[1], on=["game_id", "team"], how="full", coalesce=True).join(
        succ, on=["game_id", "team"], how="full", coalesce=True)


def load_observations(seasons: list[int], variant: str = "model", refresh: bool = False) -> pd.DataFrame:
    """One row per (game_id, team): unit channel values and n_eff (pass/rush EPA, success rate, points
    per drive `ppd_epa` with n = drives), plus net special-teams EPA."""
    from .design import VARIANTS

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    slug = variant.replace(" ", "_")
    path = CACHE_DIR / f"obs_{slug}_{seasons[0]}_{seasons[-1]}.parquet"
    if path.exists() and not refresh:
        return pd.read_parquet(path)
    frames = []
    for s in seasons:
        pbp = load_season(s)
        ch = channel_frame(pbp, **VARIANTS[variant])
        st = team_game_stats(pbp).select(
            "game_id", "team", "st_epa", "drives", *EXTRA_COLUMNS,
            pl.when(pl.col("drives") > 0).then(pl.col("drive_points") / pl.col("drives")).alias("ppd_epa"),
            pl.col("drives").cast(pl.Float64).alias("ppd_n"))
        frames.append(st.join(ch, on=["game_id", "team"], how="left").to_pandas())
    obs = pd.concat(frames, ignore_index=True)
    obs["team"] = obs["team"].map(lambda t: FRANCHISE.get(t, t))
    obs.to_parquet(path)
    return obs


def playcallers(path: Path = STAFF_CSV) -> dict[tuple[int, str, int], tuple[str, str]]:
    """(season, franchise, week) -> (offensive play-caller id, defensive play-caller id)."""
    off, dfn = {}, {}
    with path.open() as f:
        for r in csv.DictReader(f):
            team = FRANCHISE.get(r["team"], r["team"])
            for w in range(int(r["from_week"]), int(r["to_week"]) + 1):
                k = (int(r["season"]), team, w)
                if r["offense_playcaller"] == "True":
                    off[k] = r["coach_id"]
                if r["defense_playcaller"] == "True":
                    dfn[k] = r["coach_id"]
    return {k: (off.get(k), dfn.get(k)) for k in off.keys() | dfn.keys()}
