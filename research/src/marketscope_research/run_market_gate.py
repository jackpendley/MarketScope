"""MS-024: build the market-movement dataset, run the leakage audit and the data gate, and
write a Markdown report (aggregates only).

    STUDY_DATABASE_URL=... .venv/bin/python -m marketscope_research.run_market_gate \
        --out reports/market-ml-gate-v1.md
"""

from __future__ import annotations

import argparse
import os
import subprocess
from datetime import datetime, timezone

import pandas as pd

from .data import connect, load_home_spreads, load_kickoffs, load_totals
from .ml import design
from .ml.audit import leakage_audit
from .ml.dataset import build_dataset
from .ml.features import build_features
from .ml.gate import evaluate_gate, label_coverage, missingness, rate_by, split_summary


def pct(x: float) -> str:
    return "n/a" if x != x else f"{100 * x:.1f}%"


def md_table(df: pd.DataFrame, formats: dict[str, str] | None = None, index: bool = True) -> str:
    formats = formats or {}
    frame = df.reset_index() if index else df
    cols = list(frame.columns)
    out = ["| " + " | ".join(str(c) for c in cols) + " |", "|" + "---|" * len(cols)]
    for _, row in frame.iterrows():
        cells = []
        for c in cols:
            v = row[c]
            if formats.get(c) == "pct":
                cells.append(pct(float(v)))
            elif isinstance(v, float):
                cells.append(f"{v:.2f}")
            else:
                cells.append(str(v))
        out.append("| " + " | ".join(cells) + " |")
    return "\n".join(out)


def lead_bucket(hours: pd.Series) -> pd.Series:
    return pd.cut(hours, bins=[24, 48, 72, 120, 168], right=True, include_lowest=True,
                  labels=["24–48 h", "48–72 h", "72–120 h", "120–168 h"])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("--sources", default="the-odds-api,oddspapi")
    parser.add_argument("--audit-samples", type=int, default=60)
    args = parser.parse_args()
    dsn = os.environ.get("STUDY_DATABASE_URL")
    if not dsn:
        raise SystemExit("Set STUDY_DATABASE_URL (read-only use).")
    sources = [s.strip() for s in args.sources.split(",") if s.strip()]
    synthetic = "synthetic" in sources
    if synthetic and len(sources) > 1:
        raise SystemExit("Never mix synthetic and real data.")

    with connect(dsn) as conn:
        spreads = load_home_spreads(conn, sources)
        totals = load_totals(conn, sources)
        kickoffs = load_kickoffs(conn)

    df = build_dataset(spreads, totals, kickoffs)
    violations = leakage_audit(build_features, spreads, totals, kickoffs, samples=args.audit_samples)
    gate = evaluate_gate(df)

    df["lead"] = lead_bucket(df["hours_to_kickoff"])
    try:
        commit = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True).strip()
    except Exception:
        commit = "unknown"

    gate_lines = "\n".join(f"| {name} | {'pass' if ok else '**FAIL**'} |" for name, ok in gate.checks.items())
    verdict = (
        "**Gate passed.** Modelling (MS-025) may proceed on the pre-registered split."
        if gate.passed
        else "**Gate failed.** Per the pre-registration, publish exploratory analysis only; no model claims."
    )
    audit_text = (
        f"**Passed** on {args.audit_samples} sampled snapshots: perturbing every observation after t changed no feature."
        if not violations
        else "**FAILED**: " + ", ".join(f"`{k}` ({v})" for k, v in violations.items())
    )

    report = f"""# Market-movement model: data gate (MS-024, v1)

{"> **SYNTHETIC DATA: pipeline validation only.**" + chr(10) if synthetic else ""}
_Generated {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")} · commit `{commit}` · sources `{", ".join(sources)}` ·
reproduce with `research/src/marketscope_research/run_market_gate.py`. Design: `research/src/marketscope_research/ml/design.py`
(pre-registered 2026-10-18, before any label was computed)._

## Question

At a snapshot t between {design.MAX_LEAD_HOURS} h and {design.MIN_LEAD_HOURS} h before kickoff, will the board consensus
home spread move by at least {design.MOVE_THRESHOLD} points by t + {design.HORIZON_HOURS} h? The future value is the pregame
consensus snapshot nearest t + {design.HORIZON_HOURS} h within ±{design.TOLERANCE_HOURS} h; without one the label is missing,
never imputed. Secondary target: the direction of the move, given one.

## Verdict

{verdict}

| Pre-registered check | Result |
|---|---|
{gate_lines}

Core (train + validation + test): **{gate.games} games, {gate.positives} positive snapshots**; test: {gate.test_games} games,
{gate.test_positives} positives. Live forward check: {gate.forward_games} games labelled so far
({"ready" if gate.forward_ready else f"pending until ≥ {design.MIN_FORWARD_GAMES} games"}).

## Leakage audit

{audit_text}

## Splits (chronological, grouped by game)

{md_table(split_summary(df), {"positive_rate": "pct"}, index=False)}

Eligible snapshots that received a label: {pct(label_coverage(df))}. Weeks 1–5 are imported history (OddsPapi derived
6-hourly snapshots: Pinnacle and Caesars present, BetMGM absent); weeks ≥ 6 are live collection (BetMGM present, Caesars
and Pinnacle absent). The source changes exactly at the forward boundary, so the forward check doubles as a test of
transfer between sources.

## Positive rate by time to kickoff

{md_table(rate_by(df, "lead"), {"positive_rate": "pct"})}

## Positive rate by week

{md_table(rate_by(df, "week"), {"positive_rate": "pct"})}

## Feature missingness (labelled rows)

{md_table(missingness(df), {"missing_overall": "pct", "missing_imported": "pct", "missing_live": "pct"})}

`move_6h`/`move_24h` are missing when no snapshot lies within ±3 h of the lag; `pinnacle_dev` is structurally missing on
live data (Pinnacle is imported only), so it can only be evaluated on weeks 1–5.

## Notes

- Committed reports contain aggregates only, never raw lines or prices.
- Next (MS-025): baselines (majority, empirical rate by lead time, volatility heuristic, logistic regression) on this split,
  scored by Brier, log loss and calibration with game-clustered CIs.
"""
    with open(args.out, "w") as fh:
        fh.write(report)
    print(f"wrote {args.out}: gate {'passed' if gate.passed else 'failed'}, audit {'ok' if not violations else violations}")


if __name__ == "__main__":
    main()
