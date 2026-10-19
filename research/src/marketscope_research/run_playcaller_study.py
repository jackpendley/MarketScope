"""Research study R7, play-caller impact 2016–24 (PREREGISTRATION.md, R7 and addendum A). Read-only.

    STUDY_DATABASE_URL=... .venv/bin/python -m marketscope_research.run_playcaller_study --out reports/r7-play-caller.md
"""

from __future__ import annotations

import argparse
import os
import subprocess
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from . import football_studies as fs
from .data import _frame, connect
from .run_football_studies import ci, table

TRAITS = {"proe": "Pass rate over expected (pts of %)", "neutral_seconds_per_play": "Neutral seconds per play"}


def load(conn):
    franchise = "(SELECT franchise FROM nfl_teams WHERE abbr = {})"
    team_games = _frame(conn, f"""
        SELECT s.season, {franchise.format('s.team')} AS team, {franchise.format('s.opponent')} AS opponent,
               s.drives, s.drive_points, s.plays, s.proe, s.neutral_seconds_per_play
        FROM nfl_team_game_stats s
        WHERE s.season_type = 'REG' AND s.season BETWEEN 2016 AND 2024""")
    staff = _frame(conn, f"""
        SELECT season, {franchise.format('team')} AS team, coach_id, from_week, to_week,
               offense_playcaller, defense_playcaller
        FROM nfl_coaching_staff WHERE season BETWEEN 2016 AND 2024""")
    starts = _frame(conn, f"""
        SELECT season, week, {franchise.format('home_team')} AS team, home_qb_id AS qb_id FROM nfl_games
        WHERE game_type = 'REG' AND season BETWEEN 2016 AND 2024 AND home_score IS NOT NULL
        UNION ALL
        SELECT season, week, {franchise.format('away_team')}, away_qb_id FROM nfl_games
        WHERE game_type = 'REG' AND season BETWEEN 2016 AND 2024 AND home_score IS NOT NULL""")
    return team_games, staff, starts


def traits(team_games: pd.DataFrame) -> pd.DataFrame:
    """Play-weighted team-season means of the scheme traits."""
    out = []
    for (s, t), g in team_games.groupby(["season", "team"]):
        row = {"season": s, "team": t}
        for c in TRAITS:
            ok = g[c].notna()
            row[c] = float(np.average(g.loc[ok, c], weights=g.loc[ok, "plays"])) if ok.any() else np.nan
        out.append(row)
    return pd.DataFrame(out)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    dsn = os.environ.get("STUDY_DATABASE_URL")
    if not dsn:
        raise SystemExit("Set STUDY_DATABASE_URL (read-only use).")
    with connect(dsn) as conn:
        team_games, staff, starts = load(conn)
    units = fs.season_units(team_games)
    pairs = fs.r7_pairs(units, staff, starts)
    r = fs.r7_carryover(pairs)
    movers = fs.scheme_movers(traits(team_games), fs.main_caller(staff, "offense"))
    scheme = {c: fs.r7_scheme(movers.dropna(subset=[f"{c}_caller", f"{c}_prior", f"{c}_new"]), c) for c in TRAITS}

    commit = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True).strip()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    e = r["interaction"]
    verdict = ("inconclusive (gate not met)" if not r["gate"] else
               "**continuity effect: more carryover when the play-caller stays**" if e.low > 0 else
               "**continuity effect: less carryover when the play-caller stays**" if e.high < 0 else
               "not distinguishable from zero: no claim")
    label = {(True, True): "same caller, same QB", (True, False): "same caller, new QB",
             (False, True): "new caller, same QB", (False, False): "new caller, new QB"}
    parts = [
        "# R7: play-caller impact, 2016–24 (MS-035b)", "",
        f"_Generated {now} · commit `{commit}` · reproduce with "
        "`research/src/marketscope_research/run_playcaller_study.py`._", "",
        "Design pre-registered in `research/PREREGISTRATION.md` (R7 and addendum A, committed before this code). "
        "Measure: observed offensive points per drive for the regular season, centred on the league mean "
        "(not the filtered ratings, whose between-season reversion already depends on play-caller continuity). "
        "95% intervals resample team-season pairs (5,000 draws). Descriptive research; coach and roster effects "
        "are confounded.", "",
        "## Primary: extra carryover when the offensive play-caller stays", "",
        f"{r['pairs']} team-season pairs; {r['changed_caller']} with a new offensive play-caller, {r['changed_qb']} "
        f"with a new main QB (gate: at least {fs.R7_MIN_CHANGED} each: {'met' if r['gate'] else 'not met'}).", "",
        f"Model: next season's offence = a + b·this season's + c·same caller + d·same QB + e·(this season's × same "
        f"caller) + f·(this season's × same QB).", "",
        table([["e: × same play-caller (primary)", ci(e), e.excludes_zero()],
               ["f: × same QB", ci(r["qb_interaction"]), r["qb_interaction"].excludes_zero()],
               ["Carryover, all pairs (simple slope)", ci(r["overall"]), r["overall"].excludes_zero()]],
              ["Term", "Estimate (95% CI)", "vs 0"]), "",
        f"Result: {verdict}.", "",
        "## Carryover by group (exploratory)", "",
        "Slope of next season's points per drive on this season's (1 = fully kept, 0 = none).", "",
        table([[label[(g["same_caller"], g["same_qb"])], g["pairs"], ci(g["slope"])] for g in
               sorted(r["groups"], key=lambda g: (not g["same_caller"], not g["same_qb"]))],
              ["Group", "Pairs", "Carryover (95% CI)"]), "",
        "## Defence (exploratory)", "",
        f"Points per drive allowed; same defensive play-caller ({r['defense']['changed']} pairs changed). No QB term.", "",
        table([["Carryover, same defensive caller", ci(r["defense"]["same"])],
               ["Carryover, new defensive caller", ci(r["defense"]["changed_slope"])],
               ["Interaction (× same caller)", ci(r["defense"]["interaction"])]], ["Term", "Estimate (95% CI)"]), "",
        "## Scheme: does it follow the play-caller? (exploratory)", "",
        "Play-callers who were a team's main offensive caller in one season and a different team's in the next. "
        "Regression of the new team's value on the caller's old-team value and the new team's own prior value.", "",
        table([[TRAITS[c], s["movers"], ci(s["caller"]), ci(s["prior"])] for c, s in scheme.items()],
              ["Trait", "Movers", "Weight on caller's old team", "Weight on new team's prior"]), "",
    ]
    with open(args.out, "w") as f:
        f.write("\n".join(parts))
    print("\n".join(parts[8:22]))


if __name__ == "__main__":
    main()
