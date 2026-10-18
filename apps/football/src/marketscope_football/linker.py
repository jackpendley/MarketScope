"""Link odds events (The Odds API / OddsPapi) to nflverse games.

A match needs the same home AND away team (by exact name -> abbreviation) and kickoffs within
36 hours (flexed games move by hours, not days). Orientation is never repaired: if the feed's
home team is nflverse's away team, the event is reported, not linked, because every spread in
MarketScope is home-oriented and a silent swap would invert them.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

MAX_KICKOFF_GAP = pd.Timedelta(hours=36)


@dataclass
class LinkResult:
    links: list[tuple[str, str]] = field(default_factory=list)  # (game_id, event_id)
    issues: list[dict] = field(default_factory=list)  # {event_id, reason, detail}


def match_events(events: pd.DataFrame, games: pd.DataFrame, name_to_abbr: dict[str, str]) -> LinkResult:
    """events: event_id, home_team, away_team, commence_time (UTC).
    games: game_id, home_team, away_team, kickoff_utc (UTC), abbreviations."""
    result = LinkResult()
    taken: set[str] = set()
    for ev in events.sort_values("commence_time").itertuples(index=False):
        home, away = name_to_abbr.get(ev.home_team), name_to_abbr.get(ev.away_team)
        if home is None or away is None:
            result.issues.append({"event_id": ev.event_id, "reason": "unknown_team",
                                  "detail": f"{ev.away_team} @ {ev.home_team}"})
            continue
        near = games[(games["kickoff_utc"] - ev.commence_time).abs() <= MAX_KICKOFF_GAP]
        same = near[(near["home_team"] == home) & (near["away_team"] == away) & ~near["game_id"].isin(taken)]
        if len(same) == 1:
            gid = same.iloc[0]["game_id"]
            taken.add(gid)
            result.links.append((gid, ev.event_id))
            continue
        if len(same) > 1:
            result.issues.append({"event_id": ev.event_id, "reason": "ambiguous", "detail": ", ".join(same["game_id"])})
            continue
        swapped = near[(near["home_team"] == away) & (near["away_team"] == home)]
        reason = "swapped_orientation" if len(swapped) else "no_game"
        result.issues.append({"event_id": ev.event_id, "reason": reason, "detail": f"{away} @ {home}"})
    return result
