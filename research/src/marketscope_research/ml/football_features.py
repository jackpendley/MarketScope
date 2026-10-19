"""Point-in-time football features for each (game, snapshot t) row (MS-036, design_football.py).

Inputs (all teams as franchise codes):
- rows: event_id, t, consensus (board home spread at t)
- games: event_id, game_id, season, week, kickoff, home, away, neutral (the rows' games)
- schedule: season, week, game_id, kickoff, home, away (every game of the season, for rating
  availability and each team's previous games)
- ratings: season, week, team, adj_em (ratings-v1 snapshots; week 0 = preseason)
- snaps: game_id, team, gsis_id, share (max of offensive and defensive snap share)
- weather: game_id, lead_days, wind_mph (outdoor and retractable-roof games only)
- context: game_id, rest_diff (home minus away), away_travel_km, short_week_any
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .design_football import (
    HOME_ADVANTAGE,
    HURT_SHARE,
    RATING_LAG_HOURS,
    SNAPS_LAG_HOURS,
    STARTER_GAMES,
    STARTER_SHARE,
    WEATHER_LEADS,
)

HOUR = pd.Timedelta(hours=1)
COLUMNS = ["rating_gap", "abs_rating_gap", "starters_hurt_home", "starters_hurt_away", "starters_hurt_total",
           "starters_hurt_net", "wind_mph", "abs_wind_change", "outdoor", "rest_diff", "abs_rest_diff",
           "away_travel_km", "short_week_any"]


def rating_available_at(schedule: pd.DataFrame) -> pd.Series:
    """(season, week) -> when the snapshot after that week is usable: its last kickoff + lag."""
    return schedule.groupby(["season", "week"])["kickoff"].max() + RATING_LAG_HOURS * HOUR


def rating_margin(game, t: pd.Timestamp, ratings: pd.DataFrame, avail: pd.Series) -> float:
    """AdjEM(home) - AdjEM(away) + home advantage from the latest snapshot usable at t (week 0 is the
    preseason snapshot, usable all season). NaN if either team is missing."""
    usable = [k for (s, k), at in avail.items() if s == game.season and k < game.week and at <= t]
    week = max(usable, default=0)
    snap = ratings[(ratings["season"] == game.season) & (ratings["week"] == week)].set_index("team")["adj_em"]
    if game.home not in snap.index or game.away not in snap.index:
        return np.nan
    return float(snap[game.home] - snap[game.away] + (0.0 if game.neutral else HOME_ADVANTAGE))


def starters_hurt(team: str, season: int, t: pd.Timestamp, schedule: pd.DataFrame, snaps: pd.DataFrame) -> float:
    """Starters (average share >= STARTER_SHARE over up to STARTER_GAMES games before the team's most
    recent usable game, absences counted as 0) who played < HURT_SHARE in that most recent game.
    NaN when the team has no usable game before the most recent one."""
    played = schedule[(schedule["season"] == season) & ((schedule["home"] == team) | (schedule["away"] == team))
                      & (schedule["kickoff"] <= t - SNAPS_LAG_HOURS * HOUR)].sort_values("kickoff")
    if len(played) < 2:
        return np.nan
    last, prior = played["game_id"].iloc[-1], played["game_id"].iloc[-1 - STARTER_GAMES:-1].tolist()
    s = snaps[(snaps["team"] == team) & snaps["game_id"].isin(prior + [last])]
    share = s.pivot_table(index="gsis_id", columns="game_id", values="share", aggfunc="max")
    share = share.reindex(columns=prior + [last]).fillna(0.0)
    starters = share[share[prior].mean(axis=1) >= STARTER_SHARE]
    return float((starters[last] < HURT_SHARE).sum())


def weather_at(game_id: str, kickoff: pd.Timestamp, t: pd.Timestamp, weather: pd.DataFrame) -> tuple[float, float, int]:
    """(wind at the shortest usable lead, |change vs the next usable lead|, outdoor flag). Indoor
    games (no forecasts) get (0, 0, 0)."""
    w = weather[(weather["game_id"] == game_id) & weather["lead_days"].isin(WEATHER_LEADS)]
    if w.empty:
        return 0.0, 0.0, 0
    usable = w[kickoff - pd.to_timedelta(w["lead_days"], unit="D") <= t].sort_values("lead_days")
    if usable.empty:
        return np.nan, np.nan, 1
    winds = usable["wind_mph"].to_numpy(float)
    return float(winds[0]), float(abs(winds[0] - winds[1])) if len(winds) > 1 else 0.0, 1


def build_football_features(rows: pd.DataFrame, games: pd.DataFrame, schedule: pd.DataFrame,
                            ratings: pd.DataFrame, snaps: pd.DataFrame, weather: pd.DataFrame,
                            context: pd.DataFrame) -> pd.DataFrame:
    """rows + COLUMNS, one output row per input row (same order)."""
    avail = rating_available_at(schedule)
    g_by_event = games.set_index("event_id")
    ctx = context.set_index("game_id")
    out = []
    for r in rows.itertuples(index=False):
        g = g_by_event.loc[r.event_id]
        rm = rating_margin(g, r.t, ratings, avail)
        gap = rm + r.consensus  # rating margin - consensus margin, consensus margin = -home spread
        hh = starters_hurt(g.home, g.season, r.t, schedule, snaps)
        ha = starters_hurt(g.away, g.season, r.t, schedule, snaps)
        wind, dwind, outdoor = weather_at(g.game_id, g.kickoff, r.t, weather)
        c = ctx.loc[g.game_id] if g.game_id in ctx.index else None
        rest = float(c["rest_diff"]) if c is not None and pd.notna(c["rest_diff"]) else np.nan
        out.append({"rating_gap": gap, "abs_rating_gap": abs(gap), "starters_hurt_home": hh, "starters_hurt_away": ha,
                    "starters_hurt_total": hh + ha, "starters_hurt_net": ha - hh, "wind_mph": wind,
                    "abs_wind_change": dwind, "outdoor": outdoor, "rest_diff": rest, "abs_rest_diff": abs(rest),
                    "away_travel_km": float(c["away_travel_km"]) if c is not None else np.nan,
                    "short_week_any": float(c["short_week_any"]) if c is not None else np.nan})
    return pd.concat([rows.reset_index(drop=True), pd.DataFrame(out, columns=COLUMNS)], axis=1)
