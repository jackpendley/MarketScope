"""Kalman ratings in the MS-029 harness: walk-forward on the 2023-24 validation seasons against the
benchmarks, plus ablations (measurement variants and structural variants refitted on 2016-22;
channel ablations with a refitted game layer; ridge with a half-life on the same EPA signal).
Writes reports/kalman-ratings.md.

    PYTHONPATH=src .venv/bin/python -m marketscope_football.ratings.run_eval --out reports/kalman-ratings.md
"""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import chi2

from ..eval import design as ed
from ..eval.benchmarks import RidgeRatings
from ..eval.metrics import score_table
from ..eval.run_benchmarks import benchmark_factories, diff_table, main_table, prepare, ridge_grid
from ..eval.walkforward import run_models
from .design import BURN_IN_FROM, NO_CONTINUITY, VARIANTS
from .engine import PARAMS_PATH, UNIT_CHANNELS, Engine, GameLayer, KalmanRatings, load_params
from .fit import load_inputs
from .kalman import STParams, UnitParams

MODEL = "MarketScope Ratings (Kalman)"


def net_epa_column(games: pd.DataFrame, obs: pd.DataFrame) -> pd.Series:
    """Home net adjusted EPA per game (pass + rush EPA totals, home minus away, plus net special teams)."""
    o = obs.assign(off_epa=obs["pass_epa"].fillna(0) * obs["pass_plays"].fillna(0)
                   + obs["rush_epa"].fillna(0) * obs["rush_plays"].fillna(0)).set_index(["game_id", "team"])
    def one(g):
        h, a = (g.game_id, g.home), (g.game_id, g.away)
        if h not in o.index or a not in o.index:
            return np.nan
        return o.loc[h, "off_epa"] - o.loc[a, "off_epa"] + o.loc[h, "st_epa"]
    return pd.Series([one(g) for g in games.itertuples(index=False)], index=games.index)


def kalman_factory(variant: str, sigma: float, layer: GameLayer | None = None):
    measure = "model" if variant == NO_CONTINUITY else variant
    games, obs, teams, sf, wf = load_inputs(measure, variant != NO_CONTINUITY)
    units, st_p, default_layer = load_params(variant)
    params = (units, st_p, layer or default_layer)
    return lambda: KalmanRatings(variant, teams, params, obs, sf, wf, sigma)


def current_ratings(games: pd.DataFrame) -> tuple[pd.DataFrame, tuple[int, int]]:
    """Filtered ratings after every completed game: AdjEM (points vs an average team, neutral
    field) with its standard error, and the unit ratings behind it."""
    _, obs, teams, sf, wf = load_inputs("model")
    units, st_p, layer = load_params("model")
    eng = Engine(teams, units, st_p, obs, sf, wf)
    done = games[games["margin"].notna() & (games["season"] >= BURN_IN_FROM)]
    for (season, week), slot in done.groupby(["season", "week"], sort=True):
        eng.begin(season, week)
        for g in slot.itertuples(index=False):
            eng.observe(g)
    scale = {"pass": layer.n_pass, "rush": layer.n_rush, "succ": 1.0, "ppd": layer.n_drives}
    em, var = np.zeros(len(teams)), np.zeros(len(teams))
    cols = {}
    for ch in UNIT_CHANNELS:
        f, k = eng.filters[ch], layer.w.get(ch, 0.0) * scale[ch]
        r, n = f.ratings(), f.n
        em += k * (r["off"] - r["def"])
        i = np.arange(n)
        var += k ** 2 * (f.P[i, i] + f.P[n + i, n + i] - 2 * f.P[i, n + i])
        cols[f"{ch}_off"], cols[f"{ch}_def"] = r["off"], r["def"]
    st = eng.filters["st"]
    em += layer.w.get("st", 0.0) * st.ratings()["st"]
    var += layer.w.get("st", 0.0) ** 2 * np.diag(st.P)
    out = pd.DataFrame({"team": teams, "adj_em": em, "adj_em_se": np.sqrt(var), **cols, "st": st.ratings()["st"]})
    return out.sort_values("adj_em", ascending=False).reset_index(drop=True), eng.slot


