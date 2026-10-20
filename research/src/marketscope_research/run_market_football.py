"""MS-036: the market-movement model with football features vs the v1 market-only model (design
pre-registered in ml/design_football.py). Read-only; writes a report.

    STUDY_DATABASE_URL=... .venv/bin/python -m marketscope_research.run_market_football \
        --out reports/market-football-v1.md
"""

from __future__ import annotations

import argparse
import os
import subprocess
from datetime import datetime, timezone

import pandas as pd

from .data import _frame, connect, load_home_spreads, load_kickoffs, load_totals
from .ml import design, design_football
from .ml.dataset import build_dataset
from .ml.experiment_football import FootballResult, run_direction_football, run_move_football
from .ml.football_features import COLUMNS, build_football_features
from .run_market_baseline import beats, coef_md, scores_md
from .run_market_gate import md_table

SOURCES = ["the-odds-api", "oddspapi"]
FR = "(SELECT franchise FROM nfl_teams WHERE abbr = {})"


def load_football(conn) -> dict[str, pd.DataFrame]:
    schedule = _frame(conn, f"""
        SELECT game_id, season, week, kickoff_utc AS kickoff, {FR.format('home_team')} AS home,
               {FR.format('away_team')} AS away, neutral_site AS neutral, event_id::text AS event_id
        FROM nfl_games WHERE season = 2026""")
    schedule["kickoff"] = pd.to_datetime(schedule["kickoff"], utc=True)
    ratings = _frame(conn, f"""
        SELECT season, week, {FR.format('team')} AS team, adj_em FROM rating_snapshots
        WHERE model_version = %s AND season = 2026""", (design_football.RATING_VERSION,))
    snaps = _frame(conn, f"""
        SELECT game_id, {FR.format('team')} AS team, gsis_id, GREATEST(offense_pct, defense_pct) AS share
        FROM nfl_player_game_snaps WHERE season = 2026 AND gsis_id IS NOT NULL""")
    weather = _frame(conn, """
        SELECT f.game_id, f.lead_days, f.wind_mph FROM nfl_weather_forecasts f
        JOIN nfl_games g USING (game_id) WHERE g.season = 2026""")
    context = _frame(conn, """
        SELECT c.game_id, MAX(c.rest_diff) FILTER (WHERE c.team = g.home_team) AS rest_diff,
               MAX(c.travel_km) FILTER (WHERE c.team = g.away_team) AS away_travel_km,
               BOOL_OR(COALESCE(c.short_week, false))::int AS short_week_any
        FROM nfl_game_context c JOIN nfl_games g USING (game_id)
        WHERE c.season = 2026 GROUP BY c.game_id""")
    return {"schedule": schedule, "ratings": ratings, "snaps": snaps, "weather": weather, "context": context}


def add_football(df: pd.DataFrame, fb: dict[str, pd.DataFrame]) -> pd.DataFrame:
    games = fb["schedule"].dropna(subset=["event_id"])
    linked = df[df["event_id"].isin(games["event_id"])]
    feats = build_football_features(linked[["event_id", "t", "consensus"]], games, fb["schedule"], fb["ratings"],
                                    fb["snaps"], fb["weather"], fb["context"])
    return df.merge(feats.drop(columns=["consensus"]), on=["event_id", "t"], how="left")


