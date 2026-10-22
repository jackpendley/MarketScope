"""Provenance for ratings-v1 estimates (Phase 14, ADR-074): which parameters, feature schema, code and
inputs produced a prediction. Stored on every new model_predictions row."""

from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path

import pandas as pd

from .feature_schema import schema_sha256
from .version import params_sha256


def frame_sha256(df: pd.DataFrame) -> str:
    """Content hash of a table, independent of row order."""
    rows = pd.util.hash_pandas_object(df, index=False).sort_values().to_numpy()
    return hashlib.sha256(",".join(map(str, df.columns)).encode() + rows.tobytes()).hexdigest()


def input_sha256(*frames: pd.DataFrame) -> str:
    """One hash over the model's inputs (e.g. results, play-by-play channels, expected starters)."""
    return hashlib.sha256("|".join(frame_sha256(f) for f in frames).encode()).hexdigest()


def code_sha() -> str | None:
    """The commit that ran: GITHUB_SHA in Actions, else the local HEAD (None outside a checkout)."""
    if os.environ.get("GITHUB_SHA"):
        return os.environ["GITHUB_SHA"]
    try:
        return subprocess.check_output(["git", "-C", str(Path(__file__).parent), "rev-parse", "HEAD"],
                                       text=True, stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def prediction_provenance(*inputs: pd.DataFrame) -> dict:
    return {"params_sha256": params_sha256(), "feature_schema_sha256": schema_sha256(), "code_sha": code_sha(),
            "input_sha256": input_sha256(*inputs)}
