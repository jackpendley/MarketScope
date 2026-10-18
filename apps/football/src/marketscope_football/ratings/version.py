"""The frozen model version (MS-032b, ADR-039). ratings-v1 = the parameters in params.json as of the
freeze; their canonical sha256 is pinned here and checked by a test, so any change to the model's
parameters must come with a new version (and new rows), never a silent edit."""

from __future__ import annotations

import hashlib
import json

from .engine import PARAMS_PATH

MODEL_VERSION = "ratings-v1"
FROZEN_PARAMS_SHA256 = "c2f6ed74f6c7e32a57899b0080815ec48b7cace82dfe9ad9a2240624340cbe2e"


def params_sha256() -> str:
    canonical = json.dumps(json.loads(PARAMS_PATH.read_text()), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()
