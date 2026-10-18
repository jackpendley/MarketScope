"""Snap counts, injury reports and P(plays | injury status), from nflverse.

Pure functions over polars frames (unit-tested); ingest.py does the I/O.

Point-in-time rule for injuries (ADR-030): a report row first seen BEFORE its team's kickoff
is a live observation (`first_seen_at` = fetch time). A row first seen after kickoff, including
all history, is a backfill row (`first_seen_at` NULL): the final weekly report, assumed known
before kickoff because NFL teams must publish it by the day before the game.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime

import polars as pl

POSITION_GROUPS = {
    "QB": "QB",
    "RB": "RB", "HB": "RB", "FB": "RB",
    "WR": "WR",
    "TE": "TE",
    "T": "OL", "OT": "OL", "G": "OL", "OG": "OL", "C": "OL", "OL": "OL",
    "DE": "DL", "DT": "DL", "NT": "DL", "DL": "DL",
    "LB": "LB", "ILB": "LB", "OLB": "LB", "MLB": "LB",
    "CB": "DB", "S": "DB", "FS": "DB", "SS": "DB", "DB": "DB", "SAF": "DB",
    "K": "ST", "P": "ST", "LS": "ST",
}
STATUSES = ("Out", "Doubtful", "Questionable")
GROUP_ORDER = ("QB", "RB", "WR", "TE", "OL", "DL", "LB", "DB", "ST")


def position_group(col: str = "position") -> pl.Expr:
    return pl.col(col).replace_strict(POSITION_GROUPS, default="other", return_dtype=pl.String)


def practice_level(col: str = "practice_status") -> pl.Expr:
    """The final practice status of the week: Full, Limited, DNP (did not participate) or NULL."""
    s = pl.col(col)
    return (
        pl.when(s.str.starts_with("Full")).then(pl.lit("Full"))
        .when(s.str.starts_with("Limited")).then(pl.lit("Limited"))
        .when(s.str.starts_with("Did Not")).then(pl.lit("DNP"))
        .otherwise(pl.lit(None, dtype=pl.String))
    )


# --- Snap counts ------------------------------------------------------------------------

SNAP_COLUMNS = ["game_id", "season", "week", "pfr_player_id", "gsis_id", "player", "position", "team", "offense_snaps", "offense_pct",
                "defense_snaps", "defense_pct", "st_snaps", "st_pct"]


def snap_rows(snaps: pl.DataFrame, players: pl.DataFrame) -> pl.DataFrame:
    """nflverse load_snap_counts (PFR ids) -> nfl_player_game_snaps rows, with the gsis_id used by
    injury reports and play-by-play attached through load_players' pfr_id."""
    ids = players.select("gsis_id", pl.col("pfr_id").alias("pfr_player_id")).drop_nulls().unique("pfr_player_id")
    out = snaps.join(ids, on="pfr_player_id", how="left")
    return out.with_columns(
        [pl.col(c).fill_null(0).cast(pl.Int32) for c in ("season", "week", "offense_snaps", "defense_snaps", "st_snaps")]
    ).select(SNAP_COLUMNS).unique(["game_id", "pfr_player_id"], keep="first", maintain_order=True)


def played(snaps: pl.DataFrame) -> pl.DataFrame:
    """(season, week, gsis_id) for players with at least one snap of any kind."""
    total = pl.col("offense_snaps") + pl.col("defense_snaps") + pl.col("st_snaps")
    return snaps.filter((total > 0) & pl.col("gsis_id").is_not_null()).select(
        pl.col("season").cast(pl.Int32), pl.col("week").cast(pl.Int32), "gsis_id"
    ).unique()


# --- Injury reports ---------------------------------------------------------------------

INJURY_FIELDS = ["report_status", "report_primary_injury", "report_secondary_injury", "practice_status",
                 "practice_primary_injury", "position"]
INJURY_KEY = ("season", "week", "team", "gsis_id")


