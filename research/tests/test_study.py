import numpy as np
import pandas as pd
import pytest

from marketscope_research.consensus import board_quotes, consensus_series
from marketscope_research.outlier_convergence import (
    game_clustered_ci,
    label_outcomes,
    summarize,
    unconditional_move_rate,
)

T0 = pd.Timestamp("2026-10-14T00:00:00Z")


def at(hours: float) -> pd.Timestamp:
    return T0 + pd.Timedelta(hours=hours)


def spreads(rows):
    return pd.DataFrame(rows, columns=["event_id", "observed_at", "bookmaker_key", "point"])


def snapshot(event, hours, points: dict):
    return [(event, at(hours), book, p) for book, p in points.items()]


def test_board_quotes_prefers_hard_rock_az_and_counts_each_book_once():
    df = spreads(snapshot("g", 0, {"draftkings": -3, "hardrockbet_az": -3.5, "hardrockbet": -4, "bovada": -9}))
    q = board_quotes(df)
    assert sorted(q["bookmaker_key"]) == ["draftkings", "hardrockbet_az"]


def test_consensus_needs_three_books_and_takes_the_median():
    df = spreads(
        snapshot("g", 0, {"draftkings": -3, "fanduel": -3, "betmgm": -4})
        + snapshot("g", 6, {"draftkings": -3, "fanduel": -3.5})
    )
    c = consensus_series(df)
    assert c[["observed_at", "consensus", "books"]].values.tolist() == [[at(0), -3.0, 3]]


def consensus_frame(event, values: dict):
    return pd.DataFrame(
        [{"event_id": event, "observed_at": at(h), "consensus": v, "books": 3} for h, v in values.items()]
    )


KICKOFFS = pd.Series({"g": at(100), "late": at(20)})


def event(value, consensus=-3.0, hours=0, eid="g"):
    return pd.DataFrame([{"event_id": eid, "bookmaker_key": "draftkings", "detected_at": at(hours), "value": value, "consensus": consensus}])


@pytest.mark.parametrize(
    "horizon_value,book_deviation,expected",
    [(-3.5, -0.5, "toward"), (-2.5, -0.5, "away"), (-3.0, -0.5, "none"), (-2.5, 0.5, "toward")],
)
def test_outcome_direction(horizon_value, book_deviation, expected):
    c = consensus_frame("g", {0: -3.0, 24: horizon_value})
    out = label_outcomes(event(book_deviation), c, KICKOFFS)
    assert out["outcome"].tolist() == [expected]


def test_horizon_must_fall_within_tolerance_and_before_kickoff():
    c = consensus_frame("g", {0: -3.0, 12: -4.0, 36: -4.0})
    assert label_outcomes(event(-0.5), c, KICKOFFS)["outcome"].tolist() == ["no_horizon"]
    late = consensus_frame("late", {0: -3.0, 24: -4.0})  # kickoff at 20h: 24h snapshot is in-play
    assert label_outcomes(event(-0.5, eid="late"), late, KICKOFFS)["outcome"].tolist() == ["no_horizon"]


def test_nearest_snapshot_to_the_horizon_is_used():
    c = consensus_frame("g", {0: -3.0, 20: -3.0, 25: -3.5})
    out = label_outcomes(event(-0.5), c, KICKOFFS)
    assert out.iloc[0]["horizon_at"] == at(25) and out.iloc[0]["outcome"] == "toward"


def test_unconditional_move_rate_counts_only_snapshots_with_a_horizon():
    c = consensus_frame("g", {0: -3.0, 6: -3.0, 24: -3.5, 30: -3.5})
    rate, eligible = unconditional_move_rate(c, KICKOFFS)
    # 0h→24h moved; 6h→30h moved; 24h and 30h have no horizon.
    assert (rate, eligible) == (1.0, 2)


def test_summary_is_inconclusive_below_the_minimum_and_ci_is_deterministic():
    c = consensus_frame("g", {0: -3.0, 24: -3.5})
    labelled = label_outcomes(event(-0.5), c, KICKOFFS)
    r = summarize(labelled, any_move_rate=0.5, baseline_eligible=10)
    assert (r.toward, r.events_scored, r.conclusive, r.chance_toward_rate) == (1, 1, False, 0.25)
    assert np.isnan(r.ci[0])  # one game: no CI


def test_game_clustered_ci_bounds():
    rows = []
    for g in range(20):
        for k in range(3):
            rows.append({"event_id": f"g{g}", "outcome": "toward" if (g + k) % 2 == 0 else "away"})
    labelled = pd.DataFrame(rows)
    lo, hi = game_clustered_ci(labelled)
    assert 0.0 <= lo <= 0.5 <= hi <= 1.0
    assert game_clustered_ci(labelled) == (lo, hi)
