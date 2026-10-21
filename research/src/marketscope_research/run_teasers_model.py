"""MS-055a model-priced teaser legs (research/PREREGISTRATION.md Addendum N). Read-only.

    STUDY_DATABASE_URL=... .venv/bin/python -m marketscope_research.run_teasers_model --out reports/teasers-model.md

Hypothetical results on closing lines; not betting advice.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from datetime import datetime, timezone

import pandas as pd

from . import backtest as bt
from . import systems as sy
from . import teasers_model as tm
from .data import _frame, connect
from .run_fair_value import PARAMS
from .run_football_studies import table


def load(conn) -> pd.DataFrame:
    g = _frame(conn, """
        SELECT game_id, season, week, kickoff_utc AS kickoff, home_team AS home, away_team AS away,
               nflverse_close_home_spread::float8 AS home_line, nflverse_close_total::float8 AS total,
               (home_score - away_score)::float8 AS margin, (home_score + away_score)::float8 AS points
        FROM nfl_games WHERE season BETWEEN 2016 AND 2025 AND home_score IS NOT NULL
          AND nflverse_close_home_spread IS NOT NULL AND nflverse_close_total IS NOT NULL""")
    g["kickoff"] = pd.to_datetime(g["kickoff"], utc=True)
    return g


def rate(legs: pd.DataFrame):
    return bt.cluster_mean_ci((legs["result"] == "win").astype(float), legs["game_id"]) if len(legs) else None


def fmt(e):
    return "–" if e is None else f"{100 * e.value:.1f}% ({100 * e.low:.1f}–{100 * e.high:.1f}%), {e.n} legs"


def roi(legs: pd.DataFrame, price: int) -> str:
    t = bt.pair_chronological(legs)
    if t.empty:
        return "–"
    u = bt.score_teasers(t, price, "loses")
    e = bt.cluster_mean_ci(u, t["season"].astype(str) + "-" + t["week"].astype(str))
    return f"{100 * e.value:+.1f}% ({100 * e.low:+.1f} to {100 * e.high:+.1f}), {len(t)} teasers"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    dsn = os.environ.get("STUDY_DATABASE_URL")
    if not dsn:
        raise SystemExit("Set STUDY_DATABASE_URL (read-only use).")
    with connect(dsn) as conn:
        games = load(conn)
    p = json.loads(PARAMS.read_text())["margin"]
    legs = tm.leg_frame(games, 2018, p["h_s"], p["h_t"])
    be125, be120 = bt.teaser_break_even(-125), bt.teaser_break_even(-120)
    sel = tm.select_legs(legs, -125)
    sel120 = tm.select_legs(legs, -120)
    late, early = sel[sel["season"] >= 2023], sel[sel["season"] < 2023]
    e = rate(late)
    if e is None:
        verdict = "inconclusive (no legs)"
    elif e.low > be125:
        verdict = "**model-selected legs beat the −125 break-even**"
    elif e.high < be125:
        verdict = "**model-selected legs fall short of the −125 break-even**"
    else:
        verdict = "not distinguishable from the −125 break-even: no claim"

    wong = sy.wong_legs(games[games["season"] >= 2018], "V0").rename(columns={"team": "team"})
    by_season = [[s, len(d), f"{(d['result'] == 'win').mean():.1%}", f"{d['p'].mean():.1%}"]
                 for s, d in sel.groupby("season")]
    by_line = [[f"{line:+.1f}", len(d), f"{(d['result'] == 'win').mean():.1%}", f"{d['p'].mean():.1%}"]
               for line, d in sel.groupby("line") if len(d) >= 10]

    commit = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True).strip()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    parts = [
        "# Model-priced teaser legs, \"Wong 2.0\" (MS-055a)", "",
        f"_Generated {now} · commit `{commit}` · reproduce with `research/src/marketscope_research/run_teasers_model.py`._",
        "",
        "Design pre-registered in `research/PREREGISTRATION.md` (Addendum N, committed before this code). Each team's "
        "6-point teased line is priced with the fair-value engine's margin distribution (fitted only on earlier "
        "seasons, calibrated so the nflverse close is the median); legs at or above the −125 break-even "
        f"({be125:.2%}) are selected, one per game. A push counts as a loss. Game bootstrap (5,000, seed 2026). "
        "**Hypothetical results on closing lines; not betting advice.**", "",
        "## Primary: 2023–25 (out of sample for the model and its bandwidths)", "",
        f"Selected legs: {fmt(e)}. Mean model probability {late['p'].mean():.1%}. Result: {verdict}.", "",
        "## Secondary", "",
        f"- 2018–22: {fmt(rate(early))}. 2018–25: {fmt(rate(sel))}.",
        f"- Teasers at −125, chronological: 2023–25 {roi(late, -125)}; 2018–25 {roi(sel, -125)}.",
        f"- Selection at the −120 break-even ({be120:.2%}): 2018–25 {fmt(rate(sel120))}; teasers at −120 "
        f"{roi(sel120, -120)}.",
        f"- Wong V0 legs over the same seasons (2018–25): {fmt(rate(wong))}.", "",
        table(by_season, ["Season", "Selected legs", "Won", "Mean model probability"]), "",
        "Selected legs by original line (10 or more):", "",
        table(by_line, ["Line", "Legs", "Won", "Mean model probability"]), "",
        "## What this can't see", "",
        "Prices before the close; each book's teaser rules beyond a push losing; the 2026 season (tracked forward in "
        "the paper portfolio as `wong-model`).", "",
    ]
    with open(args.out, "w") as fh:
        fh.write("\n".join(parts))
    print("\n".join(parts[6:9]))


if __name__ == "__main__":
    main()
