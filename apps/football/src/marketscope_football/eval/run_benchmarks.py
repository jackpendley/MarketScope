"""Benchmark table (MS-029): tune the ridge benchmarks walk-forward on 2016-22, then score every
benchmark on the 2023-24 validation seasons. Writes reports/benchmarks.md.

    PYTHONPATH=src .venv/bin/python -m marketscope_football.eval.run_benchmarks [--refresh] --out reports/benchmarks.md
"""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from . import design as d
from .benchmarks import Elo538, NaiveHomeField, NflverseClose, RidgeRatings, ridge_ratings
from .data import games_frame, load_schedules, manifest
from .metrics import calibration_table, fit_sigma, score_table, win_probability
from .walkforward import run_models, slots


def ridge_grid(games: pd.DataFrame, target: str, seasons: tuple[int, ...]) -> pd.DataFrame:
    """Walk-forward margin MAE of every (half-life, lambda) pair over `seasons`, computing each
    slot's history once. Same filters as RidgeRatings.predict (tested to agree)."""
    done = games[games["margin"].notna()]
    errs: dict[tuple[float, float], list[float]] = {(h, l): [] for h in d.RIDGE_HALF_LIFE_GRID for l in d.RIDGE_LAMBDA_GRID}
    for season, week in slots(done):
        if season not in seasons:
            continue
        slot = done[(done["season"] == season) & (done["week"] == week)]
        as_of = slot["kickoff_utc"].min()
        hist = done[(done["kickoff_utc"] < as_of) & (done["kickoff_utc"] >= as_of - pd.Timedelta(days=d.RIDGE_WINDOW_DAYS))]
        # Same-slot games are excluded even if an earlier one kicked off first (runner semantics).
        hist = hist[~hist["game_id"].isin(slot["game_id"])]
        for (hl, lam), e in errs.items():
            r, hfa = ridge_ratings(hist, target, as_of, hl, lam)
            m = np.array([r.get(g.home, 0.0) - r.get(g.away, 0.0) + (0.0 if g.neutral else hfa)
                          for g in slot.itertuples(index=False)])
            e.extend(np.abs(m - slot["margin"].to_numpy(float)))
    return pd.DataFrame([{"half_life": h, "lambda": l, "margin_mae": float(np.mean(e))} for (h, l), e in errs.items()])


def fmt_ci(row: pd.Series, k: str, digits: int) -> str:
    if pd.isna(row[k]):
        return "–"
    return f"{row[k]:.{digits}f} ({row[f'{k}_lo']:.{digits}f} to {row[f'{k}_hi']:.{digits}f})"


def fmt_diff(row: pd.Series, k: str, digits: int) -> str:
    if pd.isna(row.get(f"d_{k}")) or row["model"] == d.REFERENCE:
        return "–"
    return f"{row[f'd_{k}']:+.{digits}f} ({row[f'd_{k}_lo']:+.{digits}f} to {row[f'd_{k}_hi']:+.{digits}f})"


def main_table(scores: pd.DataFrame) -> list[str]:
    lines = ["| Model | Margin MAE | Margin RMSE | Brier | Log loss | Total MAE |", "|---|---|---|---|---|---|"]
    for _, r in scores.iterrows():
        lines.append(f"| {r['model']} | {fmt_ci(r, 'margin_mae', 2)} | {fmt_ci(r, 'margin_rmse', 2)} | "
                     f"{fmt_ci(r, 'brier', 4)} | {fmt_ci(r, 'log_loss', 4)} | {fmt_ci(r, 'total_mae', 2)} |")
    return lines


def diff_table(scores: pd.DataFrame, reference: str) -> list[str]:
    lines = [f"| Model | Δ margin MAE vs {reference} | Δ Brier | Δ log loss |", "|---|---|---|---|"]
    for _, r in scores.iterrows():
        if r["model"] != reference:
            lines.append(f"| {r['model']} | {fmt_diff(r, 'margin_mae', 2)} | {fmt_diff(r, 'brier', 4)} | "
                         f"{fmt_diff(r, 'log_loss', 4)} |")
    return lines


def last_season() -> int:
    return date.today().year if date.today().month >= 3 else date.today().year - 1


def prepare(refresh: bool = False) -> tuple[pd.DataFrame, float, pd.DataFrame]:
    """Games frame, sigma (fit on SIGMA_FIT_SEASONS closing lines) and the games it was fit on."""
    games = games_frame(load_schedules(last_season(), refresh))
    fit = games[games["season"].isin(d.SIGMA_FIT_SEASONS) & games["margin"].notna()]
    return games, fit_sigma(fit["close_margin"].to_numpy(), fit["home_win"].to_numpy()), fit


