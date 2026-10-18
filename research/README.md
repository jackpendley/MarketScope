# MarketScope research

Reproducible studies over MarketScope's stored observations (Python 3.11+, pandas). Studies only **read** the database: the session is opened read-only (`data.py`).

## Setup

```bash
cd research
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m pytest -q        # unit tests (no database needed)
```

## Studies

| Study                                                                      | Code                                              | Report                              |
| -------------------------------------------------------------------------- | ------------------------------------------------- | ----------------------------------- |
| Does an outlier book predict consensus convergence within 24 h? (spec §15) | `src/marketscope_research/outlier_convergence.py` | `reports/outlier-convergence-v1.md` |
| Market-movement model: data gate (MS-024, spec §16)                        | `src/marketscope_research/ml/`                    | `reports/market-ml-gate-v1.md`      |

Run against a database (production via Jack's local `SUPABASE_DATABASE_URL`, or a local demo/e2e DB with `--sources synthetic`):

```bash
PYTHONPATH=src STUDY_DATABASE_URL=postgres://localhost:5432/marketscope_demo \
  .venv/bin/python -m marketscope_research.run_outlier_convergence --sources synthetic --out /tmp/synthetic.md
```

## Market-movement model: pre-registration (2026-10-18)

Fixed in `src/marketscope_research/ml/design.py` before any label, class balance or model result was computed (only per-week game and snapshot counts were looked at, to size the split):

- **Target:** at snapshot t, 168 h to 24 h before kickoff: does the board consensus home spread move ≥ 0.5 pts by t + 24 h? The future value is the pregame consensus snapshot nearest t + 24 h within ±3 h; otherwise the label is missing. Secondary target: direction (toward home or away), given a move.
- **Split, chronological and grouped by game:** train weeks 1–3, validation week 4, test week 5 (all imported history). Weeks ≥ 6 (live collection, a different book mix) are a separate forward check, reported when ≥ 15 games are labelled.
- **Gate:** ≥ 60 games, ≥ 150 positives, ≥ 15 test games, ≥ 30 test positives. If any check fails, the result is exploratory only.
- **Leakage audit:** every feature must be unchanged when all observations after t are perturbed (`ml/audit.py`). A planted leaky feature fails it (`tests/test_ml_dataset.py`).

## Principles

- **Pre-registered designs:** the event definition, outcome, baseline, and minimum sample are fixed in code and in the report _before_ results are read. Below the minimum, the verdict is **inconclusive**.
- **Point-in-time:** an event uses only data observable at its snapshot, never future observations.
- **Game-clustered inference:** observations from one game are correlated, so bootstrap CIs resample games.
- **Independent cross-check:** consensus is recomputed in Python from raw observations and compared with the value the TypeScript signal engine stored.
- **Synthetic data is never mixed with real data,** and reports on it are labeled as pipeline validation only.
- **Committed reports contain aggregates only,** never raw provider prices (ADR-010, ADR-022).
