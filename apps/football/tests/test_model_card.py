"""Generated ratings-v1 model card (ADR-074). Uses the SYNTHETIC forward-test fixture."""

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from marketscope_football.ratings import model_card as mc

SYNTH = Path(__file__).parent / "fixtures" / "synthetic_forward_test.csv"


def tiny():
    return pd.DataFrame({
        "game_id": ["a", "b", "c"], "season": 2026, "week": [1, 1, 2],
        "kickoff_utc": ["2026-09-13T17:00Z"] * 3, "home_final": [24, 10, 17], "away_final": [20, 13, 17],
        "expected_margin": [3.0, 2.0, -1.0], "expected_total": [45.0, None, 40.0], "p_home": [0.6, 0.55, 0.45],
        "close_home_spread": [-2.5, -1.0, None], "close_total": [44.5, 41.0, 37.5],
        "close_home_ml": [-130, -110, None], "close_away_ml": [110, -110, None],
    })


def test_forward_metrics_follow_the_site_scorecard_definitions():
    m = mc.forward_metrics(tiny())
    assert m["games"] == 3 and m["weeks"] == 2
    assert m["margin_mae"] == pytest.approx((1 + 5 + 1) / 3)
    assert m["margin_vs_close"]["games"] == 2  # game c has no close
    assert m["margin_vs_close"]["close"] == pytest.approx((abs(2.5 - 4) + abs(1.0 + 3)) / 2)
    assert m["brier_vs_close"]["model"] == pytest.approx(((0.6 - 1) ** 2 + (0.55 - 0) ** 2) / 2)
    assert m["total_vs_close"]["games"] == 2
    assert m["favourite_won"] == {"won": 1, "decided": 2}  # the tie (c) is not decided
    assert m["margin_vs_close"]["ci"] is None and m["calibration"] is None  # too few games


def test_no_vig_matches_the_site():
    assert mc.no_vig_home(-110, -110) == pytest.approx(0.5)
    assert mc.no_vig_home(None, 120) is None


def test_synthetic_demo_builds_a_full_card(tmp_path):
    scored = pd.read_csv(SYNTH)
    card = mc.build_card(scored, "file:synthetic")
    fw = card["forward_2026"]
    assert fw["games"] == 60 and fw["margin_vs_close"]["ci"] is not None and len(fw["calibration"]) >= 3
    assert card["test_2025"]["games"] == 285 and "nflverse close" in card["test_2025"]["models"]
    md = tmp_path / "card.md"
    md.write_text(f"intro\n{mc.BEGIN}\nold\n{mc.END}\ntail\n")
    mc.write_markdown(card, md)
    text = md.read_text()
    assert text.startswith("intro\n") and text.endswith("tail\n") and "old" not in text
    assert "Live 2026 forward test (60 final games" in text and "do not edit by hand" in text
    json.dumps(card, default=str)


def test_bootstrap_is_deterministic():
    d = np.linspace(-1, 1, 40)
    assert mc._ci(d) == mc._ci(d.copy())
