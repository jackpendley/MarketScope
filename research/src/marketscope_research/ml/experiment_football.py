"""MS-036 protocol (design_football.py): the v1 market-only logistic vs the same model with football
features, on the v1 split. C is chosen on validation per model; every model is refit on train +
validation and scored once on the test week; the forward check reuses the final models."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .design import DIRECTION_FEATURES, MIN_FORWARD_GAMES, MOVE_CATEGORICAL, MOVE_FEATURES
from .design_football import (
    FOOTBALL_DIRECTION_FEATURES,
    FOOTBALL_MOVE_FAMILIES,
    MIN_RATING_COVERAGE,
    PRIMARY_MODEL,
    PRIMARY_REFERENCE,
)
from .experiment import _choose_c, _parts, _sizes
from .metrics import bootstrap_scores
from .models import Constant, Logistic, add_derived


@dataclass
class FootballResult:
    target: str
    sizes: pd.DataFrame
    rating_coverage: float
    gate: bool
    chosen_c: dict[str, float]
    test_scores: pd.DataFrame  # vs the market-only logistic
    coefficients: pd.Series
    forward_scores: pd.DataFrame | None
    forward_games: int


def _variants(market: list[str], families: dict[str, list[str]]) -> dict[str, list[str]]:
    football = [c for cols in families.values() for c in cols]
    out = {PRIMARY_REFERENCE: market, PRIMARY_MODEL: market + football}
    out.update({f"market + {name}": market + cols for name, cols in families.items()})
    return out


def _run(data: pd.DataFrame, target: str, label: str, variants: dict[str, list[str]], categorical: list[str]) -> FootballResult:
    p = _parts(data)
    fit_df = pd.concat([p["train"], p["validation"]])
    coverage = float(fit_df["rating_gap"].notna().mean()) if len(fit_df) else 0.0
    chosen = {k: _choose_c(target, cols, categorical, p["train"], p["validation"]) for k, cols in variants.items()}
    models = {"constant": Constant(target)}
    models.update({k: Logistic(target, cols, categorical, chosen[k]) for k, cols in variants.items()})
    for m in models.values():
        m.fit(fit_df)
    test = p["test"]
    preds = {k: m.predict(test) for k, m in models.items()}
    scores = bootstrap_scores(test["event_id"].to_numpy(), test[target].to_numpy(), preds, PRIMARY_REFERENCE)
    forward = p["forward"]
    fwd_games = forward["event_id"].nunique()
    fwd = None
    if fwd_games >= MIN_FORWARD_GAMES:
        fwd = bootstrap_scores(forward["event_id"].to_numpy(), forward[target].to_numpy(),
                               {k: m.predict(forward) for k, m in models.items()}, PRIMARY_REFERENCE)
    return FootballResult(label, _sizes(p, target), coverage, coverage >= MIN_RATING_COVERAGE, chosen, scores,
                          models[PRIMARY_MODEL].coefficients(), fwd, fwd_games)


def run_move_football(df: pd.DataFrame) -> FootballResult:
    data = add_derived(df[df["moved"].notna()]).assign(moved=lambda d: d["moved"].astype(int))
    return _run(data, "moved", "move >= 0.5 within 24 h", _variants(MOVE_FEATURES, FOOTBALL_MOVE_FAMILIES),
                MOVE_CATEGORICAL)


def run_direction_football(df: pd.DataFrame) -> FootballResult:
    data = add_derived(df[df["moved"] == 1]).assign(toward_home=lambda d: (d["direction"] == "home").astype(int))
    variants = {PRIMARY_REFERENCE: DIRECTION_FEATURES, PRIMARY_MODEL: DIRECTION_FEATURES + FOOTBALL_DIRECTION_FEATURES,
                **{f"market + {c}": DIRECTION_FEATURES + [c] for c in FOOTBALL_DIRECTION_FEATURES}}
    return _run(data, "toward_home", "direction of the move (toward home), given a move", variants, [])
