"""MS-045a system catalogue F1–F10 (research/PREREGISTRATION.md Addendum F). Read-only.

    STUDY_DATABASE_URL=... .venv/bin/python -m marketscope_research.run_catalogue \
        --out reports/systems-catalogue.md --web-json ../apps/web/lib/generated/systems-catalogue.json

Hypothetical analysis of historical closing lines at -110, not betting advice.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from datetime import datetime, timezone

import pandas as pd
from scipy.stats import binomtest

from . import backtest as bt
from . import systems as sy
from .data import _frame, connect
from .run_football_studies import table

SIDE_FIELDS = {"rest_days": "rest", "bye_before": "bye", "short_week": "short", "travel_km": "travel_km",
               "tz_shift_hours": "tz_shift", "body_clock_kickoff_hour": "body_clock", "altitude_change_m": "alt_change"}


def attach_context(games: pd.DataFrame, ctx: pd.DataFrame) -> pd.DataFrame:
    """Add each side's pre-kickoff context as home_*/away_* columns, matched on the TEAM (not the
    is_home flag, which is false for both teams at a neutral site)."""
    g = games
    for prefix, col in (("home_", "home"), ("away_", "away")):
        side = ctx.rename(columns={"team": col})
        g = g.merge(side.rename(columns={c: prefix + c for c in side.columns if c not in ("game_id", col)}),
                    on=["game_id", col], how="left")
    for c in ("home_bye", "away_bye", "home_short", "away_short"):
        g[c] = g[c].fillna(False).astype(bool)
    g["away_body_clock"] = g["away_body_clock"].fillna(13.0)
    return g


def load_games(conn, seasons: tuple[int, int]) -> pd.DataFrame:
    g = _frame(conn, """
        SELECT game_id, season, week, kickoff_utc AS kickoff, home_team AS home, away_team AS away,
               neutral_site AS neutral, division_game AS division,
               nflverse_close_home_spread::float8 AS home_line, nflverse_close_total::float8 AS total,
               (home_score - away_score)::float8 AS margin, (home_score + away_score)::float8 AS points,
               extract(hour from kickoff_utc AT TIME ZONE 'America/New_York')::int AS et_hour
        FROM nfl_games
        WHERE season BETWEEN %s AND %s AND home_score IS NOT NULL
          AND nflverse_close_home_spread IS NOT NULL AND nflverse_close_total IS NOT NULL""", seasons)
    ctx = _frame(conn, f"""
        SELECT game_id, team, {", ".join(SIDE_FIELDS)} FROM nfl_game_context
        WHERE season BETWEEN %s AND %s""", seasons)
    g = attach_context(g, ctx.rename(columns=SIDE_FIELDS))
    g["kickoff"] = pd.to_datetime(g["kickoff"], utc=True)
    return g


def summarise(pos: pd.DataFrame) -> dict:
    decided = pos[pos["result"] != "push"]
    wins = int((decided["result"] == "win").sum())
    n = len(decided)
    units = pos["result"].map({"win": bt.profit(-110), "loss": -1.0, "push": 0.0})
    late = decided[decided["season"] >= 2024]
    return {
        "positions": len(pos), "decided": n, "wins": wins,
        "rate": bt.cluster_mean_ci((decided["result"] == "win").astype(float), decided["game_id"]) if n else None,
        "p": binomtest(wins, n, sy.BREAK_EVEN_110, alternative="greater").pvalue if n else 1.0,
        "late_rate": float((late["result"] == "win").mean()) if len(late) else float("nan"),
        "late_n": len(late),
        "roi": bt.cluster_mean_ci(units, pos["game_id"]) if len(pos) else None,
        "units": float(units.sum()),
        "season_units": {int(s): round(float(u.sum()), 2) for s, u in units.groupby(pos["season"])},
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--web-json")
    args = ap.parse_args()
    dsn = os.environ.get("STUDY_DATABASE_URL")
    if not dsn:
        raise SystemExit("Set STUDY_DATABASE_URL (read-only use).")
    with connect(dsn) as conn:
        games = load_games(conn, (2016, 2025))

    pos = pd.concat([sy.rule_positions(games), sy.f10_positions(games)], ignore_index=True)
    stats = {k: summarise(pos[pos["system"] == k]) for k in sy.CATALOGUE}
    passed = sy.holm({k: s["p"] for k, s in stats.items()})
    for k, s in stats.items():
        s["holm"] = bool(passed[k])
        s["supported"] = bool(passed[k] and s["late_rate"] > sy.BREAK_EVEN_110)

    def rate(e):
        return "–" if e is None else f"{100 * e.value:.1f}% ({100 * e.low:.1f}–{100 * e.high:.1f}%)"

    rows = []
    for k, s in stats.items():
        rows.append([f"{k} {sy.CATALOGUE[k]}", s["decided"], rate(s["rate"]), f"{s['p']:.3f}",
                     "yes" if s["holm"] else "no", f"{100 * s['late_rate']:.1f}% ({s['late_n']})",
                     f"{100 * s['roi'].value:+.1f}% ({100 * s['roi'].low:+.1f} to {100 * s['roi'].high:+.1f})",
                     "**supported**" if s["supported"] else "no claim"])
    seasons = sorted({y for s in stats.values() for y in s["season_units"]})
    season_rows = [[k] + [f"{stats[k]['season_units'].get(y, 0):+.1f}" for y in seasons] for k in sy.CATALOGUE]
    n_supported = sum(s["supported"] for s in stats.values())

    commit = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True).strip()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    parts = [
        "# System catalogue F1–F10: backtest (MS-045a)", "",
        f"_Generated {now} · commit `{commit}` · reproduce with `research/src/marketscope_research/run_catalogue.py`._", "",
        "Design pre-registered in `research/PREREGISTRATION.md` (Addendum F, committed before this code). Graded at "
        "the nflverse close at −110 (break-even 52.38%); pushes excluded from win rates. Primary: one-sided exact "
        "binomial test per system, Holm–Bonferroni across all ten at a family-wise 0.05, plus a 2024–25 win rate above "
        "break-even. Intervals resample games (5,000 draws, seed 2026). F10 is walk-forward from 2018. "
        "**Hypothetical results on closing lines; not betting advice.**", "",
        f"**{n_supported} of 10 systems supported.**", "",
        table(rows, ["System", "Decided", "Win rate (95% CI)", "p (one-sided)", "Passes Holm", "2024–25 win rate (n)",
                     "Return at −110 (95% CI)", "Result"]), "",
        "## Units by season (one unit per position, −110)", "",
        table(season_rows, ["System"] + [str(y) for y in seasons]), "",
        "## Reading this", "",
        "Each win rate is measured against the closing line, the market's most informed number. A public, well-known "
        "situation that still beat the close by enough to pay −110 for ten seasons would be surprising; most of these "
        "are expected to sit near 50%. The forward paper portfolio tracks every system anyway, so future results "
        "are not chosen by these past ones.", "",
    ]
    with open(args.out, "w") as f:
        f.write("\n".join(parts))
    if args.web_json:
        os.makedirs(os.path.dirname(args.web_json), exist_ok=True)
        payload = {"generated": now, "commit": commit, "breakEven": round(sy.BREAK_EVEN_110, 4), "systems": [
            {"id": k, "label": sy.CATALOGUE[k], "decided": s["decided"], "wins": s["wins"],
             "rate": round(s["rate"].value, 4), "low": round(s["rate"].low, 4), "high": round(s["rate"].high, 4),
             "p": round(s["p"], 4), "holm": s["holm"], "lateRate": round(s["late_rate"], 4), "lateN": s["late_n"],
             "roi": round(s["roi"].value, 4), "units": round(s["units"], 2), "supported": s["supported"],
             "seasonUnits": {str(y): u for y, u in s["season_units"].items()}}
            for k, s in stats.items()]}
        with open(args.web_json, "w") as f:
            json.dump(payload, f, indent=1)
    print("\n".join(parts[6:9]))


if __name__ == "__main__":
    main()