def split_lines(val: pd.DataFrame) -> list[str]:
    """Paired model-vs-benchmark differences early and late in the season (descriptive)."""
    lines = ["Paired Δ margin MAE (model minus benchmark) by part of the season:", "",
             "| Benchmark | weeks 1–4 | weeks 5+ |", "|---|---|---|"]
    for ref in ("Elo (538)", "SRS (ridge)", "market-implied ratings"):
        cells = []
        for lo, hi in ((1, 4), (5, 99)):
            part = val[val["model"].isin([MODEL, ref]) & val["week"].between(lo, hi)]
            r = score_table(part, ref).set_index("model").loc[MODEL]
            cells.append(f"{r['d_margin_mae']:+.2f} ({r['d_margin_mae_lo']:+.2f} to {r['d_margin_mae_hi']:+.2f})")
        lines.append(f"| {ref} | " + " | ".join(cells) + " |")
    return lines


def continuity_lines(params: dict) -> list[str]:
    """Likelihood-ratio test of play-caller continuity (4 extra parameters per unit channel)."""
    if NO_CONTINUITY not in params:
        return []
    lines = ["**Play-caller continuity, likelihood-ratio test** (2016–22; the model adds ρ-if-changed and a "
             "mid-season bump for offense and defense, 4 parameters per unit channel):", "",
             "| Channel | log lik with | without | 2Δ | p (χ², 4 df) |", "|---|---|---|---|---|"]
    total = 0.0
    for ch in UNIT_CHANNELS:
        a, b = params["model"]["meta"][ch]["loglik"], params[NO_CONTINUITY]["meta"][ch]["loglik"]
        lr = max(2 * (a - b), 0.0)
        total += lr
        lines.append(f"| {ch} | {a:.1f} | {b:.1f} | {lr:.1f} | {chi2.sf(lr, 4):.2f} |")
    df = 4 * len(UNIT_CHANNELS)
    lines += [f"| all | | | {total:.1f} | {chi2.sf(total, df):.2f} ({df} df) |", ""]
    return lines


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=Path("reports/kalman-ratings.md"))
    args = ap.parse_args()
    games, sigma, _ = prepare()
    params = json.loads(PARAMS_PATH.read_text())
    bench, tuned = benchmark_factories(games, sigma)

    # Ridge with a half-life on the same EPA signal (the filter's simplest alternative).
    _, obs, *_ = load_inputs("model")
    games = games.assign(net_epa=net_epa_column(games, obs))
    grid = ridge_grid(games, "net_epa", ed.TUNING_SEASONS)
    best = grid.loc[grid["margin_mae"].idxmin()]
    epa_ridge = ("ridge with a half-life on the same EPA (no filter)",
                 lambda: RidgeRatings("x", "net_epa", sigma, float(best["half_life"]), float(best["lambda"])))
    print(f"EPA ridge: half-life {best['half_life']:.0f}, lambda {best['lambda']}, tuning MAE {best['margin_mae']:.3f}")

    main_models = {MODEL: kalman_factory("model", sigma), **bench}
    seasons = ed.TUNING_SEASONS + ed.VALIDATION_SEASONS
    preds = run_models(games, main_models, seasons)
    val = preds[preds["season"].isin(ed.VALIDATION_SEASONS)]
    tune = preds[preds["season"].isin(ed.TUNING_SEASONS)]
    val_scores = score_table(val, ed.REFERENCE)
    tune_scores = score_table(tune, ed.REFERENCE)
    vs = {ref: score_table(val[val["model"].isin([MODEL, ref])], ref) for ref in ("Elo (538)", "SRS (ridge)")}

    abl = {MODEL: kalman_factory("model", sigma)}
    for v in [*VARIANTS, NO_CONTINUITY]:
        if v != "model" and v in params:
            abl[v] = kalman_factory(v, sigma)
    for name, layer in params["model"]["game_alternatives"].items():
        abl[name] = kalman_factory("model", sigma, GameLayer(**layer))
    abl[epa_ridge[0]] = epa_ridge[1]
    abl_preds = run_models(games, abl, ed.VALIDATION_SEASONS)
    abl_scores = score_table(abl_preds, MODEL)

    by_phase = val.assign(err=(val["margin"] - val["actual_margin"]).abs(),
                          phase=np.where(val["week"] <= 4, "weeks 1–4", "weeks 5+")).pivot_table(
        index="model", columns=["phase"], values="err", aggfunc="mean", sort=False)
    by_season = val.assign(err=(val["margin"] - val["actual_margin"]).abs()).pivot_table(
        index="model", columns="season", values="err", aggfunc="mean", sort=False)

    p = params["model"]
    ratings, (r_season, r_week) = current_ratings(games)

    def diff_line(t, ref):
        r = t[t["model"] == MODEL].iloc[0]
        return (f"vs {ref}: Δ margin MAE {r['d_margin_mae']:+.2f} ({r['d_margin_mae_lo']:+.2f} to "
                f"{r['d_margin_mae_hi']:+.2f}), Δ Brier {r['d_brier']:+.4f} ({r['d_brier_lo']:+.4f} to {r['d_brier_hi']:+.4f}), "
                f"Δ log loss {r['d_log_loss']:+.4f} ({r['d_log_loss_lo']:+.4f} to {r['d_log_loss_hi']:+.4f})")

    L = [
        "# MarketScope Ratings: Kalman unit ratings (MS-030)", "",
        f"_Generated by `marketscope_football.ratings.run_eval` on {date.today().isoformat()}. Parameters fitted by "
        "`ratings.fit` on 2016–22 only and frozen in `ratings/params.json`; 2023–24 never informed a choice; "
        "2025 untouched._", "",
        "## Model", "",
        "- **Channels (separate filters):** pass EPA/dropback, rush EPA/rush, success rate (all luck-adjusted, "
        "capped, WP-weighted; ADR-029), points per drive, and net special-teams EPA.",
        "- **State:** per channel, 32 offense + 32 defense units and a league mean (special teams: 32 units). "
        "Each team-game observes `mean + off[A] + def[B] ± hfa/2`, noise σ²/n_eff, so opponent adjustment happens "
        "inside the filter.",
        "- **Time:** random walk between weeks; at a season boundary unit → ρ·unit + noise, ρ depending on whether "
        "the unit's play-caller changed; a mid-season play-caller change adds one-time variance.",
        "- **Game layer:** margin = Σ w·feature + c·(not neutral), OLS on the filter's pre-week predictions for "
        "2016–22. Win probability Φ(margin / σ) as for the benchmarks.",
        f"- **Burn-in:** the filter starts in {BURN_IN_FROM}; 2012–15 never enter the likelihood.", "",
        f"## Validation, {ed.VALIDATION_SEASONS[0]}–{ed.VALIDATION_SEASONS[-1]} ({val_scores['games'].iloc[0]} games)", "",
        *main_table(val_scores), "", *diff_table(val_scores, ed.REFERENCE), "",
        f"Paired against the benchmarks the model must beat:", "",
        f"- {diff_line(vs['Elo (538)'], 'Elo (538)')}",
        f"- {diff_line(vs['SRS (ridge)'], 'SRS (ridge)')}", "",
        *split_lines(val), "",
        "Margin MAE by season and part of the season:", "",
        "| Model | " + " | ".join(map(str, by_season.columns)) + " | " + " | ".join(by_phase.columns) + " |",
        "|---|" + "---|" * (len(by_season.columns) + len(by_phase.columns)),
        *[f"| {m} | " + " | ".join(f"{v:.2f}" for v in by_season.loc[m]) + " | "
          + " | ".join(f"{v:.2f}" for v in by_phase.loc[m]) + " |" for m in by_season.index], "",
        f"## Tuning seasons, {ed.TUNING_SEASONS[0]}–{ed.TUNING_SEASONS[-1]} (in-sample for the model)", "",
        *main_table(tune_scores), "",
        "## Ablations (validation seasons, paired against the model)", "",
        "Measurement and structural variants are refitted on 2016–22 from scratch; channel ablations keep the "
        "filters and refit the game layer; the ridge row tunes its half-life and λ on 2016–22.", "",
        *diff_table(abl_scores, MODEL), "",
        "## Fitted parameters (maximum likelihood, 2016–22)", "",
        "| Channel | σ² | q week off / def | q season off / def | ρ off same / changed | ρ def same / changed | bump off / def | HFA | log lik |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for ch in UNIT_CHANNELS:
        u = p[ch]
        L.append(f"| {ch} | {u['sigma2']:.3g} | {u['q_week_off']:.2g} / {u['q_week_def']:.2g} | "
                 f"{u['q_season_off']:.2g} / {u['q_season_def']:.2g} | {u['rho_off_same']:.2f} / {u['rho_off_changed']:.2f} | "
                 f"{u['rho_def_same']:.2f} / {u['rho_def_changed']:.2f} | {u['bump_off']:.2g} / {u['bump_def']:.2g} | "
                 f"{u['hfa']:+.3f} | {p['meta'][ch]['loglik']:.0f} |")
    s = p["st"]
    L += [f"| special teams | {s['sigma2']:.3g} | {s['q_week']:.2g} | {s['q_season']:.2g} | {s['rho']:.2f} | – | – | "
          f"{s['hfa']:+.3f} | {p['meta']['st']['loglik']:.0f} |", "",
          "**Stability (signal-to-noise).** Between seasons a unit keeps ρ of its rating. Within a season the weekly "
          "drift sd is √q_week; for scale, the end-of-season spread of team units is shown below.", ""]
    L += ["| Channel | Offense: weekly drift sd / team sd | Defense: weekly drift sd / team sd |", "|---|---|---|"]
    for ch in UNIT_CHANNELS:
        u = p[ch]
        off_sd, def_sd = ratings[f"{ch}_off"].std(), ratings[f"{ch}_def"].std()
        L.append(f"| {ch} | {np.sqrt(u['q_week_off']):.3g} / {off_sd:.3g} | {np.sqrt(u['q_week_def']):.3g} / {def_sd:.3g} |")
    g = p["game"]
    L += ["", *continuity_lines(params)]
    L += ["**Game layer** (2016–22 OLS): " + ", ".join(f"w_{k} {v:.3g}" for k, v in g["w"].items())
          + f", home {g['c']:+.2f} pts; plays per team-game {g['n_pass']:.1f} dropbacks, {g['n_rush']:.1f} rushes, "
          f"{g['n_drives']:.1f} drives. In-sample margin MAE {p['meta']['game']['mae']:.3f}.", "",
          f"## Current ratings (filtered through {r_season} week {r_week})", "",
          "AdjEM: expected margin in points against an average team on a neutral field (± 1 SE). Unit columns: "
          "EPA/play above average (defense: allowed, so negative is good).", "",
          "| Rk | Team | AdjEM | Pass off | Pass def | Rush off | Rush def | ST (EPA/game) |", "|---|---|---|---|---|---|---|---|"]
    for i, r in ratings.iterrows():
        L.append(f"| {i + 1} | {r['team']} | {r['adj_em']:+.1f} ± {r['adj_em_se']:.1f} | {r['pass_off']:+.3f} | "
                 f"{r['pass_def']:+.3f} | {r['rush_off']:+.3f} | {r['rush_def']:+.3f} | {r['st']:+.2f} |")
    L.append("")
    args.out.write_text("\n".join(L))
    print(f"wrote {args.out}")
    print(val_scores[["model", "margin_mae", "brier", "log_loss"]].to_string(index=False))
    print(abl_scores[["model", "d_margin_mae", "d_margin_mae_lo", "d_margin_mae_hi"]].to_string(index=False))


if __name__ == "__main__":
    main()
