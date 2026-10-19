"""ratings-v2 flags and the pre-registered adoption rule (MS-039)."""

import pandas as pd
import pytest

from marketscope_football.ratings import v2


def _starters():
    k = lambda s, w: pd.Timestamp(f"{s}-09-0{w} 17:00", tz="UTC")  # noqa: E731
    rows = []
    # 2020: KC main QB "a" (3 starts) despite "b" starting once; DEN "c" and "d" tie 2-2, "d" later.
    for w, qb in zip([1, 2, 3, 4], ["a", "a", "b", "a"]):
        rows.append({"game_id": f"k20{w}", "season": 2020, "week": w, "kickoff_utc": k(2020, w), "team": "KC", "actual_qb": qb, "exp_qb": qb})
    for w, qb in zip([1, 2, 3, 4], ["c", "c", "d", "d"]):
        rows.append({"game_id": f"d20{w}", "season": 2020, "week": w, "kickoff_utc": k(2020, w), "team": "DEN", "actual_qb": qb, "exp_qb": qb})
    # 2021 week 1: KC expects "a" again (same), DEN expects "c" (changed from "d").
    rows.append({"game_id": "k211", "season": 2021, "week": 1, "kickoff_utc": k(2021, 1), "team": "KC", "actual_qb": "a", "exp_qb": "a"})
    rows.append({"game_id": "d211", "season": 2021, "week": 1, "kickoff_utc": k(2021, 1), "team": "DEN", "actual_qb": "c", "exp_qb": "c"})
    return pd.DataFrame(rows)


def test_qb_change_compares_week1_expected_starter_with_last_seasons_main_qb():
    st = _starters()
    games = pd.DataFrame({"game_id": st["game_id"], "game_type": "REG"})
    flags = v2.qb_offense_changes(games, st)
    assert flags == {(2021, "KC"): False, (2021, "DEN"): True}


def test_playoff_starts_do_not_count_toward_the_main_qb():
    st = _starters()
    games = pd.DataFrame({"game_id": st["game_id"], "game_type": ["REG"] * len(st)})
    games.loc[games["game_id"].isin(["d203", "d204"]), "game_type"] = "POST"  # "d" only started playoff games
    assert v2.qb_offense_changes(games, st)[(2021, "DEN")] is False


def test_variant_flags_keep_defence_and_combine_offence():
    callers = {(2021, "KC"): (True, True), (2021, "DEN"): (False, False)}
    qbs = {(2021, "KC"): False, (2021, "DEN"): True}
    assert v2.v2_flags("qb", callers, qbs) == {(2021, "KC"): (False, True), (2021, "DEN"): (True, False)}
    assert v2.v2_flags("qb_or_caller", callers, qbs) == {(2021, "KC"): (True, True), (2021, "DEN"): (True, False)}
    with pytest.raises(ValueError):
        v2.v2_flags("caller", callers, qbs)


def test_adoption_needs_every_check():
    good = pd.Series({"d_margin_mae": -0.01, "d_log_loss": -0.0001})
    assert v2.adoption(-100.0, -99.0, good)[0]
    assert not v2.adoption(-100.0, -101.0, good)[0]  # worse likelihood
    assert not v2.adoption(-100.0, -99.0, pd.Series({"d_margin_mae": -0.01, "d_log_loss": 0.0002}))[0]
    assert not v2.adoption(-100.0, -99.0, pd.Series({"d_margin_mae": 0.01, "d_log_loss": -0.0002}))[0]
