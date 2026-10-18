"""MS-025 protocol: select hyperparameters on validation, refit on train + validation, score
once on the test week; the forward (live) check uses the same final models."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .design import (
    DIRECTION_FEATURES,
    DIRECTION_PINNACLE_ABLATION,
    LR_C_GRID,
    MIN_FORWARD_GAMES,
    MOVE_CATEGORICAL,
    MOVE_FEATURES,
    PINNACLE_ABLATION,
)
from .metrics import best_f1_threshold, bootstrap_scores, calibration_table, log_loss, precision_recall, score
from .models import (
    BucketRate,
    Constant,
    Logistic,
    RecentWeekRate,
    add_derived,
    lead_bucket,
    sign_bucket,
    volatility_bucket,
)


@dataclass
class ExperimentResult:
    target: str
    sizes: pd.DataFrame
    chosen_c: dict[str, float]
    test_scores: pd.DataFrame  # bootstrap table vs the constant baseline
    test_vs_recent: pd.DataFrame | None
    calibration: dict[str, pd.DataFrame]
    by_lead: pd.DataFrame | None
    threshold: dict[str, float] | None
    coefficients: pd.Series
    forward_scores: pd.DataFrame | None
    forward_games: int
    notes: list[str] = field(default_factory=list)


def _choose_c(target: str, numeric: list[str], categorical: list[str], train: pd.DataFrame, val: pd.DataFrame) -> float:
    losses = {}
    for c in LR_C_GRID:
        m = Logistic(target, numeric, categorical, c).fit(train)
        losses[c] = log_loss(val[target].to_numpy(), m.predict(val))
    return min(losses, key=losses.get)


def _sizes(parts: dict[str, pd.DataFrame], target: str) -> pd.DataFrame:
    return pd.DataFrame(
        [{"split": k, "games": v["event_id"].nunique(), "rows": len(v), "positives": int(v[target].sum()),
          "positive_rate": float(v[target].mean()) if len(v) else float("nan")} for k, v in parts.items()]
    )


def _parts(df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    return {s: df[df["split"] == s] for s in ["train", "validation", "test", "forward"]}


def run_move(df: pd.DataFrame) -> ExperimentResult:
    target = "moved"
    data = add_derived(df[df["moved"].notna()]).assign(moved=lambda d: d["moved"].astype(int))
    p = _parts(data)
    fit_df = pd.concat([p["train"], p["validation"]])
    c_main = _choose_c(target, MOVE_FEATURES, MOVE_CATEGORICAL, p["train"], p["validation"])
    c_pin = _choose_c(target, MOVE_FEATURES + PINNACLE_ABLATION, MOVE_CATEGORICAL, p["train"], p["validation"])

    # Threshold for precision/recall: best F1 of the train-fit model on validation.
    val_model = Logistic(target, MOVE_FEATURES, MOVE_CATEGORICAL, c_main).fit(p["train"])
    threshold = best_f1_threshold(p["validation"][target].to_numpy(), val_model.predict(p["validation"]))

    models = {
        "constant": Constant(target),
        "recent-week rate": RecentWeekRate(target),
        "rate by lead time": BucketRate(target, lead_bucket, "rate by lead time"),
        "volatility heuristic": BucketRate(target, volatility_bucket, "volatility heuristic"),
        "logistic": Logistic(target, MOVE_FEATURES, MOVE_CATEGORICAL, c_main),
        "logistic + Pinnacle": Logistic(target, MOVE_FEATURES + PINNACLE_ABLATION, MOVE_CATEGORICAL, c_pin),
    }
    for m in models.values():
        m.fit(fit_df)
    test = p["test"]
    y, games = test[target].to_numpy(), test["event_id"].to_numpy()
    preds = {k: m.predict(test) for k, m in models.items()}
    scores = bootstrap_scores(games, y, preds, reference="constant")
    vs_recent = bootstrap_scores(games, y, preds, reference="recent-week rate")

    leads = lead_bucket(test)
    by_lead = []
    for bucket in ["24-48", "48-72", "72-120", "120+"]:
        mask = (leads == bucket).to_numpy()
        if mask.sum() == 0:
            continue
        row = {"lead_h": bucket, "rows": int(mask.sum()), "positive_rate": float(y[mask].mean())}
        for k in ["constant", "rate by lead time", "volatility heuristic", "logistic"]:
            row[f"brier: {k}"] = score(y[mask], preds[k][mask])["brier"]
        by_lead.append(row)

    forward = p["forward"]
    fwd_games = forward["event_id"].nunique()
    fwd_scores = None
    if fwd_games >= MIN_FORWARD_GAMES:
        fwd_preds = {k: m.predict(forward) for k, m in models.items() if k != "logistic + Pinnacle"}
        fwd_scores = bootstrap_scores(forward["event_id"].to_numpy(), forward[target].to_numpy(), fwd_preds, "constant")

    return ExperimentResult(
        target="move >= 0.5 within 24 h",
        sizes=_sizes(p, target),
        chosen_c={"logistic": c_main, "logistic + Pinnacle": c_pin},
        test_scores=scores,
        test_vs_recent=vs_recent,
        calibration={k: calibration_table(y, preds[k]) for k in ["constant", "recent-week rate", "logistic"]},
        by_lead=pd.DataFrame(by_lead),
        threshold={**precision_recall(y, preds["logistic"], threshold)},
        coefficients=models["logistic"].coefficients(),
        forward_scores=fwd_scores,
        forward_games=fwd_games,
    )


def run_direction(df: pd.DataFrame) -> ExperimentResult:
    target = "toward_home"
    moved = df[df["moved"] == 1]
    data = add_derived(moved).assign(toward_home=lambda d: (d["direction"] == "home").astype(int))
    p = _parts(data)
    fit_df = pd.concat([p["train"], p["validation"]])
    c_main = _choose_c(target, DIRECTION_FEATURES, [], p["train"], p["validation"])
    c_pin = _choose_c(target, DIRECTION_FEATURES + DIRECTION_PINNACLE_ABLATION, [], p["train"], p["validation"])
    models = {
        "constant": Constant(target),
        "outlier-direction rule": BucketRate(target, sign_bucket("outlier_dev"), "outlier-direction rule"),
        "momentum rule": BucketRate(target, sign_bucket("move_24h"), "momentum rule"),
        "logistic": Logistic(target, DIRECTION_FEATURES, [], c_main),
        "logistic + Pinnacle": Logistic(target, DIRECTION_FEATURES + DIRECTION_PINNACLE_ABLATION, [], c_pin),
    }
    for m in models.values():
        m.fit(fit_df)
    test = p["test"]
    y, games = test[target].to_numpy(), test["event_id"].to_numpy()
    preds = {k: m.predict(test) for k, m in models.items()}
    forward = p["forward"]
    return ExperimentResult(
        target="direction of the move (toward home), given a move",
        sizes=_sizes(p, target),
        chosen_c={"logistic": c_main, "logistic + Pinnacle": c_pin},
        test_scores=bootstrap_scores(games, y, preds, reference="constant"),
        test_vs_recent=None,
        calibration={"logistic": calibration_table(y, preds["logistic"])},
        by_lead=None,
        threshold=None,
        coefficients=models["logistic"].coefficients(),
        forward_scores=None,
        forward_games=forward["event_id"].nunique(),
    )
