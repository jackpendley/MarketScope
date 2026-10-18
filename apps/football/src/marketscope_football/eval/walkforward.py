"""Walk-forward runner: for every (season, week) slot in kickoff order, the model predicts the
slot's games from what it has been shown so far, then is shown the slot's results.

Point-in-time is structural, not a convention: `predict` receives the slot's games with every
result column removed, and `update` is called only after the slot's predictions are recorded.
So a prediction can depend only on games from earlier slots (tested: truncation invariance and
a planted model that reads a result column fails).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Protocol

import pandas as pd

from .data import RESULT_COLUMNS
from .design import TEST_SEASON


class Model(Protocol):
    name: str

    def predict(self, games: pd.DataFrame) -> pd.DataFrame:
        """Index-aligned with `games`; columns `margin` (expected home margin), `p_home`, and
        optionally `total`."""
        ...

    def update(self, results: pd.DataFrame) -> None:
        """Learn from a slot's completed games (all columns, including results)."""
        ...


class HeldOutSeasonError(RuntimeError):
    pass


def slots(games: pd.DataFrame) -> list[tuple[int, int]]:
    return sorted(set(zip(games["season"], games["week"])))


def walk_forward(games: pd.DataFrame, model: Model, score_seasons: Iterable[int],
                 allow_test: bool = False) -> pd.DataFrame:
    """Predictions for every completed game in `score_seasons`. The model is updated through
    every earlier slot (warm-up) and never sees a slot after the last scored one."""
    score_seasons = set(score_seasons)
    if TEST_SEASON in score_seasons and not allow_test:
        raise HeldOutSeasonError(f"{TEST_SEASON} is the untouched test season (evaluated once, MS-032)")
    done = games[games["margin"].notna()]
    last = max(score_seasons)
    out = []
    for season, week in slots(done):
        if season > last:
            break
        slot = done[(done["season"] == season) & (done["week"] == week)]
        if season in score_seasons:
            pre = slot.drop(columns=[c for c in RESULT_COLUMNS if c in slot.columns])
            p = model.predict(pre)
            if not p.index.equals(pre.index):
                raise ValueError(f"{model.name}: predictions not aligned with the slot's games")
            out.append(pd.DataFrame({
                "model": model.name, "game_id": slot["game_id"], "season": season, "week": week,
                "margin": p["margin"], "p_home": p["p_home"],
                "total": p["total"] if "total" in p else float("nan"),
                "actual_margin": slot["margin"], "home_win": slot["home_win"], "actual_total": slot["total"],
            }))
        model.update(slot)
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame()


def run_models(games: pd.DataFrame, factories: dict[str, Callable[[], Model]], score_seasons: Iterable[int],
               allow_test: bool = False) -> pd.DataFrame:
    """Walk-forward predictions for several models (fresh instances), stacked long. Used both
    for the benchmark table and for ablations (variants of one model)."""
    frames = []
    for name, make in factories.items():
        m = make()
        m.name = name
        frames.append(walk_forward(games, m, score_seasons, allow_test))
    return pd.concat(frames, ignore_index=True)
