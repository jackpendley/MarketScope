"""The ratings-v1 game model's feature schema (Phase 14, ADR-074).

The game layer is linear: expected home margin = sum of weight x feature + home-field constant (when not
neutral). The weights are frozen in params.json (ADR-039). This module writes down what each feature is
and when it becomes available, generated from the frozen parameters so the two cannot drift.
`feature_schema.json` beside params.json is the committed copy; a test checks it matches, and every
prediction records the schema's hash.

    PYTHONPATH=src .venv/bin/python -m marketscope_football.ratings.feature_schema   # rewrite the JSON
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .engine import PARAMS_PATH
from .version import MODEL_VERSION, params_sha256

SCHEMA_PATH = Path(__file__).with_name("feature_schema.json")

AFTER_GAMES = "filtered state after every completed game before the prediction (point in time)"
AT_PREDICTION = "latest depth charts, injury reports and snaps published before the prediction"

DESCRIPTIONS = {
    "pass": ("Expected net pass EPA per game: home minus away (offense vs opposing defense) EPA per dropback "
             "times league dropbacks per team-game", "points", AFTER_GAMES),
    "rush": ("Expected net rush EPA per game, built the same way from rushing plays", "points", AFTER_GAMES),
    "succ": ("Expected success-rate difference (home offense vs away defense minus the reverse)", "share",
             AFTER_GAMES),
    "ppd": ("Expected net points from drives: points-per-drive difference times league drives per team-game",
            "points", AFTER_GAMES),
    "st": ("Expected net special-teams EPA per game", "points", AFTER_GAMES),
    "qb": ("Expected starting quarterback's rating relative to the team's baseline quarterback, net of the "
           "opponent's", "points", AT_PREDICTION),
    "avail_ol": ("Expected missing offensive-line starters, net (home minus away)", "starters", AT_PREDICTION),
    "avail_skill": ("Expected missing skill-position starters, net", "starters", AT_PREDICTION),
    "avail_front7": ("Expected missing front-seven starters, net", "starters", AT_PREDICTION),
    "avail_db": ("Expected missing defensive-back starters, net", "starters", AT_PREDICTION),
}


def feature_schema() -> dict:
    """The schema, generated from the frozen parameters. Raises if a weighted feature has no description."""
    layer = json.loads(PARAMS_PATH.read_text())["model"]["game"]
    missing = set(layer["w"]) - set(DESCRIPTIONS)
    if missing:
        raise ValueError(f"features without a description: {sorted(missing)}")
    return {
        "model_version": MODEL_VERSION,
        "params_sha256": params_sha256(),
        "target": "home margin of victory (points), full game including overtime",
        "outputs": {
            "expected_margin": "sum of weight x feature, plus home_field when the site is not neutral",
            "p_home": "P(home wins) from the fitted margin distribution (key numbers), a tie counted as half",
            "expected_total": "total_a + total_b x expected drives x expected points per drive (both offenses)",
        },
        "home_field": {"weight": layer["c"], "unit": "points", "applies": "not a neutral site"},
        "features": [{"name": k, "weight": w, "description": DESCRIPTIONS[k][0], "unit": DESCRIPTIONS[k][1],
                      "available": DESCRIPTIONS[k][2]} for k, w in layer["w"].items()],
        "rules": ["A game's result never feeds its own features (ADR-028).",
                  "The displayed rating uses no market inputs."],
    }


def canonical(schema: dict) -> str:
    return json.dumps(schema, sort_keys=True, separators=(",", ":"))


def schema_sha256(schema: dict | None = None) -> str:
    return hashlib.sha256(canonical(schema or feature_schema()).encode()).hexdigest()


def write(path: Path = SCHEMA_PATH) -> Path:
    path.write_text(json.dumps(feature_schema(), indent=2) + "\n")
    return path


if __name__ == "__main__":
    print(write(), schema_sha256())
