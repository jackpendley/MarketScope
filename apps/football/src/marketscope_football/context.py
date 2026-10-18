"""Pre-game context per team per game (MS-028, ADR-032): rest, travel, time zones, altitude,
road streaks and coaching tenure. Everything here is known before kickoff (schedule, venue,
staff as of that week). Pure functions over pandas frames, unit-tested.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

from .coaching import slug
from .venues import haversine_km

FRANCHISE = {"OAK": "LV", "SD": "LAC", "STL": "LA"}
BYE_MIN_REST = 13  # days since the last game: a bye week (or longer)
SHORT_WEEK_MAX_REST = 5  # e.g. Thursday after Sunday (4 days)


def utc_offset_hours(tz: str, at: datetime) -> float:
    return at.astimezone(ZoneInfo(tz)).utcoffset().total_seconds() / 3600


def home_venues(games: pd.DataFrame) -> dict[tuple[int, str], str]:
    """(season, team) -> the venue of most of the team's non-neutral home games."""
    home = games[~games["neutral_site"]]
    out = {}
    for (season, team), grp in home.groupby(["season", "home_team"]):
        out[(season, team)] = grp["venue_key"].mode().iloc[0]
    return out


def tenure(series: list[tuple[str, str]]) -> list[int]:
    """For a franchise's games in order, each game's count of consecutive PRIOR games with the
    same coach (0 in a coach's first game)."""
    out, run, prev = [], 0, None
    for _, coach in series:
        run = run + 1 if coach == prev else 0
        out.append(run)
        prev = coach
    return out


def team_game_context(games: pd.DataFrame, venues: dict[str, dict], staff: list[dict],
                      prior_head_coaches: pd.DataFrame | None = None) -> pd.DataFrame:
    """`games`: one row per game (game_id, season, week, kickoff_utc, home_team, away_team,
    neutral_site, division_game, home_rest_days, away_rest_days, venue_key). `staff`:
    coaching_staff.csv rows. `prior_head_coaches` (optional): earlier seasons' games
    (kickoff_utc, team, coach) so head-coach tenure is not cut off at the first season."""
    games = games.sort_values("kickoff_utc").reset_index(drop=True)
    hv = home_venues(games)
    hc_week, off_week, def_week = {}, {}, {}
    for r in staff:
        for w in range(int(r["from_week"]), int(r["to_week"]) + 1):
            k = (int(r["season"]), r["team"], w)
            if r["role"] == "HC":
                hc_week[k] = slug(r["coach_name"])
            if r["offense_playcaller"] in ("True", True):
                off_week[k] = r["coach_id"]
            if r["defense_playcaller"] in ("True", True):
                def_week[k] = r["coach_id"]

    rows = []
    for g in games.itertuples(index=False):
        kickoff = pd.Timestamp(g.kickoff_utc).to_pydatetime()
        venue = venues[g.venue_key]
        for side in ("home", "away"):
            team = getattr(g, f"{side}_team")
            opp = g.away_team if side == "home" else g.home_team
            rest = getattr(g, f"{side}_rest_days")
            opp_rest = getattr(g, f"{'away' if side == 'home' else 'home'}_rest_days")
            home_key = hv.get((g.season, team), g.venue_key)
            home = venues[home_key]
            rows.append({
                "game_id": g.game_id, "season": g.season, "week": g.week, "team": team, "opponent": opp,
                "kickoff_utc": kickoff, "is_home": side == "home" and not g.neutral_site,
                "neutral_site": bool(g.neutral_site), "division_game": bool(g.division_game),
                "venue_key": g.venue_key, "roof_type": venue["roof_type"],
                "rest_days": None if pd.isna(rest) else int(rest),
                "rest_diff": None if pd.isna(rest) or pd.isna(opp_rest) else int(rest) - int(opp_rest),
                "bye_before": None if pd.isna(rest) else int(rest) >= BYE_MIN_REST,
                "short_week": None if pd.isna(rest) else int(rest) <= SHORT_WEEK_MAX_REST,
                "home_venue_key": home_key,
                "travel_km": round(haversine_km(float(home["lat"]), float(home["lon"]),
                                                float(venue["lat"]), float(venue["lon"])), 1),
                "tz_shift_hours": utc_offset_hours(venue["timezone"], kickoff) - utc_offset_hours(home["timezone"], kickoff),
                "body_clock_kickoff_hour": round(_local_hour(kickoff, home["timezone"]), 2),
                "venue_local_kickoff_hour": round(_local_hour(kickoff, venue["timezone"]), 2),
                "altitude_m": int(float(venue["elevation_m"])),
                "altitude_change_m": int(float(venue["elevation_m"])) - int(float(home["elevation_m"])),
                "hc_coach": hc_week.get((g.season, team, g.week)),
                "off_playcaller": off_week.get((g.season, team, g.week)),
                "def_playcaller": def_week.get((g.season, team, g.week)),
            })
    out = pd.DataFrame(rows)
    out["franchise"] = out["team"].map(lambda t: FRANCHISE.get(t, t))
    out = out.sort_values(["franchise", "kickoff_utc"]).reset_index(drop=True)

    # Road streak: consecutive games away from home (neutral counts as away), this one included.
    streak = []
    for _, grp in out.groupby("franchise", sort=False):
        run = 0
        for is_home in grp["is_home"]:
            run = 0 if is_home else run + 1
            streak.append(run)
    out["road_streak"] = streak

    # Coaching tenure in consecutive games with the franchise (prior seasons seed the head coach).
    prior = defaultdict(list)
    if prior_head_coaches is not None:
        for p in prior_head_coaches.sort_values("kickoff_utc").itertuples(index=False):
            prior[FRANCHISE.get(p.team, p.team)].append((p.kickoff_utc, slug(p.coach)))
    for col, out_col in (("hc_coach", "hc_tenure_games"), ("off_playcaller", "off_playcaller_tenure_games"),
                         ("def_playcaller", "def_playcaller_tenure_games")):
        values = []
        for franchise, grp in out.groupby("franchise", sort=False):
            seed = prior[franchise] if col == "hc_coach" else []
            series = seed + list(zip(grp["kickoff_utc"], grp[col].fillna("?")))
            t = tenure(series)[len(seed):]
            if not seed:
                # A run that began at the first game we have is a lower bound (left-censored).
                first_run = next((i for i, c in enumerate(grp[col].fillna("?")) if c != grp[col].iloc[0]), len(t))
                t = [None] * first_run + t[first_run:]
            values += t
        out[out_col] = pd.array(values, dtype="Int64")
    out["new_off_playcaller"] = (out["off_playcaller_tenure_games"] == 0).astype("boolean")
    out["new_def_playcaller"] = (out["def_playcaller_tenure_games"] == 0).astype("boolean")
    return out.drop(columns=["franchise"]).sort_values(["kickoff_utc", "game_id", "is_home"]).reset_index(drop=True)


def _local_hour(at: datetime, tz: str) -> float:
    local = at.astimezone(ZoneInfo(tz))
    return local.hour + local.minute / 60
