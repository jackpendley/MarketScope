"""Run the outlier-convergence study and write a Markdown report.

    STUDY_DATABASE_URL=... .venv/bin/python -m marketscope_research.run_outlier_convergence \
        --out reports/outlier-convergence-v1.md [--sources synthetic]
"""

from __future__ import annotations

import argparse
import os
import subprocess
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from .consensus import consensus_series
from .data import connect, load_divergence_events, load_home_spreads, load_kickoffs
from .outlier_convergence import (
    breakdown,
    toward_share_among_moved,
    HORIZON_HOURS,
    MIN_EVENTS,
    MIN_GAMES,
    TOLERANCE_HOURS,
    label_outcomes,
    summarize,
    unconditional_move_rate,
)


def pct(x: float) -> str:
    return "n/a" if x != x else f"{100 * x:.1f}%"


def breakdown_md(t: pd.DataFrame, label: str) -> str:
    lines = [
        f"| {label} | Events | Games | Toward | Away | None | Toward rate | Toward share of moves |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for key, row in t.iterrows():
        share = "n/a" if pd.isna(row["toward_share_of_moves"]) else pct(row["toward_share_of_moves"])
        lines.append(
            f"| {key} | {int(row['events'])} | {int(row['games'])} | {int(row['toward'])} | {int(row['away'])} | "
            f"{int(row['none'])} | {pct(row['toward_rate'])} | {share} |"
        )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument(
        "--sources",
        default="the-odds-api,oddspapi",
        help="comma-separated: the-odds-api, oddspapi (real) or synthetic (validation only)",
    )
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
        event_ids = sorted(spreads["event_id"].unique().tolist())
        events = load_divergence_events(conn, event_ids)
        kickoffs = load_kickoffs(conn)

    consensus = consensus_series(spreads)
    # Independent cross-check: Python consensus at each event's snapshot vs the stored value.
    merged = events.merge(
        consensus.rename(columns={"observed_at": "detected_at", "consensus": "py_consensus"}),
        on=["event_id", "detected_at"],
        how="left",
    )
    mismatches = int((~np.isclose(merged["py_consensus"], merged["consensus"], equal_nan=False)).sum())

    labelled = label_outcomes(events, consensus, kickoffs)
    any_move, eligible = unconditional_move_rate(consensus, kickoffs)
    r = summarize(labelled, any_move, eligible)

    # Exploratory (not pre-registered): direction among moves, per source and per book.
    labelled["source"] = labelled["event_id"].map(spreads.groupby("event_id")["source"].first())
    share, (share_lo, share_hi), n_moved = toward_share_among_moved(labelled)
    by_source = breakdown_md(breakdown(labelled, "source"), "Source")
    by_book = breakdown_md(breakdown(labelled, "bookmaker_key"), "Diverging book")

    try:
        commit = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True).strip()
    except Exception:
        commit = "unknown"
    first, last = spreads["observed_at"].min(), spreads["observed_at"].max()
    snapshots = spreads["observed_at"].nunique()
    games_by_source = spreads.groupby("source")["event_id"].nunique().to_dict()

    if not r.conclusive:
        verdict = (
            f"**Inconclusive: sample below the pre-registered minimum** ({r.events_scored} scored events from "
            f"{r.games_scored} games; minimum {MIN_EVENTS} events from {MIN_GAMES} games). No claim is made "
            "either way. Re-run as history accumulates."
        )
    else:
        lo, hi = r.ci
        if lo > r.chance_toward_rate:
            verdict = (
                f"The consensus moved toward the diverging book in {pct(r.toward_rate)} of events "
                f"(95% game-clustered CI {pct(lo)}–{pct(hi)}), above the {pct(r.chance_toward_rate)} chance baseline."
            )
        elif hi < r.chance_toward_rate:
            verdict = (
                f"The consensus moved toward the diverging book in only {pct(r.toward_rate)} of events "
                f"(CI {pct(lo)}–{pct(hi)}), below the {pct(r.chance_toward_rate)} chance baseline."
            )
        else:
            verdict = (
                f"No detectable effect: toward-rate {pct(r.toward_rate)} (CI {pct(lo)}–{pct(hi)}) overlaps the "
                f"{pct(r.chance_toward_rate)} chance baseline. A null result."
            )

    report = f"""# Study: does an outlier book predict consensus convergence? (v1)

{"> **SYNTHETIC DATA: pipeline validation only. Not a finding about real markets.**" + chr(10) if synthetic else ""}
_Generated {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")} · commit `{commit}` · sources `{", ".join(sources)}` ·
reproduce with `research/src/marketscope_research/run_outlier_convergence.py`._

## Question

When a sportsbook's home spread diverges from the same-snapshot consensus, does the rest of the market
(the consensus) move toward that book's line within the next {HORIZON_HOURS} hours more often than chance?

## Pre-registered design

- **Events:** `book_divergence` v1 onsets: a book ≥ 0.5 pts from the median of ≥ 3 target books in one
  snapshot (`docs/SIGNAL_DEFINITIONS.md`). Point-in-time: uses only data observed at the event's snapshot.
- **Outcome:** consensus at the snapshot nearest t + {HORIZON_HOURS} h within ±{TOLERANCE_HOURS} h, pregame, ≥ 3 books.
  *toward* = moved in the direction of the book's deviation; *away* = opposite; *none* = unchanged. Events with
  no eligible horizon snapshot are excluded and counted.
- **Baselines:** the unconditional share of eligible snapshots whose consensus changed by the horizon, in either
  direction; *toward by chance* = half of it.
- **Inference:** 95% bootstrap CI (5,000 resamples) resampling **games**, since events within a game are correlated.
- **Minimum sample:** ≥ {MIN_EVENTS} scored events from ≥ {MIN_GAMES} games, otherwise inconclusive.

## Data

| | |
|---|---|
| Observations (home spreads, pregame) | {len(spreads):,} |
| Snapshots | {snapshots} |
| Games | {len(event_ids)} ({", ".join(f"{k}: {v}" for k, v in sorted(games_by_source.items()))}) |
| Observed range | {first:%Y-%m-%d %H:%M} – {last:%Y-%m-%d %H:%M} UTC |
| Divergence events | {r.events_total} |
| Events with an eligible horizon | {r.events_scored} (from {r.games_scored} games) |
| Consensus cross-check (Python vs stored) | {len(events) - mismatches}/{len(events)} match |

## Results

| Outcome | Events |
|---|---|
| Consensus moved toward the book | {r.toward} |
| Moved away | {r.away} |
| No change | {r.none} |
| **Toward rate** | **{pct(r.toward_rate)}** (95% game-clustered CI {pct(r.ci[0])}–{pct(r.ci[1])}) |
| Any consensus move at horizon (all snapshots) | {pct(r.any_move_rate)} of {r.baseline_eligible} |
| Toward by chance (baseline) | {pct(r.chance_toward_rate)} |

**Verdict:** {verdict}

## Exploratory robustness checks (added after seeing v1 results; not pre-registered)

The chance baseline is unconditional, but divergences tend to occur while a market is already moving, so
the baseline may understate how often the consensus moves after one. A check that doesn't depend on it:
**among events where the consensus moved, what share moved toward the book?** If divergence carried no
directional information, that share would be about 50%.

- Toward share of moves: **{pct(share)}** of {n_moved} (95% game-clustered CI {pct(share_lo)}–{pct(share_hi)})

{by_source}

{by_book}

Treat these as descriptive. They were chosen after the primary result was known, and per-group cells are small.

## Limitations

- **Polling resolution:** about 4 snapshots/day, so the horizon snapshot can be up to {TOLERANCE_HOURS} h from t + {HORIZON_HOURS} h.
- **Coverage:** only board books count toward consensus (Pinnacle is stored but excluded). Live snapshots lack
  Caesars (paid plan) and imported history lacks BetMGM (failed validation), so most snapshots have 4 books.
- **Derived snapshots:** imported games are resampled from change logs. If the provider missed a book's update,
  that book looks stale-but-divergent until its next recorded change, and the consensus can appear to move
  "toward" it when the other books revert. Validation agreement was 85–100% for the books used, not 100%.
- **Source imbalance:** almost all scored events come from imported history (see the per-source table).
- **Sources:** live Odds API snapshots (from 2026-10-16) and OddsPapi line-move history imported for
  earlier games as derived 6-hourly snapshots (ADR-026). Each game uses exactly one source. OddsPapi
  excludes BetMGM and carries quotes forward between recorded changes (its change-log semantics).
- **Cause:** a consensus moving toward a book does not mean the book "knew" anything. Shared news (injuries,
  weather) moves all books, and the diverging book may simply have updated first.
- **The chance baseline assumes symmetric direction.** That's reasonable for a first pass, but it's an
  assumption, not a fact.
"""
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w") as f:
        f.write(report)
    print(f"wrote {args.out}: {r.events_scored} scored events, {r.games_scored} games, conclusive={r.conclusive}, "
          f"cross-check {len(events) - mismatches}/{len(events)}")


if __name__ == "__main__":
    main()
