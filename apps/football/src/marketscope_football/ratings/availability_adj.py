"""Non-QB availability (MS-031b): expected absences per position group, from the injury report and
the players' recent snap shares.

For a team-game, each player's recent share = his mean offensive (or defensive) snap share over the
team's previous RECENT_GAMES games this season (0 for games he missed). His probability of missing
this game comes from this week's final injury report (Out 1.0, Doubtful 0.99, Questionable 0.32:
P(plays | status) 2016-22, reports/plays-given-status.md) or a reserve roster status (IR, PUP...: 1.0).
Absence[group] = sum of P(miss) x recent share, in starter-equivalents. Long-term absences stop
counting once they leave the recent window: by then the filter's ratings reflect the team without
them. Returning players are not credited (a known asymmetry). QBs are handled by the QB layer.
Snap counts (PFR via nflverse) start in 2013.
"""

from __future__ import annotations

from collections import defaultdict, deque

import nflreadpy as nfl
import pandas as pd
import polars as pl

from ..availability import POSITION_GROUPS
from ..schedules import FRANCHISE
from .observations import per_season

RECENT_GAMES = 3
P_MISS = {"Out": 1.0, "Doubtful": 0.991, "Questionable": 0.323}
RESERVE = {"RES"}
GROUPS = {"OL": "ol", "WR": "skill", "TE": "skill", "RB": "rb", "DL": "front7", "LB": "front7", "DB": "db"}
FEATURES = tuple(f"avail_{g}" for g in dict.fromkeys(GROUPS.values()))
SNAPS_FROM = 2013


def _fr(t):
    return FRANCHISE.get(t, t)


def load_snaps(seasons: list[int], refresh: bool | set[int] = False) -> pd.DataFrame:
    """game_id, team, player (gsis_id, or pfr id when unmatched), group, share (offense or defense snap %)."""
    ids = None

    def fetch(season):
        nonlocal ids
        if ids is None:
            ids = nfl.load_players().select("gsis_id", pl.col("pfr_id").alias("pfr_player_id")).drop_nulls().unique("pfr_player_id")
        s = nfl.load_snap_counts([season]).join(ids, on="pfr_player_id", how="left").to_pandas()
        grp = s["position"].map(POSITION_GROUPS).map(GROUPS)
        side_off = grp.isin(["ol", "skill", "rb"])
        df = pd.DataFrame({"game_id": s["game_id"], "team": s["team"].map(_fr),
                           "player": s["gsis_id"].fillna("pfr:" + s["pfr_player_id"].astype(str)), "group": grp,
                           "share": s["offense_pct"].where(side_off, s["defense_pct"]).astype(float)})
        return df[df["group"].notna()].drop_duplicates(["game_id", "player"])
    return per_season("snaps", [s for s in seasons if s >= SNAPS_FROM], fetch, refresh)


def load_reserve(seasons: list[int], refresh: bool | set[int] = False) -> pd.DataFrame:
    """Players on a reserve list (IR, PUP, NFI, suspended...) per team-week: season, week, team, gsis_id."""
    def fetch(season):
        r = nfl.load_rosters_weekly([season]).filter(pl.col("status").is_in(list(RESERVE))).to_pandas()
        return pd.DataFrame({"season": r["season"].astype(int), "week": r["week"].astype(int), "team": r["team"].map(_fr),
                             "gsis_id": r["gsis_id"]}).dropna().drop_duplicates()
    return per_season("reserve", seasons, fetch, refresh)


def absences(games: pd.DataFrame, snaps: pd.DataFrame, injuries: pd.DataFrame, reserve: pd.DataFrame,
             recent: int = RECENT_GAMES) -> pd.DataFrame:
    """One row per (game_id, team) with avail_<group> expected absences (starter-equivalents).
    Uses only snaps from the team's earlier games and this week's pre-game report/roster status."""
    status = injuries.set_index(["season", "week", "team", "gsis_id"])["report_status"].to_dict()
    res = set(map(tuple, reserve[["season", "week", "team", "gsis_id"]].to_numpy()))
    by_game = {k: g for k, g in snaps.groupby(["game_id", "team"])}
    rows = []
    hist: dict[str, deque] = defaultdict(lambda: deque(maxlen=recent))  # team -> recent games' (season, snaps)
    order = pd.concat([games[["game_id", "season", "week", "kickoff_utc", "home"]].rename(columns={"home": "team"}),
                       games[["game_id", "season", "week", "kickoff_utc", "away"]].rename(columns={"away": "team"})])
    for r in order.sort_values(["kickoff_utc", "game_id"]).itertuples(index=False):
        past = [g for s, g in hist[r.team] if s == r.season]
        if past and all(g.empty for g in past):
            past = []
        out = dict.fromkeys(FEATURES, 0.0)
        if past:
            share = pd.concat(past).groupby(["player", "group"])["share"].sum() / len(past)
            for (player, group), sh in share.items():
                if (r.season, r.week, r.team, player) in res:
                    p = 1.0
                else:
                    p = P_MISS.get(status.get((r.season, r.week, r.team, player)), 0.0)
                if p:
                    out[f"avail_{group}"] += p * sh
        rows.append({"game_id": r.game_id, "team": r.team, "has_history": bool(past), **out})
        # Every game enters the window (a game without snap rows counts as one where nobody played).
        hist[r.team].append((r.season, by_game.get((r.game_id, r.team), snaps.iloc[:0])))
    return pd.DataFrame(rows)


class AvailabilityAdjuster:
    """Game features for the walk-forward model: home absence minus away absence per group.
    Absences are precomputed point-in-time (each row uses only earlier games and pre-game reports)."""

    def __init__(self, table: pd.DataFrame):
        self.t = table.set_index(["game_id", "team"])[list(FEATURES)].to_dict("index")

    def features(self, g) -> dict[str, float]:
        h = self.t.get((g.game_id, g.home), dict.fromkeys(FEATURES, 0.0))
        a = self.t.get((g.game_id, g.away), dict.fromkeys(FEATURES, 0.0))
        return {f: h[f] - a[f] for f in FEATURES}
