"""The one-time 2025 test of ratings-v1 (MS-032b, ADR-039). Refuses to run twice (the report file is the
record) or with parameters other than the frozen ones. Writes reports/test-2025.md and the run record
reports/model_runs/ratings-v1-test-2025.json (loaded into model_runs by `ingest model-runs`).

    PYTHONPATH=src .venv/bin/python -m marketscope_football.ratings.run_test --confirm-once
"""

from __future__ import annotations

import argparse
import json
import math
import subprocess
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from ..eval import design as ed
from ..eval.metrics import calibration_table, score_table
from ..eval.run_benchmarks import benchmark_factories, diff_table, main_table, prepare
from ..eval.walkforward import run_models
from .engine import PARAMS_PATH
from .live import build_model
from .margin_dist import MarginDistribution
from .outputs import home_advantage_points
from .version import FROZEN_PARAMS_SHA256, MODEL_VERSION, params_sha256

REPORT = Path("reports/test-2025.md")
RECORD = Path("reports/model_runs/ratings-v1-test-2025.json")
MODEL = MODEL_VERSION


def parameter_table(model, params: dict) -> list[str]:
    """Our fitted values next to the published ones (docs/RATINGS.md prior-art table)."""
    p, sel = params["model"], {r["factor"]: r for r in params["model"]["meta"]["selection"]["table"]}
    layer = model.layer
    hfa = home_advantage_points(model.engine, layer)
    tr, qp = model.qb.tracker, p["qb"]
    season_end = max(t for _, _, t in tr.qb.values())
    recent = {q: s for q, s in tr.qb.items() if (season_end - s[2]).days < 120 and s[0] > 300}
    best = max(tr.rating(q, season_end) for q in recent)
    qb_pts = layer.n_pass * (best - qp["replacement"]) * layer.w["qb"]
    w = layer.w
    rho = {ch: (p[ch]["rho_off_same"], p[ch]["rho_def_same"]) for ch in ("pass", "rush")}
    rows = [
        ("Home-field advantage (points)", f"{hfa:.1f}", "538: 65 Elo (≈ 2.6 pts), later ≈ 48 Elo; ELWAY 1–3.5; Inpredictable ≈ 2"),
        ("Extra home edge in the playoffs", f"{sel['playoffs']['coef']:+.1f} (t {sel['playoffs']['t']:.1f}; not kept)", "ELWAY +0.75"),
        ("Bye week", f"{sel['bye week']['coef']:+.1f} (t {sel['bye week']['t']:.1f}; not kept)", "538 +25 Elo (≈ 1 pt); ELWAY ≈ +1; arXiv 2408.10867 ≈ 0 since 2011"),
        ("Each extra day of rest", f"{sel['rest difference']['coef']:+.2f} (t {sel['rest difference']['t']:.1f}; not kept)", "ELWAY +0.3"),
        ("Travel (per 1000 km)", f"{sel['travel distance']['coef']:+.2f} (t {sel['travel distance']['t']:.1f}; not kept)", "538: travel-distance term"),
        ("New head coach (first 10 games)", f"{sel['new head coach']['coef']:+.1f} (t {sel['new head coach']['t']:.1f}; not kept)", "ELWAY: negative for ≈ 10 games"),
        ("Rating kept between seasons", f"pass off {rho['pass'][0]:.2f} / def {rho['pass'][1]:.2f}; rush {rho['rush'][0]:.2f} / {rho['rush'][1]:.2f}",
         "538 keeps ⅔; nfelo reversion ≈ 0.53"),
        ("P(QB plays \\| Questionable)", f"{qp['p_questionable']:.2f}", "ELWAY ≈ 0.70"),
        ("P(plays \\| Doubtful), all positions", "0.01", "ELWAY ≈ 0.07 (QBs)"),
        ("Best starting QB vs replacement (points)", f"{qb_pts:.1f}", "ELWAY: QB ≈ 30% of a team's player value"),
        ("Missing starter, non-QB (points)", f"OL {-w['avail_ol']:.2f}, WR/TE {-w['avail_skill']:.2f}, front 7 {-w['avail_front7']:.2f}, DB {-w['avail_db']:.2f}",
         "ELWAY 0.5–1 typical, max ≈ 2"),
        ("Pythagorean exponent", f"{params['luck']['pythag']['exponent']:.2f}", "classic NFL 2.37"),
        ("Margin of exactly 3 vs a smooth curve", f"{p['margin_dist']['weights'][3]:.1f}×", "(key number)"),
        ("Model + market blend", "not tested (research R6)", "nfelo: ≈ 65% market weight optimal"),
    ]
    return ["| Parameter | MarketScope (fitted 2016–22) | Published |", "|---|---|---|",
            *[f"| {a} | {b} | {c} |" for a, b, c in rows]]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--confirm-once", action="store_true", required=True)
    ap.add_argument("--rehearse", type=int, help="rehearse on an already-scored season, writing to /tmp (no record)")
    args = ap.parse_args()
    global REPORT, RECORD
    if args.rehearse:
        if args.rehearse == ed.TEST_SEASON:
            raise SystemExit("rehearsal must use an already-scored season")
        REPORT, RECORD = Path(f"/tmp/rehearse-{args.rehearse}.md"), Path(f"/tmp/rehearse-{args.rehearse}.json")
        REPORT.unlink(missing_ok=True)
        RECORD.unlink(missing_ok=True)
    elif REPORT.exists() or RECORD.exists():
        raise SystemExit(f"{REPORT} already exists: the 2025 test has been run. It is never re-run for {MODEL}.")
    if params_sha256() != FROZEN_PARAMS_SHA256:
        raise SystemExit("params.json differs from the frozen ratings-v1 parameters")

    games, sigma, _ = prepare()
    params = json.loads(PARAMS_PATH.read_text())
    bench, tuned = benchmark_factories(games, sigma, verbose=False)
    holder = {}

    def v1():
        m, _, _ = build_model(games, sigma, name=MODEL)
        holder["m"] = m
        return m

    test = [args.rehearse or ed.TEST_SEASON]
    preds = run_models(games, {MODEL: v1, **bench}, test, allow_test=not args.rehearse)
    scores = score_table(preds, ed.REFERENCE)
    vs = {ref: score_table(preds[preds["model"].isin([MODEL, ref])], ref).set_index("model").loc[MODEL]
          for ref in ("Elo (538)", "SRS (ridge)", "market-implied ratings", "naive home field")}
    v = preds[preds["model"] == MODEL]
    cal = calibration_table(v["p_home"].to_numpy(), v["home_win"].to_numpy())
    # Cover probabilities against the closing line (pushes excluded).
    md = params["model"]["margin_dist"]
    dist = MarginDistribution(md["scale"], md["weights"])
    close = games.set_index("game_id").loc[v["game_id"], "close_margin"].to_numpy()
    pc, pp = dist.p_cover(v["margin"].to_numpy(), close)
    nopush = v["actual_margin"].to_numpy() != close
    y = (v["actual_margin"].to_numpy() > close).astype(float)[nopush]
    p = (pc / np.clip(1 - pp, 1e-9, None))[nopush]
    cover_ll = float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))

    ran_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    code_sha = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()

    def d(r, k, dg):
        return f"{r['d_' + k]:+.{dg}f} ({r['d_' + k + '_lo']:+.{dg}f} to {r['d_' + k + '_hi']:+.{dg}f})"

    L = [f"# The 2025 test of {MODEL} (MS-032b)", "",
         f"_Run once on {ran_at} (code {code_sha[:7]}, params sha256 {FROZEN_PARAMS_SHA256[:12]}). The parameters were frozen in "
         "an earlier commit, and 2025 had never been scored by any MarketScope model. This file is the record; the script "
         "refuses to run again._", "",
         f"## {test[0]} ({scores['games'].iloc[0]} games, regular season and playoffs; walk-forward)", "",
         *main_table(scores), "", *diff_table(scores, ed.REFERENCE), "",
         f"Paired against the benchmarks ({MODEL} minus benchmark; negative = better):", "",
         "| Benchmark | Δ margin MAE | Δ Brier | Δ log loss |", "|---|---|---|---|",
         *[f"| {ref} | {d(r, 'margin_mae', 2)} | {d(r, 'brier', 4)} | {d(r, 'log_loss', 4)} |" for ref, r in vs.items()], "",
         f"Probability of covering the closing line (pushes excluded, {int(nopush.sum())} games): log loss {cover_ll:.4f} vs "
         f"{math.log(2):.4f} for a coin flip.", "",
         "Reliability of the win probability:", "", "| Predicted | n | Observed |", "|---|---|---|",
         *[f"| {b} | {int(r['n'])} | {r['observed']:.2f} |" for b, r in cal.iterrows() if r["n"] > 0], "",
         "## Parameter comparison", "", *parameter_table(holder["m"], params), ""]
    REPORT.write_text("\n".join(L))
    metrics = {r["model"]: {k: (None if pd.isna(r[k]) else float(r[k])) for k in r.index if k != "model"}
               for _, r in scores.iterrows()}
    metrics["paired_vs_benchmarks"] = {ref: {k: (None if pd.isna(r[k]) else float(r[k])) for k in r.index if k.startswith("d_")}
                                       for ref, r in vs.items()}
    metrics["cover_log_loss"] = cover_ll
    RECORD.parent.mkdir(parents=True, exist_ok=True)
    RECORD.write_text(json.dumps({"model_version": MODEL, "run_kind": "test", "seasons": str(test[0]),
                                  "games": int(scores["games"].iloc[0]), "metrics": metrics,
                                  "params_sha256": FROZEN_PARAMS_SHA256, "code_sha": code_sha,
                                  "notes": "one-time test of the frozen ratings-v1 on the untouched 2025 season",
                                  "ran_at": ran_at}, indent=2))
    print("\n".join(L[4:12]))


if __name__ == "__main__":
    main()
