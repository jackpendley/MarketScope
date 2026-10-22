"""The ratings-v1 feature schema and prediction provenance (ADR-074)."""

import json

import pandas as pd
import pytest

from marketscope_football.ratings import feature_schema as fs
from marketscope_football.ratings import provenance
from marketscope_football.ratings.version import FROZEN_PARAMS_SHA256


def test_committed_schema_matches_the_frozen_parameters():
    committed = json.loads(fs.SCHEMA_PATH.read_text())
    assert committed == fs.feature_schema(), "run `python -m marketscope_football.ratings.feature_schema`"
    assert committed["params_sha256"] == FROZEN_PARAMS_SHA256


def test_every_weighted_feature_is_described_and_typed():
    s = fs.feature_schema()
    names = [f["name"] for f in s["features"]]
    assert len(names) == len(set(names)) == 10
    for f in s["features"]:
        assert f["description"] and f["unit"] in {"points", "share", "starters"} and f["available"]


def test_schema_hash_is_canonical():
    s = fs.feature_schema()
    reordered = json.loads(json.dumps(s, sort_keys=False))
    assert fs.schema_sha256(s) == fs.schema_sha256(reordered) == fs.schema_sha256()
    assert len(fs.schema_sha256()) == 64


def test_input_hash_ignores_row_order_but_not_content():
    a = pd.DataFrame({"game_id": ["g1", "g2"], "margin": [3.0, -7.0]})
    b = pd.DataFrame({"team": ["LA"], "qb": ["00-1"]})
    assert provenance.input_sha256(a, b) == provenance.input_sha256(a.iloc[::-1], b)
    assert provenance.input_sha256(a, b) != provenance.input_sha256(a.assign(margin=[3.0, -6.0]), b)
    p = provenance.prediction_provenance(a, b)
    assert p["params_sha256"] == FROZEN_PARAMS_SHA256 and p["feature_schema_sha256"] == fs.schema_sha256()


def test_code_sha_prefers_the_actions_commit(monkeypatch):
    monkeypatch.setenv("GITHUB_SHA", "a" * 40)
    assert provenance.code_sha() == "a" * 40


def test_reloaded_model_computes_exactly_what_the_schema_describes():
    import numpy as np

    from marketscope_football.ratings.engine import load_params

    _units, _st, layer = load_params("model")  # the saved, frozen model
    s = fs.feature_schema()
    rng = np.random.default_rng(0)
    for neutral in (False, True):
        f = {x["name"]: float(rng.normal()) for x in s["features"]}
        by_schema = sum(x["weight"] * f[x["name"]] for x in s["features"]) + (0 if neutral else s["home_field"]["weight"])
        assert layer.margin(f, neutral) == pytest.approx(by_schema)
