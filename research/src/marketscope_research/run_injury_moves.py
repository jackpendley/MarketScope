"""Research study R2w, market moves on newly confirmed absences (2026 weeks 1–6; PREREGISTRATION.md,
addendum B). Read-only.

    STUDY_DATABASE_URL=... .venv/bin/python -m marketscope_research.run_injury_moves --out reports/r2w-injury-moves.md
"""

from __future__ import annotations

import argparse
import os
import subprocess
from datetime import datetime, timezone

from . import football_studies as fs
from .consensus import consensus_series
from .data import _frame, connect
from .run_football_studies import ci, load

WEEKS = range(1, 7)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    dsn = os.environ.get("STUDY_DATABASE_URL")
    if not dsn:
        raise SystemExit("Set STUDY_DATABASE_URL (read-only use).")
    with connect(dsn) as conn:
        games, _, _, spreads, _, kickoffs = load(conn)
        final = _frame(conn, """
            SELECT DISTINCT ON (season, week, team, gsis_id) season, week,
                   (SELECT franchise FROM nfl_teams WHERE abbr = team) AS team, gsis_id, position, report_status
            FROM nfl_injury_reports WHERE season = 2026 AND game_type = 'REG' AND gsis_id IS NOT NULL
            ORDER BY season, week, team, gsis_id, id DESC""")
        snaps = _frame(conn, """
            SELECT season, week, (SELECT franchise FROM nfl_teams WHERE abbr = team) AS team, gsis_id,
                   offense_pct, defense_pct
            FROM nfl_player_game_snaps WHERE season = 2026 AND gsis_id IS NOT NULL""")
    g26 = games[(games["season"] == 2026) & (games["game_type"] == "REG") & games["week"].isin(WEEKS)
                & games["event_id"].notna()]
    leads = fs.consensus_at_leads(consensus_series(spreads[spreads["event_id"].isin(g26["event_id"])]), kickoffs)
    m = g26.merge(leads, on="event_id").dropna(subset=["6 days", "close"])
    m["move"] = (-m["close"]) - (-m["6 days"])  # margin orientation: + = toward home
    events = fs.injury_events(final, snaps)
    events = events[events["week"].isin(WEEKS)]
    r = fs.r2w(m[["season", "week", "home", "away", "move"]], events)

    commit = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True).strip()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    if not r["gate"]:
        verdict = "inconclusive (gate not met)"
    else:
        e = r["slope"]
        verdict = ("**the consensus moves toward the injured team's opponent**" if e.low > 0 else
                   "**the consensus moves toward the injured team**" if e.high < 0 else
                   "not distinguishable from zero: no claim")
    parts = [
        "# R2w: market moves on newly confirmed absences, 2026 weeks 1–6 (MS-035c)", "",
        f"_Generated {now} · commit `{commit}` · reproduce with "
        "`research/src/marketscope_research/run_injury_moves.py`._", "",
        "Design pre-registered in `research/PREREGISTRATION.md` (addendum B, committed before this code). "
        "Event: a starter (≥ 50% of snaps over his recent games) listed Out on the final injury report who "
        "played the team's previous game. Outcome: board-consensus margin move from 6 days out to the close. "
        "95% intervals resample games (5,000 draws). Information already priced 6 days out is not visible here. "
        "Market data; not betting advice.", "",
        "## Primary: consensus move per net newly-out starter", "",
        f"{r['games']} games with a 6-day and closing consensus; {r['events']} events in them "
        f"({r['games_with_events']} games with at least one), {r['qb_events']} QB events. "
        f"Gate: {fs.R2W_MIN_EVENTS} events ({'met' if r['gate'] else 'not met'}).", "",
        f"Slope: {ci(r.get('slope'))} points of line move toward the opponent per event. Result: {verdict}.", "",
        "## Robustness (added after seeing the primary result)", "",
        f"Counting non-QB events only: {ci(r.get('slope_non_qb'))} points per event. Not pre-registered; it checks "
        "that the primary slope does not rest on the few QB games.", "",
        "## QB events (exploratory)", "",
        (f"QB claim gate ({fs.R2W_MIN_QB}) {'met' if r['qb_gate'] else 'not met'}. Moves toward the opponent of "
         f"the team missing its QB, game by game: {', '.join(f'{x:+.1f}' for x in r['qb_moves']) or 'none'}."), "",
    ]
    with open(args.out, "w") as f:
        f.write("\n".join(parts))
    print("\n".join(parts[6:12]))


if __name__ == "__main__":
    main()
