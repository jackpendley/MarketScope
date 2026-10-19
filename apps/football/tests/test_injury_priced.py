"""R2h on synthetic data with known answers."""

import numpy as np
import pandas as pd

from marketscope_football.ratings import injury_priced as ip


def _frame(slope: float, n: int = 2000, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    qb = np.where(rng.uniform(size=n) < 0.1, rng.normal(scale=3, size=n), 0.0)
    other = rng.normal(scale=0.8, size=n)
    return pd.DataFrame({"season": rng.choice(range(2016, 2025), n), "avail_qb": qb, "avail_other": other,
                         "ats": slope * (qb + other) + rng.normal(scale=12, size=n)})


def test_r2h_finds_planted_underpricing_and_respects_a_null():
    under = ip.r2h(_frame(0.9), resamples=400)
    assert under["gate"] and under["claim"] == "under-priced"
    null = ip.r2h(_frame(0.0, seed=1), resamples=400)
    assert null["claim"] is None and null["primary"][1] < 0 < null["primary"][2]


def test_recording_model_passes_predictions_through():
    class Layer:
        w = {"qb": 0.5, "avail_ol": -0.7, "pass": 1.0}

    class Fake:
        name, layer = "fake", Layer()
        def predict(self, games):
            return pd.DataFrame({"margin": 1.0, "p_home": 0.55}, index=games.index)
        def _features(self, g):
            return {"qb": 2.0, "avail_ol": 1.0, "pass": 3.0}
        def update(self, results):
            self.updated = True

    m = ip.RecordingModel(Fake())
    out = m.predict(pd.DataFrame({"game_id": ["g1"]}))
    assert out["margin"].iloc[0] == 1.0
    assert m.rows == [{"game_id": "g1", "avail_qb": 1.0, "avail_other": -0.7}]