def injury_rows(injuries: pl.DataFrame) -> list[dict]:
    """nflverse load_injuries -> normalized rows with a content hash of the reported fields."""
    df = injuries.filter(pl.col("gsis_id").is_not_null()).with_columns(
        pl.col("season").cast(pl.Int32), pl.col("week").cast(pl.Int32)
    ).unique(list(INJURY_KEY), keep="last")
    rows = []
    for r in df.iter_rows(named=True):
        content = "|".join(str(r.get(f) or "") for f in INJURY_FIELDS)
        rows.append({
            "season": r["season"], "week": r["week"], "game_type": r["game_type"], "team": r["team"],
            "gsis_id": r["gsis_id"], "full_name": r["full_name"], **{f: r.get(f) for f in INJURY_FIELDS},
            "content_hash": hashlib.sha1(content.encode()).hexdigest()[:16],
        })
    return rows


@dataclass
class InjuryPlan:
    inserts: list[dict] = field(default_factory=list)  # new rows (live or backfill)
    touch: list[int] = field(default_factory=list)  # live rows seen again unchanged: bump last_seen_at
    backfill_updates: list[dict] = field(default_factory=list)  # corrections to backfill rows, in place


def plan_injury_changes(
    fetched: list[dict],
    latest: dict[tuple, dict],
    kickoffs: dict[tuple, datetime],
    now: datetime,
) -> InjuryPlan:
    """Decide what to write for one fetch.

    `latest` maps (season, week, team, gsis_id) to the newest stored row for that key
    ({"id", "content_hash", "first_seen_at"}); `kickoffs` maps (season, week, team) to that
    team's kickoff. A key whose game is unknown is treated as already played (backfill).
    Live history is append-only: a status change before kickoff adds a row; after kickoff a
    live row is frozen.
    """
    plan = InjuryPlan()
    for row in fetched:
        key = tuple(row[k] for k in INJURY_KEY)
        kickoff = kickoffs.get(key[:3])
        before_kickoff = kickoff is not None and now < kickoff
        prev = latest.get(key)
        live = {**row, "first_seen_at": now, "last_seen_at": now}
        backfill = {**row, "first_seen_at": None, "last_seen_at": None}
        if prev is None:
            plan.inserts.append(live if before_kickoff else backfill)
        elif prev["first_seen_at"] is not None:  # newest stored row is live
            if not before_kickoff:
                continue
            if prev["content_hash"] == row["content_hash"]:
                plan.touch.append(prev["id"])
            else:
                plan.inserts.append(live)
        else:  # only a backfill row so far
            if before_kickoff:  # e.g. a rescheduled game: start live history
                if prev["content_hash"] != row["content_hash"]:
                    plan.inserts.append(live)
            elif prev["content_hash"] != row["content_hash"]:
                plan.backfill_updates.append({**backfill, "id": prev["id"]})
    return plan


# --- P(plays | status) ------------------------------------------------------------------


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / (1 + z * z / n)
    return (centre - half, centre + half)


def status_outcomes(injuries: pl.DataFrame, snaps: pl.DataFrame) -> pl.DataFrame:
    """One row per injury-report listing with a game status, and whether the player played."""
    listed = injuries.filter(pl.col("report_status").is_in(list(STATUSES)) & pl.col("gsis_id").is_not_null())
    listed = listed.with_columns(pl.col("season").cast(pl.Int32), pl.col("week").cast(pl.Int32))
    out = listed.join(played(snaps).with_columns(played=pl.lit(1)), on=["season", "week", "gsis_id"], how="left")
    return out.with_columns(
        played=pl.col("played").fill_null(0), group=position_group(), practice=practice_level()
    ).select("season", "week", "team", "gsis_id", "report_status", "group", "practice", "played")


def rate_table(outcomes: pl.DataFrame, by: list[str]) -> pl.DataFrame:
    t = outcomes.group_by(by).agg(n=pl.len(), played=pl.col("played").sum()).sort(by)
    cis = [wilson(k, n) for k, n in zip(t["played"], t["n"])]
    return t.with_columns(
        p=pl.col("played") / pl.col("n"),
        lo=pl.Series([c[0] for c in cis]),
        hi=pl.Series([c[1] for c in cis]),
    )
