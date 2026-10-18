"""Factor selection (MS-032): apply the pre-registered rule in selection_design.py, refit the kept
factors jointly, and write the ratings-v1 game layer. Writes reports/factor-selection.md.

    PYTHONPATH=src .venv/bin/python -m marketscope_football.ratings.selection --out reports/factor-selection.md
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
import math
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from ..eval import design as ed
from ..eval.data import load_schedules
from ..eval.metrics import score_table, win_probability
from ..eval.run_benchmarks import last_season, prepare
from ..eval.walkforward import walk_forward
from .availability_adj import AvailabilityAdjuster
from .engine import PARAMS_PATH, GameLayer, load_params
from .factors import RecordingKalman, candidate_features, context_rows
from .fit import load_inputs
from .qb import QBAdjuster, QBParams
from .qb_fit import availability_inputs, qb_inputs
from .selection_design import CANDIDATES, MIN_T, RB_FEATURE

BASE = "MS-031 model"


def feature_matrix(games: pd.DataFrame, sigma: float, layer: GameLayer, seasons: tuple[int, ...]) -> pd.DataFrame:
    """Pre-game features of the MS-031 model for every completed game in `seasons` (walk-forward)."""
    _, obs, teams, sf, wf = load_inputs("model")
    units, st, _ = load_params("model")
    last = int(games["season"].max())
    starters, qbg = qb_inputs(games, last)
    qp = QBParams(**json.loads(PARAMS_PATH.read_text())["model"]["qb"])
    m = RecordingKalman(BASE, teams, (units, st, layer), obs, sf, wf, sigma,
                        qb=QBAdjuster(qp, starters, qbg, layer.n_pass), avail=AvailabilityAdjuster(availability_inputs(games, last)))
    preds = walk_forward(games, m, seasons)
    X = pd.DataFrame(m.rows).set_index("game_id")
    return X.join(preds.set_index("game_id")[["season", "week", "actual_margin", "home_win", "actual_total"]])


def ols(X: pd.DataFrame, cols: list[str]) -> tuple[np.ndarray, np.ndarray]:
    """Coefficients (cols + home) and HC1 robust standard errors."""
    A = X[cols + ["home"]].to_numpy(float)
    y = X["actual_margin"].to_numpy(float)
    beta, *_ = np.linalg.lstsq(A, y, rcond=None)
    e = y - A @ beta
    n, k = A.shape
    bread = np.linalg.inv(A.T @ A)
    meat = A.T @ (A * (e ** 2)[:, None])
    se = np.sqrt(np.diag(bread @ meat @ bread) * n / (n - k))
    return beta, se


def preds_frame(X: pd.DataFrame, cols: list[str], beta: np.ndarray, name: str, sigma: float) -> pd.DataFrame:
    m = X[cols + ["home"]].to_numpy(float) @ beta
    return pd.DataFrame({"model": name, "game_id": X.index, "margin": m, "p_home": win_probability(m, sigma),
                         "actual_margin": X["actual_margin"].to_numpy(), "home_win": X["home_win"].to_numpy(),
                         "actual_total": X["actual_total"].to_numpy()})


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=Path("reports/factor-selection.md"))
    ap.add_argument("--probabilities", action="store_true", help="fit the margin distribution (after selection)")
    args = ap.parse_args()
    if args.probabilities:
        probabilities(args.out)
        return
    games, sigma, _ = prepare()
    params = json.loads(PARAMS_PATH.read_text())
    layer = GameLayer(**params["model"]["game"])
    base_cols = list(layer.w)

    X = feature_matrix(games, sigma, layer, ed.TUNING_SEASONS + ed.VALIDATION_SEASONS)
    F = candidate_features(context_rows(load_schedules(last_season())), games).set_index("game_id")
    X = X.join(F)
    missing = X[list(F.columns)].isna().any(axis=1)
    if missing.any():
        raise SystemExit(f"{int(missing.sum())} games without candidate features")
    tune, val = X[X["season"].isin(ed.TUNING_SEASONS)], X[X["season"].isin(ed.VALIDATION_SEASONS)]

    # The matrix reproduces the frozen layer exactly (same data, same OLS).
    b0, _ = ols(tune, base_cols)
    assert np.allclose(b0[:-1], [layer.w[c] for c in base_cols], rtol=1e-4, atol=1e-4) and abs(b0[-1] - layer.c) < 1e-4
    base_val = preds_frame(val, base_cols, b0, BASE, sigma)

    rows, kept = [], []
    tests = {name: (feats, sign) for name, (feats, sign, _) in CANDIDATES.items()}
    for name, (feats, sign) in tests.items():
        cols = base_cols + feats
        beta, se = ols(tune, cols)
        t = beta[len(base_cols)] / se[len(base_cols)]
        cand = preds_frame(val, cols, beta, name, sigma)
        sc = score_table(pd.concat([base_val, cand]), BASE).set_index("model").loc[name]
        keep = (np.sign(t) == sign and abs(t) >= MIN_T) and sc["d_margin_mae"] <= 0 and sc["d_log_loss"] <= 0
        rows.append({"factor": name, "coef": beta[len(base_cols)], "t": t, "expected": "+" if sign > 0 else "−",
                     "d_mae": sc["d_margin_mae"], "d_mae_lo": sc["d_margin_mae_lo"], "d_mae_hi": sc["d_margin_mae_hi"],
                     "d_ll": sc["d_log_loss"], "d_ll_lo": sc["d_log_loss_lo"], "d_ll_hi": sc["d_log_loss_hi"], "keep": keep})
        if keep:
            kept += feats
    # RB absence: tested by removal (keep only if it passes the same rule).
    no_rb = [c for c in base_cols if c != RB_FEATURE]
    beta_rb, se_rb = ols(tune, base_cols)
    i = base_cols.index(RB_FEATURE)
    t_rb = beta_rb[i] / se_rb[i]
    b_nr, _ = ols(tune, no_rb)
    sc = score_table(pd.concat([preds_frame(val, no_rb, b_nr, BASE, sigma), base_val.assign(model="with RB")]), BASE
                     ).set_index("model").loc["with RB"]
    keep_rb = (t_rb <= -MIN_T) and sc["d_margin_mae"] <= 0 and sc["d_log_loss"] <= 0
    rows.append({"factor": "RB absence (kept only if it passes)", "coef": beta_rb[i], "t": t_rb, "expected": "−",
                 "d_mae": sc["d_margin_mae"], "d_mae_lo": sc["d_margin_mae_lo"], "d_mae_hi": sc["d_margin_mae_hi"],
                 "d_ll": sc["d_log_loss"], "d_ll_lo": sc["d_log_loss_lo"], "d_ll_hi": sc["d_log_loss_hi"], "keep": keep_rb})

    final_cols = (base_cols if keep_rb else no_rb) + kept
    bf, sef = ols(tune, final_cols)
    final = GameLayer(layer.n_pass, layer.n_rush, layer.n_drives, {c: float(v) for c, v in zip(final_cols, bf[:-1])},
                      float(bf[-1]), layer.total_a, layer.total_b)
    final_val = preds_frame(val, final_cols, bf, "ratings-v1", sigma)
    fsc = score_table(pd.concat([base_val, final_val]), BASE).set_index("model")

    m = params["model"]
    m["game_alternatives"][BASE] = asdict(layer)
    m["game"] = asdict(final)
    m["factors"] = kept
    m["meta"]["selection"] = {"table": rows, "kept": kept, "rb_kept": bool(keep_rb)}
    PARAMS_PATH.write_text(json.dumps(params, indent=2, default=lambda o: o.item()))

    def ci(r, k, d):
        return f"{r[k]:+.{d}f} ({r[k + '_lo']:+.{d}f} to {r[k + '_hi']:+.{d}f})"
    L = ["# Factor selection (MS-032)", "",
         f"_Generated by `marketscope_football.ratings.selection` on {date.today().isoformat()}. Rule pre-registered in "
         "`ratings/selection_design.py` (committed before any candidate was fitted): keep a factor if its 2016–22 "
         f"coefficient has the expected sign with |t| ≥ {MIN_T:g} (HC1 robust) AND, on 2023–24 paired against the MS-031 "
         "model, Δ margin MAE ≤ 0 and Δ log loss ≤ 0._", "",
         "| Factor | Coef (pts) | t | Expected sign | Δ margin MAE (2023–24) | Δ log loss | Kept |", "|---|---|---|---|---|---|---|"]
    for r in rows:
        L.append(f"| {r['factor']} | {r['coef']:+.2f} | {r['t']:+.1f} | {r['expected']} | {ci(r, 'd_mae', 2)} | "
                 f"{ci(r, 'd_ll', 4)} | {'**yes**' if r['keep'] else 'no'} |")
    L += ["", "Definitions: " + "; ".join(f"**{k}**: {v[2]}" for k, v in CANDIDATES.items()) + ".", "",
          f"## ratings-v1 game layer ({'RB absence kept' if keep_rb else 'RB absence dropped'}; extra factors: "
          f"{', '.join(kept) if kept else 'none'})", "",
          "| Feature | Weight | HC1 t |", "|---|---|---|",
          *[f"| {c} | {b:+.3f} | {b / s:+.1f} |" for c, b, s in zip(final_cols + ["home"], bf, sef)], "",
          f"2023–24 vs the MS-031 model: Δ margin MAE {ci(fsc.loc['ratings-v1'], 'd_margin_mae', 2)}, Δ log loss "
          f"{ci(fsc.loc['ratings-v1'], 'd_log_loss', 4)}. This score is optimistic by construction (factors were chosen "
          "on these seasons); the 2025 test is the honest estimate.", ""]
    args.out.write_text("\n".join(L))
    print("\n".join(L[4:4 + len(rows) + 1]))
    print("kept:", kept, "rb:", keep_rb)



def probabilities(out: Path) -> None:
    """Fit the margin distribution, compare it with Phi(m / sigma) on 2023-24 (pre-registered rule),
    and report win/cover/total calibration. Appends to reports/factor-selection.md."""
    from .margin_dist import fit_scale, fit_shape
    from ..eval.metrics import calibration_table

    games, sigma, _ = prepare()
    params = json.loads(PARAMS_PATH.read_text())
    layer = GameLayer(**params["model"]["game"])
    cols = list(layer.w)
    X = feature_matrix(games, sigma, GameLayer(**params["model"]["game_alternatives"][BASE]), ed.TUNING_SEASONS + ed.VALIDATION_SEASONS)
    X["margin"] = X[cols + ["home"]].to_numpy(float) @ np.array([layer.w[c] for c in cols] + [layer.c])
    X = X.join(games.set_index("game_id")[["close_margin", "close_total"]])

    hist = games[games["season"].isin(ed.SIGMA_FIT_SEASONS) & games["margin"].notna() & games["close_margin"].notna()]
    shape, meta = fit_shape(hist["close_margin"].to_numpy(float), hist["margin"].to_numpy(float))
    tune, val = X[X["season"].isin(ed.TUNING_SEASONS)], X[X["season"].isin(ed.VALIDATION_SEASONS)]
    dist = fit_scale(shape, tune["margin"].to_numpy(float), tune["actual_margin"].to_numpy(float))

    base = pd.DataFrame({"model": "Φ(m / σ)", "game_id": val.index, "margin": val["margin"], "p_home": win_probability(val["margin"].to_numpy(), sigma),
                         "actual_margin": val["actual_margin"], "home_win": val["home_win"], "actual_total": val["actual_total"]})
    kd = base.assign(model="key-number distribution", p_home=dist.p_home(val["margin"].to_numpy()))
    sc = score_table(pd.concat([base, kd]), "Φ(m / σ)").set_index("model")
    adopt = bool(sc.loc["key-number distribution", "d_log_loss"] <= 0)

    # Cover probabilities against the closing line (pushes excluded): the model's view vs the market's.
    pc, pp = dist.p_cover(val["margin"].to_numpy(), val["close_margin"].to_numpy())
    pc_np = pc / np.clip(1 - pp, 1e-9, None)
    covered = (val["actual_margin"] > val["close_margin"]).astype(float)
    nopush = val["actual_margin"] != val["close_margin"]
    y, p = covered[nopush].to_numpy(), pc_np[nopush.to_numpy()]
    ll_model = float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))
    ll_half = math.log(2)

    params["model"]["margin_dist"] = {"scale": dist.scale, "weights": dist.weights, "shape_scale_close": shape.scale,
                                      "adopted": adopt, "fit": meta}
    PARAMS_PATH.write_text(json.dumps(params, indent=2, default=lambda o: o.item()))

    w = dict(enumerate(shape.weights))
    cal = {name: calibration_table(f["p_home"].to_numpy(), f["home_win"].to_numpy()) for name, f in (("Φ(m / σ)", base), ("key-number distribution", kd))}
    cover_cal = calibration_table(p, y)
    L = ["", "## Probabilities", "",
         f"Margin distribution fitted on {meta['games']:,} games (1999–2015 closing lines): scale {shape.scale:.2f}; refitted for "
         f"the model on 2016–22: scale {dist.scale:.2f}. Key-number multipliers (probability relative to the smooth curve):", "",
         "| Margin | " + " | ".join(str(k) for k in range(0, 15)) + " |", "|---|" + "---|" * 15,
         "| Multiplier | " + " | ".join(f"{w[k]:.2f}" for k in range(0, 15)) + " |", "",
         "Win probability on 2023–24 (paired vs Φ(m / σ), σ = {:.2f}):".format(sigma), "",
         "| Mapping | Brier | Log loss | Δ log loss |", "|---|---|---|---|",
         *[f"| {n} | {r['brier']:.4f} | {r['log_loss']:.4f} | {r['d_log_loss']:+.4f} ({r['d_log_loss_lo']:+.4f} to {r['d_log_loss_hi']:+.4f}) |"
           for n, r in sc.iterrows()], "",
         f"Pre-registered rule: adopt the key-number distribution if its log loss is no worse → **{'adopted' if adopt else 'not adopted; Φ stays'}**.", "",
         "Reliability (observed home win rate by predicted bin, 2023–24):", "",
         "| Bin | Φ(m / σ) | key-number distribution |", "|---|---|---|",
         *[f"| {b} | " + " | ".join("–" if cal[n].loc[b, 'n'] == 0 else f"{cal[n].loc[b, 'observed']:.2f} (n {int(cal[n].loc[b, 'n'])})"
                                     for n in cal) + " |" for b in cal["Φ(m / σ)"].index], "",
         "### Against the closing line", "",
         f"Model probability that the home team covers the close (pushes excluded), 2023–24, {int(nopush.sum())} games: log loss "
         f"{ll_model:.4f} vs {ll_half:.4f} for a coin flip. "
         + ("Worse than a coin flip: the model's disagreements with the close carry no information about who covers, as expected for a "
            "model that is 0.4 points less accurate than the close." if ll_model > ll_half else
            "Slightly better than a coin flip on these seasons; not evidence of an edge (no CI, 570 games)."), "",
         "| Model P(home covers) | n | Observed cover rate |", "|---|---|---|",
         *[f"| {b} | {int(r['n'])} | {r['observed']:.2f} |" for b, r in cover_cal.iterrows() if r["n"] > 0], ""]
    with out.open("a") as f:
        f.write("\n".join(L))
    print(sc[["brier", "log_loss", "d_log_loss", "d_log_loss_lo", "d_log_loss_hi"]].round(4).to_string())
    print("adopt:", adopt, "scale close", round(shape.scale, 2), "model", round(dist.scale, 2), "cover ll", round(ll_model, 4))


if __name__ == "__main__":
    main()
