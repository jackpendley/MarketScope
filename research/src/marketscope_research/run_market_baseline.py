"""MS-025: baselines and logistic regression for the market-movement targets; writes a report.

    STUDY_DATABASE_URL=... .venv/bin/python -m marketscope_research.run_market_baseline \
        --out reports/market-baseline-v1.md
"""

from __future__ import annotations

import argparse
import os
import subprocess
from datetime import datetime, timezone

import pandas as pd

from .data import connect, load_home_spreads, load_kickoffs, load_totals
from .ml import design
from .ml.dataset import build_dataset
from .ml.experiment import ExperimentResult, run_direction, run_move
from .run_market_gate import md_table, pct


def ci(row: pd.Series, col: str, lo: str, hi: str, digits: int = 4) -> str:
    return f"{row[col]:.{digits}f} ({row[lo]:.{digits}f} to {row[hi]:.{digits}f})"


def scores_md(t: pd.DataFrame, reference: str) -> str:
    lines = [
        f"| Model | Brier (95% CI) | Log loss (95% CI) | AUC (95% CI) | Δ Brier vs {reference} | Δ log loss vs {reference} |",
        "|---|---|---|---|---|---|",
    ]
    for _, r in t.iterrows():
        auc = "n/a" if r["auc"] != r["auc"] else ci(r, "auc", "auc_lo", "auc_hi", 3)
        lines.append(
            f"| {r['model']} | {ci(r, 'brier', 'brier_lo', 'brier_hi')} | {ci(r, 'log_loss', 'log_loss_lo', 'log_loss_hi')} | "
            f"{auc} | {ci(r, 'd_brier', 'd_brier_lo', 'd_brier_hi')} | {ci(r, 'd_log_loss', 'd_ll_lo', 'd_ll_hi')} |"
        )
    return "\n".join(lines)


def beats(t: pd.DataFrame, model: str) -> str:
    r = t[t["model"] == model].iloc[0]
    if r["d_ll_hi"] < 0 and r["d_brier_hi"] < 0:
        return "better (both CIs below 0)"
    if r["d_ll_lo"] > 0 and r["d_brier_lo"] > 0:
        return "worse (both CIs above 0)"
    return "not distinguishable (a CI includes 0)"


def calibration_md(cal: dict[str, pd.DataFrame]) -> str:
    parts = []
    for name, t in cal.items():
        t = t.reset_index()
        t["bin"] = t["bin"].astype(str)
        parts.append(f"**{name}**\n\n" + md_table(t, {"mean_predicted": "pct", "observed_rate": "pct"}, index=False))
    return "\n\n".join(parts)


def coef_md(coefs: pd.Series, top: int = 12) -> str:
    rows = [f"| {name} | {value:+.3f} |" for name, value in coefs.head(top).items()]
    return "| Feature (standardized) | Coefficient |\n|---|---|\n" + "\n".join(rows)


def section(r: ExperimentResult, headline: str) -> str:
    out = [
        md_table(r.sizes, {"positive_rate": "pct"}, index=False),
        "",
        f"Chosen L2 strength C on validation: {', '.join(f'{k} = {v}' for k, v in r.chosen_c.items())}.",
        "",
        "### Test week (scored once)",
        "",
        scores_md(r.test_scores, "constant"),
        "",
        f"**{headline}** vs the constant baseline: {beats(r.test_scores, 'logistic')}.",
    ]
    if r.test_vs_recent is not None:
        out += ["", "Against the recent-week base rate:", "", scores_md(r.test_vs_recent, "recent-week rate"), "",
                f"Logistic regression vs the recent-week rate: {beats(r.test_vs_recent, 'logistic')}."]
    if r.by_lead is not None and not r.by_lead.empty:
        out += ["", "### Brier score by time to kickoff (test)", "", md_table(r.by_lead, {"positive_rate": "pct"}, index=False)]
    if r.threshold:
        th = r.threshold
        out += ["", f"At the validation-chosen threshold p ≥ {th['threshold']:.3f}, logistic regression flags {th['flagged']} test "
                f"snapshots: precision {pct(th['precision'])}, recall {pct(th['recall'])}."]
    out += ["", "### Calibration (test)", "", calibration_md(r.calibration), "",
            "### Logistic regression coefficients (final fit)", "", coef_md(r.coefficients)]
    if r.forward_scores is not None:
        out += ["", "### Forward check (live weeks ≥ 6)", "", scores_md(r.forward_scores, "constant")]
    else:
        out += ["", f"Forward check (live weeks ≥ 6): pending, {r.forward_games} games labelled "
                f"(needs {design.MIN_FORWARD_GAMES})."]
    return "\n".join(out)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("--sources", default="the-odds-api,oddspapi")
    args = parser.parse_args()
    dsn = os.environ.get("STUDY_DATABASE_URL")
    if not dsn:
        raise SystemExit("Set STUDY_DATABASE_URL (read-only use).")
    sources = [s.strip() for s in args.sources.split(",") if s.strip()]
    if "synthetic" in sources and len(sources) > 1:
        raise SystemExit("Never mix synthetic and real data.")
    with connect(dsn) as conn:
        df = build_dataset(load_home_spreads(conn, sources), load_totals(conn, sources), load_kickoffs(conn))

    move, direction = run_move(df), run_direction(df)
    try:
        commit = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True).strip()
    except Exception:
        commit = "unknown"

    report = f"""# Market-movement model: baselines (MS-025, v1)

{"> **SYNTHETIC DATA: pipeline validation only.**" + chr(10) if "synthetic" in sources else ""}
_Generated {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")} · commit `{commit}` · sources `{", ".join(sources)}` ·
reproduce with `research/src/marketscope_research/run_market_baseline.py`. Data gate and features: `market-ml-gate-v1.md`._

## Protocol (pre-registered in `ml/design.py` before any model was fit)

- Hyperparameters (logistic L2 strength C from {list(design.LR_C_GRID)}) are chosen by validation log loss with models fit
  on the training weeks; every model is then **refit on train + validation and scored once on the test week**.
- Scores: Brier, log loss, AUC; 95% CIs and paired differences from {design.BOOTSTRAP_RESAMPLES:,} bootstrap resamples of
  **games** (snapshots within a game are correlated). A model "beats" a baseline only when both the Brier and log-loss
  difference CIs lie entirely below zero.
- Baselines: constant (train + validation rate); recent-week rate (the last fitting week's rate, added after the gate report
  showed the rate rising by week, before any model was fit); smoothed rate by time to kickoff; volatility heuristic
  (smoothed rate by recent consensus changes and 24 h movement).
- The headline logistic model uses only features present in both sources so it can run on live data; Pinnacle is an ablation.

## 1. Will the consensus move ≥ {design.MOVE_THRESHOLD} pts within {design.HORIZON_HOURS} h?

{section(move, "Logistic regression")}

## 2. Direction, given a move (toward the home side vs the away side)

{section(direction, "Logistic regression")}

## Limitations

- One season, five weeks of imported history and one test week (15 games): CIs are wide and a single week can be atypical.
- The positive rate drifts upward by week, so any fixed base rate is miscalibrated on later weeks.
- Imported snapshots are derived from change logs (ADR-026); live snapshots come from a different book mix. The forward
  check measures transfer between them once enough live games are labelled.
- These models describe market behaviour. Predicting a line move is not evidence of profitable betting after the vig.
"""
    with open(args.out, "w") as fh:
        fh.write(report)
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
