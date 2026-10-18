"""The frozen ratings-v1 parameters must not change silently (ADR-039)."""

from marketscope_football.ratings.version import FROZEN_PARAMS_SHA256, MODEL_VERSION, params_sha256


def test_params_match_the_frozen_version():
    assert params_sha256() == FROZEN_PARAMS_SHA256, (
        f"ratings/params.json changed: {MODEL_VERSION} is frozen. Create a new model version instead.")
