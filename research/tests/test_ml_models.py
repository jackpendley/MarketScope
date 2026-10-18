import numpy as np
import pandas as pd

from marketscope_research.ml.experiment import run_direction, run_move
from marketscope_research.ml.features import FEATURES
from marketscope_research.ml.metrics import bootstrap_scores, brier, calibration_table, log_loss, precision_recall
from marketscope_research.ml.models import BucketRate, Constant, RecentWeekRate, volatility_bucket


def synthetic_dataset(seed: int = 0) -> pd.DataFrame:
    """A dataset where recent volatility genuinely predicts moves, and the outlier book
    predicts the direction (synthetic: pipeline validation only)."""
    rng = np.random.default_rng(seed)
    rows = []
    for g in range(100):
        week = 1 + g // 16
        for i in range(20):
            changes = int(rng.integers(0, 4))
            p = 0.05 + 0.15 * changes
            moved = rng.random() < p
            outlier = float(rng.choice([-0.5, 0.0, 0.5]))
            home = (rng.random() < (0.8 if outlier < 0 else 0.2 if outlier > 0 else 0.5)) if moved else None
            row = {f: 0.0 for f in FEATURES}
            row.update(
                event_id=f"g{g}", t=pd.Timestamp("2026-09-01", tz="UTC") + pd.Timedelta(hours=6 * i), week=week,
                split={1: "train", 2: "train", 3: "train", 4: "validation", 5: "test"}.get(week, "forward"),
                changes_48h=changes, abs_move_24h=0.5 * (changes > 1), hours_to_kickoff=24 + 6 * i, outlier_dev=outlier,
                pinnacle_dev=np.nan if week >= 6 else outlier, dow_et=i % 7, moved=float(moved),
                direction=None if home is None else ("home" if home else "away"),
            )
            rows.append(row)
    return pd.DataFrame(rows)


def test_metrics_basics():
    y = np.array([0, 1, 1, 0])
    assert brier(y, y.astype(float)) == 0
    assert np.isclose(log_loss(y, np.full(4, 0.5)), np.log(2))
    pr = precision_recall(y, np.array([0.1, 0.9, 0.4, 0.6]), 0.5)
    assert pr["flagged"] == 2 and pr["precision"] == 0.5 and pr["recall"] == 0.5
    cal = calibration_table(y, np.array([0.05, 0.95, 0.95, 0.05]))
    assert cal["n"].sum() == 4


def test_bootstrap_difference_is_zero_against_itself():
    games = np.repeat(np.arange(10), 5)
    y = (np.arange(50) % 3 == 0).astype(int)
    p = np.full(50, y.mean())
    t = bootstrap_scores(games, y, {"a": p, "b": p.copy()}, reference="a")
    row = t[t["model"] == "b"].iloc[0]
    assert row["d_brier"] == 0 and row["d_brier_lo"] == 0 and row["d_brier_hi"] == 0


def test_baselines():
    df = pd.DataFrame({"moved": [0, 0, 1, 1, 1, 0], "week": [1, 1, 2, 2, 2, 2],
                       "changes_48h": [0, 0, 2, 2, 2, 0], "abs_move_24h": [0, 0, 1, 1, 1, 0]})
    assert Constant("moved").fit(df).predict(df)[0] == 0.5
    assert RecentWeekRate("moved").fit(df).predict(df)[0] == 0.75
    v = BucketRate("moved", volatility_bucket, "v").fit(df).predict(df)
    assert v[2] > v[0]  # the volatile bucket predicts a higher rate (shrunk toward 0.5)


def test_experiment_finds_a_real_signal_on_synthetic_data():
    df = synthetic_dataset()
    move = run_move(df)
    lr = move.test_scores.set_index("model").loc["logistic"]
    assert lr["d_ll_hi"] < 0  # beats the constant baseline with a CI below zero
    assert move.forward_scores is not None and move.forward_games >= 15
    direction = run_direction(df)
    rule = direction.test_scores.set_index("model").loc["outlier-direction rule"]
    assert rule["d_ll_hi"] < 0
