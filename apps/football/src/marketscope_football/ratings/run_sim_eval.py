"""Season-simulation evaluation (MS-034) -> reports/season-sim.md and ratings/simulation.json.

1. Game noise: the share of the fitted margin spread that is rating error (2016-22, the tuning
   seasons), so the simulation can draw rating error separately without double counting.
2. Backtest 2016-24 (the 2025 test season stays untouched): projections before week 1 and after every
   regular-season week, scored against what happened (playoffs, division, #1 seed, conference, Super
   Bowl, wins), next to two simpler versions: the same model without rating uncertainty, and a
   no-ratings baseline (every game a home-field coin flip). Nothing is tuned on these results.

    PYTHONPATH=src .venv/bin/python -m marketscope_football.ratings.run_sim_eval [--sims 2000]
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

from ..eval.run_benchmarks import prepare
from .design import LIKELIHOOD_SEASONS
from .live import build_model
from .project import SIM_PARAMS_PATH, rating_error_variance, season_projections
from .simulate import IX, TEAMS, Standings, head_to_head, n_seeds
from .version import MODEL_VERSION

REPORT = Path(__file__).resolve().parents[3] / "reports" / "season-sim.md"
SEASONS = range(2016, 2025)
BUCKETS = [(0, 0, "Preseason"), (1, 4, "Weeks 1-4"), (5, 8, "Weeks 5-8"), (9, 12, "Weeks 9-12"), (13, 17, "Weeks 13+")]
TARGETS = [("playoff_p", "made_playoffs", "Playoffs"), ("division_p", "won_division", "Division"),
           ("seed1_p", "seed1", "#1 seed"), ("conf_p", "won_conf", "Conference"), ("sb_p", "won_sb", "Super Bowl")]


def outcomes(games: pd.DataFrame) -> pd.DataFrame:
    """What happened each season: seeds from the real standings (the tiebreakers reproduce the actual
    fields, tests/test_simulate.py), conference and Super Bowl winners, regular-season wins."""
    rows = []
    for season in SEASONS:
        g = games[games["season"] == season]
        reg = g[g["game_type"] == "REG"]
        res = reg["home_win"].to_numpy(float)[None, :]
        hp, hw, c = head_to_head(1, reg["home"].map(IX).to_numpy(), reg["away"].map(IX).to_numpy(), res)
        st = Standings(hp[0], hw[0], c, np.random.default_rng(0))
        made, div, top = set(), set(), set()
        for conf in (0, 1):
            seeds, winners = st.conference_seeds(conf, n_seeds(season))
            made |= set(seeds)
            div |= set(winners)
            top.add(seeds[0])
        win = lambda r: r.home if r.margin > 0 else r.away  # noqa: E731
        conf_w = {IX[win(r)] for r in g[g["game_type"] == "CON"].itertuples()}
        sb_w = {IX[win(r)] for r in g[g["game_type"] == "SB"].itertuples()}
        wins = hw[0].sum(1)
        for t, team in enumerate(TEAMS):
            rows.append({"season": season, "team": team, "made_playoffs": t in made, "won_division": t in div,
                         "seed1": t in top, "won_conf": t in conf_w, "won_sb": t in sb_w, "wins": wins[t]})
    return pd.DataFrame(rows)


def no_ratings(season, week, inp):
    """Baseline: every unplayed game is a home-field coin flip; no team strength at all."""
    inp.mean_margin = np.where(np.isnan(inp.result), np.where(inp.neutral, 0.0, inp.hfa), np.nan)
    inp.strength = np.zeros_like(inp.strength)
    return inp


def score(frame: pd.DataFrame, truth: pd.DataFrame) -> pd.DataFrame:
    m = frame.merge(truth, on=["season", "team"])
    m = m[m["games_played"] < m.groupby(["season"])["games_played"].transform("max")]  # drop decided seasons
    out = []
    for lo, hi, label in BUCKETS:
        b = m[m["week"].between(lo, hi)]
        row = {"bucket": label, "projections": len(b) // 32}
        for p, y, name in TARGETS:
            row[name] = float(((b[p] - b[y].astype(float)) ** 2).mean())
        row["Wins MAE"] = float((b["mean_wins"] - b["wins"]).abs().mean())
        out.append(row)
    return pd.DataFrame(out)


def paired(a: pd.DataFrame, b: pd.DataFrame, truth: pd.DataFrame, resamples: int = 2000) -> pd.DataFrame:
    """a - b per target over weeks 1+ (undecided), with a 95% interval resampling whole seasons."""
    def per_season(frame):
        m = frame.merge(truth, on=["season", "team"])
        m = m[(m["week"] >= 1) & (m["games_played"] < m.groupby("season")["games_played"].transform("max"))]
        cols = {name: (m[p] - m[y].astype(float)) ** 2 for p, y, name in TARGETS}
        cols["Wins MAE"] = (m["mean_wins"] - m["wins"]).abs()
        return pd.DataFrame(cols).assign(season=m["season"].to_numpy()).groupby("season").mean()
    d = per_season(a) - per_season(b)
    rng = np.random.default_rng(2026)
    rows = []
    for col in d.columns:
        x = d[col].to_numpy()
        boots = np.sort([x[rng.integers(0, len(x), len(x))].mean() for _ in range(resamples)])
        rows.append({"metric": col, "difference": x.mean(), "low": boots[int(0.025 * resamples)],
                     "high": boots[int(0.975 * resamples) - 1]})
    return pd.DataFrame(rows)


def calibration(frame: pd.DataFrame, truth: pd.DataFrame) -> pd.DataFrame:
    m = frame.merge(truth, on=["season", "team"])
    m = m[(m["week"] >= 1) & (m["games_played"] < m.groupby("season")["games_played"].transform("max"))]
    bins = np.minimum((m["playoff_p"] * 10).astype(int), 9)
    g = m.groupby(bins)
    return pd.DataFrame({"range": [f"{10 * b}-{10 * b + 10}%" for b in g.groups], "team-weeks": g.size().to_numpy(),
                         "mean estimate": g["playoff_p"].mean().to_numpy(),
                         "made playoffs": g["made_playoffs"].mean().to_numpy()})


def md(df: pd.DataFrame, fmt: dict) -> str:
    cols = list(df.columns)
    lines = ["| " + " | ".join(cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    for _, r in df.iterrows():
        lines.append("| " + " | ".join(fmt.get(c, "{}").format(r[c]) for c in cols) + " |")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sims", type=int, default=2000)
    args = ap.parse_args()
    t0 = time.time()
    games, sigma, _ = prepare()

    model, _, obs = build_model(games, sigma)
    scale = model.dist.scale
    v, n = rating_error_variance(model, games, obs, LIKELIHOOD_SEASONS)
    game_scale = float(np.sqrt(scale ** 2 - v))
    params = {"model_version": MODEL_VERSION, "fitted_scale": scale, "rating_error_variance": v,
              "rating_error_games": n, "game_scale": game_scale, "seasons": f"{min(LIKELIHOOD_SEASONS)}-{max(LIKELIHOOD_SEASONS)}"}
    SIM_PARAMS_PATH.write_text(json.dumps(params, indent=2) + "\n")
    print(f"game scale {game_scale:.3f} (fitted {scale:.3f}, rating-error variance {v:.2f} over {n} games)")

    truth = outcomes(games)
    variants = {}
    for name, kw in (("ratings-v1", {"game_scale": game_scale}),
                     ("no rating uncertainty", {"game_scale": None, "uncertainty": False}),
                     ("no ratings (home-field coin flips)", {"game_scale": None, "uncertainty": False,
                                                            "on_inputs": no_ratings})):
        model, _, obs = build_model(games, sigma)
        variants[name] = season_projections(model, games, obs, set(SEASONS), args.sims, **kw)
        print(f"{name}: {len(variants[name]) // 32} projections ({time.time() - t0:.0f}s)")

    f3 = {k: "{:.4f}" for _, _, k in TARGETS} | {"Wins MAE": "{:.2f}"}
    parts = [
        "# Season simulation: evaluation (MS-034)",
        "",
        f"Generated by `ratings/run_sim_eval.py` with {MODEL_VERSION} (frozen parameters), {args.sims:,} simulated "
        f"seasons per projection. Backtest seasons {SEASONS.start}-{SEASONS.stop - 1}; the 2025 test season is not "
        "used. Nothing in the simulation is tuned on these results. Model estimates, not betting advice.",
        "",
        "## Game noise",
        "",
        f"The key-number margin distribution was fitted on model errors (scale {scale:.2f} points), which include "
        f"rating error. Over {n:,} games in {params['seasons']} the rating-error variance of a matchup averaged "
        f"{v:.2f} points², so the simulation plays games with scale {game_scale:.2f} and draws each team's rating "
        "error once per simulated season (correlated across its games) plus a weekly drift.",
        "",
        "## Tiebreakers",
        "",
        "NFL procedures through strength of schedule, then a coin flip. On the real results they reproduce every "
        "playoff field and Wild Card matchup of 2016-24 (`tests/test_simulate.py`).",
        "",
        "## Brier scores (lower is better)",
        "",
        "Projections before week 1 and after each regular-season week, averaged over teams and weeks in each bucket. "
        "Seasons already decided (all games played) are excluded.",
        "",
    ]
    for name, frame in variants.items():
        parts += [f"### {name}", "", md(score(frame, truth), f3), ""]
    ci = {"difference": "{:+.4f}", "low": "{:+.4f}", "high": "{:+.4f}"}
    parts += ["## Paired differences (weeks 1+, 95% interval resampling seasons)", "",
              "Negative favors ratings-v1. Nine seasons is a small sample: read the intervals, not the points.", ""]
    for other in list(variants)[1:]:
        parts += [f"### ratings-v1 minus {other}", "", md(paired(variants["ratings-v1"], variants[other], truth), ci), ""]
    cal = calibration(variants["ratings-v1"], truth)
    parts += ["## Calibration of playoff odds (ratings-v1, weeks 1+)", "",
              md(cal, {"team-weeks": "{:,}", "mean estimate": "{:.3f}", "made playoffs": "{:.3f}"}), ""]
    REPORT.write_text("\n".join(parts))
    print(f"wrote {REPORT} in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
