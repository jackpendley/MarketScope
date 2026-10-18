import numpy as np
import pandas as pd

from marketscope_research.ml.audit import leakage_audit
from marketscope_research.ml.dataset import build_dataset
from marketscope_research.ml.design import nfl_week, split_for_week
from marketscope_research.ml.features import FEATURES, build_features
from marketscope_research.ml.gate import evaluate_gate, split_summary
from marketscope_research.ml.labels import label_moves

KICK = pd.Timestamp("2026-10-04T17:00:00Z")  # Week 4, Sunday 1pm ET
BOOKS = ["draftkings", "fanduel", "williamhill_us", "hardrockbet"]


def at(hours_before_kickoff: float) -> pd.Timestamp:
    return KICK - pd.Timedelta(hours=hours_before_kickoff)


def spreads_for(event: str, lines: dict[float, list[float]], source="oddspapi", pinnacle=None) -> pd.DataFrame:
    """lines: hours-before-kickoff -> one line per board book (in BOOKS order)."""
    rows = []
    for h, pts in lines.items():
        for book, p in zip(BOOKS, pts):
            rows.append((event, at(h), book, p, source, at(h) - pd.Timedelta(hours=2)))
        if pinnacle is not None and h in pinnacle:
            rows.append((event, at(h), "pinnacle", pinnacle[h], source, at(h)))
    return pd.DataFrame(rows, columns=["event_id", "observed_at", "bookmaker_key", "point", "source", "bookmaker_updated_at"])


def totals_for(event: str, lines: dict[float, float]) -> pd.DataFrame:
    rows = [(event, at(h), b, p, "oddspapi") for h, p in lines.items() for b in BOOKS[:3]]
    return pd.DataFrame(rows, columns=["event_id", "observed_at", "bookmaker_key", "point", "source"])


KICKOFFS = pd.Series({"g": KICK})
# Snapshots every 6 h from 96 h to 0 h before kickoff; the line moves from -3 to -3.5 at 54 h.
LINES = {h: ([-3.0, -3.0, -3.0, -2.5] if h > 54 else [-3.5, -3.5, -3.5, -3.0]) for h in range(96, -1, -6)}


def test_features_are_point_in_time_values():
    f = build_features(spreads_for("g", LINES, pinnacle={60: -4.0}), totals_for("g", {66: 44.5, 60: 44.5, 42: 43.0}), KICKOFFS)
    assert f["hours_to_kickoff"].between(24, 168).all()
    assert list(f.columns) == ["event_id", "t", *FEATURES]
    r60 = f[f["t"] == at(60)].iloc[0]
    assert r60["consensus"] == -3.0 and r60["books"] == 4 and r60["range"] == 0.5
    assert r60["outlier_dev"] == 0.5  # Hard Rock +0.5 off the median
    assert r60["pinnacle_dev"] == -1.0
    assert r60["dist_key3"] == 0 and r60["on_key"] == 1 and r60["half_point"] == 0
    assert np.isclose(r60["median_quote_age_h"], 2.0)
    r54 = f[f["t"] == at(54)].iloc[0]  # first snapshot after the move
    assert r54["move_6h"] == -0.5 and r54["move_24h"] == -0.5 and r54["changes_48h"] == 1
    assert np.isnan(r54["pinnacle_dev"])
    assert f[f["t"] == at(48)].iloc[0]["move_6h"] == 0
    r42 = f[f["t"] == at(42)].iloc[0]
    assert r42["totals_abs_move_24h"] == 1.5  # 43.0 now vs 44.5 at ~t-24h


def test_snapshot_without_three_books_has_no_row():
    s = spreads_for("g", {48: [-3, -3, -3, -3]})
    s = s[s["bookmaker_key"].isin(BOOKS[:2])]
    assert build_features(s, totals_for("g", {}), KICKOFFS).empty


def test_labels_use_nearest_pregame_snapshot_and_stay_missing_without_one():
    s = spreads_for("g", LINES)
    times = pd.DataFrame({"event_id": ["g", "g", "g"], "t": [at(78), at(72), at(24)]})
    lab = label_moves(s, KICKOFFS, times).set_index("t")
    assert lab.loc[at(78), "moved"] == 1 and lab.loc[at(78), "direction"] == "home"  # -3 -> -3.5 by t+24
    assert lab.loc[at(72), "moved"] == 1
    # t = 24 h before kickoff: the horizon window is kickoff +/- 3 h. The snapshot at kickoff is
    # not pregame and the previous one (6 h before) is outside the window, so the label is missing.
    assert np.isnan(lab.loc[at(24), "moved"])


def test_small_move_is_negative_class():
    s = spreads_for("g", {72: [-3, -3, -3, -3], 48: [-3, -3, -3.5, -3.5]})  # median -3.25: a 0.25 move
    lab = label_moves(s, KICKOFFS, pd.DataFrame({"event_id": ["g"], "t": [at(72)]}))
    assert lab.iloc[0]["moved"] == 0 and lab.iloc[0]["direction"] is None


def test_week_and_split():
    weeks = nfl_week(pd.Series(pd.to_datetime(["2026-09-11T00:20:00Z", "2026-09-15T00:15:00Z", "2026-10-04T17:00:00Z"], utc=True)))
    # Thursday night Week 1 (Sep 10 ET), Monday night Week 1 (Sep 14 ET), Week 4 Sunday.
    assert weeks.tolist() == [1, 1, 4]
    assert [split_for_week(w) for w in (1, 4, 5, 6, 9)] == ["train", "validation", "test", "forward", "forward"]


def test_leakage_audit_passes_for_real_features_and_catches_a_planted_leak():
    s = spreads_for("g", LINES, pinnacle={h: -3.5 for h in LINES})
    t = totals_for("g", {h: 44.5 for h in LINES})
    assert leakage_audit(build_features, s, t, KICKOFFS, samples=10) == {}

    def leaky(spreads, totals, kickoffs):
        f = build_features(spreads, totals, kickoffs)
        lab = label_moves(spreads, kickoffs, f[["event_id", "t"]])
        f["future_consensus"] = lab["future_consensus"].to_numpy()  # peeks at t + 24 h
        return f

    violations = leakage_audit(leaky, s, t, KICKOFFS, samples=10)
    assert "future_consensus" in violations and set(violations) == {"future_consensus"}


def test_dataset_and_gate_counts():
    s = pd.concat([spreads_for("g", LINES), spreads_for("h", LINES)])
    kick = pd.Series({"g": KICK, "h": KICK})
    df = build_dataset(s, totals_for("g", {}), kick)
    assert set(df["split"]) == {"validation"} and df["week"].eq(4).all()
    summary = split_summary(df).set_index("split")
    assert summary.loc["validation", "games"] == 2
    gate = evaluate_gate(df)
    assert not gate.passed and gate.games == 2