def benchmark_factories(games: pd.DataFrame, sigma: float, verbose: bool = True) -> tuple[dict, dict]:
    """The benchmark models (fresh-instance factories), with the ridge benchmarks tuned on
    TUNING_SEASONS. Returns (factories, tuned: label -> (target, half-life, lambda, grid))."""
    tuned = {}
    for label, target in (("SRS (ridge)", "margin"), ("market-implied ratings", "close_margin")):
        grid = ridge_grid(games, target, d.TUNING_SEASONS)
        best = grid.loc[grid["margin_mae"].idxmin()]
        tuned[label] = (target, float(best["half_life"]), float(best["lambda"]), grid)
        if verbose:
            print(f"{label}: half-life {best['half_life']:.0f} d, lambda {best['lambda']}, tuning MAE {best['margin_mae']:.3f}")
    factories = {
        "naive home field": lambda: NaiveHomeField(sigma),
        "Elo (538)": lambda: Elo538(),
        **{label: (lambda t=t, h=h, l=l, label=label: RidgeRatings(label, t, sigma, h, l))
           for label, (t, h, l, _) in tuned.items()},
        d.REFERENCE: lambda: NflverseClose(sigma),
    }
    return factories, tuned


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true", help="re-download nflverse schedules")
    ap.add_argument("--out", type=Path, default=Path("reports/benchmarks.md"))
    args = ap.parse_args()

    last = last_season()
    games, sigma, fit = prepare(args.refresh)
    print(f"sigma = {sigma:.3f} from {len(fit)} games")
    factories, tuned = benchmark_factories(games, sigma)
    seasons = d.TUNING_SEASONS + d.VALIDATION_SEASONS
    preds = run_models(games, factories, seasons)
    val = preds[preds["season"].isin(d.VALIDATION_SEASONS)]
    tune = preds[preds["season"].isin(d.TUNING_SEASONS)]
    val_scores = score_table(val, d.REFERENCE)
    tune_scores = score_table(tune, d.REFERENCE)

    h_srs, l_srs = tuned["SRS (ridge)"][1:3]
    ablations = {
        "Elo (538)": lambda: Elo538(),
        "Elo, home field 48 (538's later value)": lambda: Elo538(hfa=48.0),
        "Elo, no margin-of-victory multiplier": lambda: Elo538(mov=False),
        "SRS (ridge)": lambda: RidgeRatings("SRS (ridge)", "margin", sigma, h_srs, l_srs),
        "SRS, current season only": lambda: RidgeRatings("x", "margin", sigma, h_srs, l_srs, season_only=True),
    }
    abl = run_models(games, ablations, d.VALIDATION_SEASONS)
    abl_elo = score_table(abl[abl["model"].str.startswith("Elo")], "Elo (538)")
    abl_srs = score_table(abl[abl["model"].str.startswith("SRS")], "SRS (ridge)")

    by_season = val.assign(err=(val["margin"] - val["actual_margin"]).abs()).pivot_table(
        index="model", columns="season", values="err", aggfunc="mean", sort=False)
    early = val.assign(err=(val["margin"] - val["actual_margin"]).abs(),
                       phase=np.where(val["week"] <= 4, "weeks 1–4", "weeks 5+")).pivot_table(
        index="model", columns="phase", values="err", aggfunc="mean", sort=False)

    m = manifest(last)
    L = [
        "# Benchmarks (MS-029)", "",
        f"_Generated by `marketscope_football.eval.run_benchmarks` on {date.today().isoformat()}. "
        f"nflverse schedules via nflreadpy {m.get('nflreadpy', '?')} (sha256 {m.get('sha256', '?')[:12]}). "
        "Design pre-registered in `eval/design.py` before any result was computed._", "",
        "## Setup", "",
        "- **Walk-forward:** for each (season, week), every model predicts the week's games from earlier weeks only, "
        "then sees the results. Result columns are removed before `predict` is called.",
        f"- **Seasons:** warm-up from {d.WARMUP_FROM}; hyperparameters chosen on {d.TUNING_SEASONS[0]}–{d.TUNING_SEASONS[-1]}; "
        f"headline table on {d.VALIDATION_SEASONS[0]}–{d.VALIDATION_SEASONS[-1]} validation; {d.TEST_SEASON} untouched "
        "(the runner refuses it).",
        "- **Games:** every completed game, regular season and playoffs. Outcome for win probability: home win 1, loss 0, tie 0.5.",
        f"- **Win probability from a margin:** Φ(margin / σ), σ = {sigma:.2f} fitted on {len(fit):,} games "
        f"from {d.SIGMA_FIT_SEASONS[0]}–{d.SIGMA_FIT_SEASONS[-1]} closing lines. Elo uses its own logistic curve; "
        "the close uses the no-vig moneyline.",
        f"- **Intervals:** 95% bootstrap ({d.BOOTSTRAP_RESAMPLES:,} resamples of games). Δ columns are paired "
        "differences (negative = better than the reference).", "",
        "## Benchmarks", "",
        "| Benchmark | Definition |", "|---|---|",
        f"| naive home field | Recent league home margin (previous {d.HFA_WINDOW_SEASONS} seasons + current to date), 0 at neutral sites. Total: recent league mean |",
        f"| Elo (538) | FiveThirtyEight NFL Elo as published: K {d.ELO_K:.0f}, home field {d.ELO_HFA:.0f} Elo, revert ⅓ to {d.ELO_MEAN:.0f}, margin-of-victory multiplier; spread = Elo diff / {d.ELO_POINTS_PER_POINT:.0f} |",
        f"| SRS (ridge) | margin = r_home − r_away + HFA, weighted ridge refit weekly. Tuned: half-life {h_srs:.0f} days, λ {l_srs:g} |",
        f"| market-implied ratings | The same estimator fitted to past closing spreads (Inpredictable-style). Tuned: half-life {tuned['market-implied ratings'][1]:.0f} days, λ {tuned['market-implied ratings'][2]:g} |",
        f"| {d.REFERENCE} | The closing spread, no-vig moneyline and total themselves |", "",
        f"## Validation, {d.VALIDATION_SEASONS[0]}–{d.VALIDATION_SEASONS[-1]} ({val_scores['games'].iloc[0]} games)", "",
        *main_table(val_scores), "",
        *diff_table(val_scores, d.REFERENCE), "",
        "Margin MAE by season and by part of the season:", "",
        "| Model | " + " | ".join(str(c) for c in by_season.columns) + " | " + " | ".join(early.columns) + " |",
        "|---|" + "---|" * (len(by_season.columns) + len(early.columns)),
        *[f"| {mdl} | " + " | ".join(f"{v:.2f}" for v in by_season.loc[mdl]) + " | "
          + " | ".join(f"{v:.2f}" for v in early.loc[mdl]) + " |" for mdl in by_season.index], "",
        "**Sanity check (expected before running):** Elo/SRS margin MAE ≈ 10–11, the close ≈ 9.5–10. "
        + ", ".join(f"{r['model']} {r['margin_mae']:.2f}" for _, r in val_scores.iterrows()) + ".", "",
        f"## Tuning seasons, {d.TUNING_SEASONS[0]}–{d.TUNING_SEASONS[-1]} ({tune_scores['games'].iloc[0]} games)", "",
        "In-sample for the two tuned ridge benchmarks (their hyperparameters were picked here); out-of-sample for the rest.", "",
        *main_table(tune_scores), "",
        "Ridge tuning grid (walk-forward margin MAE; rows half-life in days, columns λ):", "",
    ]
    for label, (_, h, l, grid) in tuned.items():
        piv = grid.pivot(index="half_life", columns="lambda", values="margin_mae")
        L += [f"**{label}**", "", "| half-life | " + " | ".join(f"λ {c:g}" for c in piv.columns) + " |",
              "|---|" + "---|" * len(piv.columns),
              *[f"| {int(i)} | " + " | ".join(f"{v:.3f}" for v in piv.loc[i]) + " |" for i in piv.index], ""]
        edges = [n for n, v, g in (("half-life", h, d.RIDGE_HALF_LIFE_GRID), ("λ", l, d.RIDGE_LAMBDA_GRID))
                 if v in (min(g), max(g))]
        if edges:
            runner_up = grid.loc[(grid["half_life"] == h) & (grid["lambda"] != l), "margin_mae"].min()
            L += [f"The best {' and '.join(edges)} sits at the edge of the pre-registered grid. The grid was not "
                  f"extended (that would be a deviation); the nearest alternative at the same half-life is "
                  f"{runner_up - grid['margin_mae'].min():.3f} points worse, so the surface is flat there.", ""]
    L += ["## Ablations (validation seasons)", "",
          "The ablation runner scores variants of one model on the same games, paired against the base variant.", "",
          *diff_table(abl_elo, "Elo (538)"), "", *diff_table(abl_srs, "SRS (ridge)"), "",
          "## Calibration (validation seasons)", "",
          "| Predicted P(home win) | " + " | ".join(val_scores["model"]) + " |", "|---|" + "---|" * len(val_scores)]
    cals = {mdl: calibration_table(g["p_home"].to_numpy(), g["home_win"].to_numpy()) for mdl, g in val.groupby("model", sort=False)}
    for b in cals[d.REFERENCE].index:
        cells = []
        for mdl in val_scores["model"]:
            c = cals[mdl].loc[b]
            cells.append("–" if c["n"] == 0 else f"{c['observed']:.2f} (n {int(c['n'])})")
        L.append(f"| {b} | " + " | ".join(cells) + " |")
    L += ["", "Each cell: observed home win rate (games). A calibrated model's rate falls inside its bin.", ""]
    args.out.write_text("\n".join(L))
    print(f"wrote {args.out}")
    print(val_scores[["model", "margin_mae", "margin_rmse", "brier", "log_loss", "total_mae"]].to_string(index=False))


if __name__ == "__main__":
    main()