def section(r: FootballResult) -> str:
    out = [md_table(r.sizes, {"positive_rate": "pct"}, index=False), "",
           f"Rating margin available for {r.rating_coverage:.1%} of fitting rows (gate "
           f"{design_football.MIN_RATING_COVERAGE:.0%}: {'met' if r.gate else 'not met'}).", "",
           "Chosen L2 strength C on validation: " + ", ".join(f"{k} = {v}" for k, v in r.chosen_c.items()) + ".", "",
           "### Test week (scored once), paired against the market-only model", "",
           scores_md(r.test_scores, design_football.PRIMARY_REFERENCE), "",
           f"**Primary ({design_football.PRIMARY_MODEL} vs {design_football.PRIMARY_REFERENCE}):** "
           f"{beats(r.test_scores, design_football.PRIMARY_MODEL) if r.gate else 'inconclusive (coverage gate)'}. "
           "Rows other than these two and the constant are exploratory ablations.", "",
           "### Coefficients of the football model (final fit, standardized)", "", coef_md(r.coefficients, 16)]
    if r.forward_scores is not None:
        out += ["", "### Forward check (live weeks ≥ 6)", "", scores_md(r.forward_scores, design_football.PRIMARY_REFERENCE)]
    else:
        out += ["", f"Forward check (live weeks ≥ 6): pending, {r.forward_games} games labelled "
                f"(needs {design.MIN_FORWARD_GAMES})."]
    return "\n".join(out)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    dsn = os.environ.get("STUDY_DATABASE_URL")
    if not dsn:
        raise SystemExit("Set STUDY_DATABASE_URL (read-only use).")
    with connect(dsn) as conn:
        df = build_dataset(load_home_spreads(conn, SOURCES), load_totals(conn, SOURCES), load_kickoffs(conn))
        fb = load_football(conn)
    df = add_football(df, fb)
    move, direction = run_move_football(df), run_direction_football(df)
    commit = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True).strip()
    labelled = df[df["moved"].notna() & df["split"].isin(["train", "validation", "test"])]
    missing = labelled[COLUMNS].isna().mean().rename("missing").to_frame()

    def line(r: FootballResult, label: str) -> str:
        row = r.test_scores.set_index("model").loc[design_football.PRIMARY_MODEL]
        return (f"- **{label}:** football model minus market-only model on the test week: Δ Brier {row['d_brier']:+.4f} "
                f"({row['d_brier_lo']:+.4f} to {row['d_brier_hi']:+.4f}), Δ log loss {row['d_log_loss']:+.3f} "
                f"({row['d_ll_lo']:+.3f} to {row['d_ll_hi']:+.3f}): **{beats(r.test_scores, design_football.PRIMARY_MODEL)}**.")

    report = f"""# Market-movement model with football features (MS-036, v1)

_Generated {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")} · commit `{commit}` · sources `{", ".join(SOURCES)}` ·
reproduce with `research/src/marketscope_research/run_market_football.py`. Design pre-registered in
`ml/design_football.py` (committed before any football feature was built); the target, split and scoring are v1's
(`market-baseline-v1.md`)._

## Summary

{line(move, "Will it move")}
{line(direction, "Direction")}

"Better" requires both the Brier and the log-loss difference CIs to lie below zero (2,000 game-resampled bootstraps).

## Football features (point in time at each snapshot)

| Family | Will-it-move features | Direction feature |
|---|---|---|
| Ratings | abs_rating_gap: \\|rating margin − consensus margin\\| | rating_gap (+ = ratings like home more than the market) |
| Injuries | starters_hurt_total: starters who played < 25% of snaps in their team's latest game | starters_hurt_net (away − home) |
| Weather | wind_mph, abs_wind_change, outdoor (shortest usable forecast lead) | – |
| Schedule | abs_rest_diff, away_travel_km, short_week_any | rest_diff (home − away) |

Rating margins use the latest ratings-v1 snapshot usable at t (16 h after its week's last kickoff); snap counts only from
games that kicked off at least 36 h before t; a forecast at lead N days only from kickoff − N days. A unit test perturbs
everything usable after t and checks that no feature changes. Implementation detail fixed before fitting: a starter's
average uses up to three of his team's games before its latest one (at least one), so weeks 2–3 are covered.

Share of labelled rows (train, validation, test) where each feature is missing (imputed with the median plus a missing
indicator, as in v1):

{md_table(missing, {"missing": "pct"})}

## 1. Will the consensus move ≥ {design.MOVE_THRESHOLD} pts within {design.HORIZON_HOURS} h?

{section(move)}

## 2. Direction, given a move

{section(direction)}

## Limitations

- The same small sample as v1: three training weeks, one validation week and a 15-game test week. A null here means
  "not detectable with this much data", not "no effect".
- The direction result is not independent of R4's exploratory finding on the same weeks (the consensus drifted toward
  the ratings), and the injury feature is related to R2w.
- These models describe market behaviour. Predicting a line move is not evidence of profitable betting after the vig.
"""
    with open(args.out, "w") as fh:
        fh.write(report)
    print(report.split("## Football features")[0])


if __name__ == "__main__":
    main()
