"""MS-057 does the market move toward the ratings model from early in the week? (research/
PREREGISTRATION.md Addendum O). Read-only.

    STUDY_DATABASE_URL=... .venv/bin/python -m marketscope_research.run_model_open --phase discovery \
        --out reports/model-open-discovery.md
"""

from __future__ import annotations

import argparse
import os
import subprocess
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from . import evaluation as ev
from . import fair_value as fv
from . import injury_windows as iw
from . import model_open as mo
from . import sharp_market as sm
from .data import _frame, connect
from .ml import design_football
from .run_football_studies import ci, table

FR = "(SELECT franchise FROM nfl_teams WHERE abbr = {})"


def load(conn):
    schedule = _frame(conn, f"""
        SELECT game_id, season, week, kickoff_utc AS kickoff, {FR.format('home_team')} AS home,
               {FR.format('away_team')} AS away, neutral_site AS neutral, event_id::text AS event_id,
               home_score IS NOT NULL AS final
        FROM nfl_games WHERE season = 2026 AND game_type = 'REG'""")
    schedule["kickoff"] = pd.to_datetime(schedule["kickoff"], utc=True)
    ratings = _frame(conn, f"""
        SELECT season, week, {FR.format('team')} AS team, adj_em FROM rating_snapshots
        WHERE model_version = %s AND season = 2026""", (design_football.RATING_VERSION,))
    events = [e for e in schedule["event_id"].dropna()]
    moves = _frame(conn, """
        SELECT event_id::text, bookmaker_key, changed_at, point::float8 AS point, price1, price2,
               limit1::float8 AS limit1
        FROM line_moves WHERE market_type = 'spreads' AND bookmaker_key = 'pinnacle'
          AND event_id = ANY(%s::uuid[])""", (events,))
    moves["changed_at"] = pd.to_datetime(moves["changed_at"], utc=True)
    history = _frame(conn, """
        SELECT season, nflverse_close_home_spread::float8 AS home_line, nflverse_close_total::float8 AS total,
               (home_score - away_score)::float8 AS margin, (home_score + away_score)::float8 AS points
        FROM nfl_games WHERE season BETWEEN 2016 AND 2025 AND home_score IS NOT NULL
          AND nflverse_close_home_spread IS NOT NULL AND nflverse_close_total IS NOT NULL""")
    return schedule, ratings, moves, history


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", choices=["discovery", "confirmation"], default="discovery")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    dsn = os.environ.get("STUDY_DATABASE_URL")
    if not dsn:
        raise SystemExit("Set STUDY_DATABASE_URL (read-only use).")
    with connect(dsn) as conn:
        schedule, ratings, moves, history = load(conn)
    tl = sm.timelines(moves)
    frame = mo.model_frame(schedule, ratings, tl)  # rating availability uses the whole season's schedule
    kicks = schedule.dropna(subset=["event_id"]).set_index("event_id")["kickoff"]
    in_phase = kicks < sm.DISCOVERY_END if args.phase == "discovery" else \
        (kicks >= sm.DISCOVERY_END) & (kicks < sm.CONFIRMATION_END)
    final = set(schedule.loc[schedule["final"], "event_id"].dropna())
    frame = frame[frame["event_id"].isin(set(kicks[in_phase].index) & final)]

    # The seeded bootstrap resamples rows by position: sort so it doesn't depend on SQL row order.
    frame = frame.sort_values("event_id").reset_index(drop=True)
    e1 = iw.slope_ci(frame, "y", "x") if len(frame) > 2 else None

    # Addendum V: the shared early line, a market-only baseline, frozen-first and week-block sensitivities.
    based = mo.add_baseline(frame, schedule, mo.closes_frame(schedule, tl))
    with_b = based.dropna(subset=["xb"]).reset_index(drop=True)
    joint = ev.ols_ci(with_b, "y", ["x", "xb"]) if len(with_b) > 3 else None
    base_only = ev.ols_ci(with_b, "y", ["xb"])[0] if len(with_b) > 2 else None
    null = mo.joint_permutation(with_b) if len(with_b) > 3 else None  # Addendum W
    beats_null = bool(joint and null is not None and joint[0].value > np.nanquantile(null, 0.975))
    perm = mo.permutation_slopes(frame) if len(frame) > 2 else None
    frame_k = frame.assign(decision_at=frame["event_id"].map(kicks) - mo.LEAD)
    first = ev.frozen_first(frame_k, "decision_at", "O")
    e_first = ev.ols_ci(first, "y", ["x"])[0] if len(first) > 2 else None
    e_week = ev.ols_ci(frame, "y", ["x"], cluster="week")[0] if frame["week"].nunique() > 2 else None
    engine = fv.load_engine(history)
    vals = mo.model_side_values(frame, tl, kicks, engine)
    e2 = sm.ratio_bootstrap(vals.assign(v=vals["value"]), "v") if len(vals) else None
    vals3 = mo.model_side_values(frame, tl, kicks, fv.load_engine(history, v3=True))  # Addendum T secondary
    e3 = sm.ratio_bootstrap(vals3.assign(v=vals3["value"]), "v") if len(vals3) else None

    def verdict(e, claim):
        if e is None:
            return "inconclusive (no games)"
        tag = " (discovery result; confirmation on weeks 7–14 decides)" if args.phase == "discovery" else ""
        return f"**{claim}**{tag}" if e.low > 0 else ("**the opposite**" + tag if e.high < 0 else
                                                       "not distinguishable: no claim")

    def vci(e):
        return "–" if e is None else f"{e.value:+.3f} ({e.low:+.3f} to {e.high:+.3f}; {e.clusters} clusters)"

    def pct(e):
        return "–" if e is None else f"{100 * e.value:+.1f}% ({100 * e.low:+.1f} to {100 * e.high:+.1f})"

    # Exploratory (added after the first run): value by size of the disagreement.
    by_size = []
    allv = mo.model_side_values(frame.assign(x=frame["x"]), tl, kicks, engine)
    xs = frame.set_index("event_id")["x"].abs()
    allv["absx"] = allv["event_id"].map(xs)
    for lo, hi in ((1.5, 2.5), (2.5, 3.5), (3.5, 99)):
        d = allv[(allv["absx"] >= lo) & (allv["absx"] < hi)]
        by_size.append([f"{lo}–{hi if hi < 99 else '+'}", len(d), pct(sm.ratio_bootstrap(d.assign(v=d["value"]), "v"))
                        if len(d) else "–"])

    commit = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True).strip()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    parts = [
        f"# Does the market move toward the model? {args.phase} (MS-057)", "",
        f"_Generated {now} · commit `{commit}` · reproduce with "
        f"`research/src/marketscope_research/run_model_open.py --phase {args.phase}`._", "",
        "Design pre-registered in `research/PREREGISTRATION.md` (Addendum O, committed before this code). Decision time "
        "6 days before kickoff; the model line is ratings-only (AdjEM gap plus 1.6 home advantage) from the latest "
        "snapshot usable then. Game bootstrap (5,000, seed 2026). **Analysis, not betting advice.**", "",
        f"**Sample:** {len(frame)} games. Mean |disagreement| {frame['x'].abs().mean():.2f} points; mean |move to the "
        f"close| {frame['y'].abs().mean():.2f} points; lines unchanged from 6 days out: {(frame['y'] == 0).mean():.0%}.",
        "",
        "## Primary: slope of Pinnacle's move to the close on the model's disagreement", "",
        f"Slope: {ci(e1, 3)} points of move per point of disagreement. **Primary result:** "
        f"{verdict(e1, 'the market moves toward the model')}.", "",
        "## Addendum V: is it the model, or the early line?", "",
        "y and x share Pinnacle's line at d, so noise in that line alone makes the slope positive. The baseline is "
        "the market's own view before d: team ratings fitted to Pinnacle's closing lines of games already final. "
        + ("Discovery numbers are descriptive; confirmation decides." if args.phase == "discovery" else
           "The joint regression is the Addendum V secondary."), "",
        f"- Games: {len(frame)} in {frame['week'].nunique()} weeks; {len(with_b)} with a baseline (week 1 has none).",
        f"- Joint regression, model coefficient: {vci(joint[0] if joint else None)}; baseline coefficient: "
        f"{vci(joint[1] if joint else None)}. "
        + ("**The ratings add information beyond the market's earlier closes.**"
           if joint and joint[0].low > 0 and beats_null else
           # Addendum V suggested "no more than toward its own earlier lines" here; that overstates when the
           # baseline coefficient is itself near 0 and the model's interval is merely wide (ADR-069).
           "Not established beyond the market's own earlier closes: the model coefficient's interval includes 0 "
           "or it does not beat the permutation null."
           if joint else "No claim."),
        f"- Addendum W null, the model coefficient with model lines shuffled within weeks (1,000 permutations): "
        f"97.5th percentile {np.nanquantile(null, 0.975):+.3f}; the observed coefficient "
        f"{'exceeds' if beats_null else 'does not exceed'} it." if null is not None else "- Addendum W null: –",
        f"- Baseline alone: {vci(base_only)}.",
        f"- Model lines shuffled within each week (1,000 permutations): mean slope "
        f"{np.nanmean(perm):+.3f}, 95% of permutations {np.nanquantile(perm, 0.025):+.3f} to "
        f"{np.nanquantile(perm, 0.975):+.3f}." if perm is not None else "- Permutations: –",
        f"- Frozen first (decisions after Addendum O was committed): {vci(e_first)} over {len(first)} games.",
        f"- Week-block bootstrap of the primary slope: {vci(e_week)}.", "",
        "## Secondary: the model's side at Pinnacle's line 6 days out (|disagreement| ≥ 1.5)", "",
        f"{len(vals)} positions. Mean value at Pinnacle's no-vig close: {pct(e2)}. Secondary: "
        f"{verdict(e2, 'taking the model side early carries positive value')}.", "",
        "Engine v3 (Addendum T secondary; MS-059 line conversion, logit scale): "
        f"{pct(e3)}" + (" (post hoc on discovery games: descriptive only)." if args.phase == "discovery" else "."), "",
        "## Exploratory: value by size of the disagreement (added after the first run)", "",
        table(by_size, ["Disagreement size (points)", "Positions", "Value at Pinnacle's close"]), "",
        "## What this can't see", "",
        "Injury and QB news (the model line here is ratings-only); openers more than 14 days out; earlier seasons "
        "(no early lines before 2026 without paid history).", "",
    ]
    with open(args.out, "w") as fh:
        fh.write("\n".join(parts))
    print("\n".join(p for p in parts if "result" in p.lower() and "**" in p or p.startswith("**Sample") or
                    p.startswith(str(len(vals)))))


if __name__ == "__main__":
    main()
