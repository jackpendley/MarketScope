"""Unit tests for snap counts, injury snapshots and P(plays | status)."""

from datetime import datetime, timedelta, timezone

import polars as pl
import pytest

from marketscope_football.availability import (InjuryPlan, injury_rows, plan_injury_changes, position_group,
                                                practice_level, rate_table, snap_rows, status_outcomes, wilson)

NOW = datetime(2026, 10, 18, 13, 0, tzinfo=timezone.utc)
KICKOFF = NOW + timedelta(hours=4)


def injury(**kw) -> dict:
    row = {"season": 2026, "week": 6, "game_type": "REG", "team": "KC", "gsis_id": "00-1", "full_name": "A Player",
           "position": "WR", "report_status": "Questionable", "report_primary_injury": "Knee",
           "report_secondary_injury": None, "practice_status": "Limited Participation in Practice",
           "practice_primary_injury": "Knee", "practice_secondary_injury": None, "season_type": "REG",
           "first_name": "A", "last_name": "Player"}
    row.update(kw)
    return row


def rows(*dicts) -> list[dict]:
    return injury_rows(pl.DataFrame(list(dicts)))


def test_content_hash_ignores_the_name_and_tracks_reported_fields():
    a, b, c = rows(injury()), rows(injury(full_name="Renamed")), rows(injury(report_status="Out"))
    assert a[0]["content_hash"] == b[0]["content_hash"] != c[0]["content_hash"]


def test_first_sighting_before_kickoff_is_live_and_after_kickoff_is_backfill():
    fetched = rows(injury(), injury(gsis_id="00-2", team="BUF"))
    kickoffs = {(2026, 6, "KC"): KICKOFF, (2026, 6, "BUF"): NOW - timedelta(days=3)}
    plan = plan_injury_changes(fetched, {}, kickoffs, NOW)
    by_team = {r["team"]: r for r in plan.inserts}
    assert by_team["KC"]["first_seen_at"] == NOW and by_team["KC"]["last_seen_at"] == NOW
    assert by_team["BUF"]["first_seen_at"] is None and by_team["BUF"]["last_seen_at"] is None


def test_unknown_game_is_treated_as_backfill():
    plan = plan_injury_changes(rows(injury()), {}, {}, NOW)
    assert plan.inserts[0]["first_seen_at"] is None


def test_live_history_appends_changes_touches_repeats_and_freezes_at_kickoff():
    fetched = rows(injury())
    h = fetched[0]["content_hash"]
    key = (2026, 6, "KC", "00-1")
    kick = {(2026, 6, "KC"): KICKOFF}
    same = plan_injury_changes(fetched, {key: {"id": 7, "content_hash": h, "first_seen_at": NOW}}, kick, NOW)
    assert same == InjuryPlan(touch=[7])
    changed = plan_injury_changes(fetched, {key: {"id": 7, "content_hash": "old", "first_seen_at": NOW}}, kick, NOW)
    assert len(changed.inserts) == 1 and changed.inserts[0]["first_seen_at"] == NOW
    after = plan_injury_changes(fetched, {key: {"id": 7, "content_hash": "old", "first_seen_at": NOW}}, kick,
                                KICKOFF + timedelta(minutes=1))
    assert after == InjuryPlan()


def test_backfill_rows_are_corrected_in_place():
    fetched = rows(injury())
    key = (2026, 6, "KC", "00-1")
    prev = {key: {"id": 3, "content_hash": "old", "first_seen_at": None}}
    plan = plan_injury_changes(fetched, prev, {(2026, 6, "KC"): NOW - timedelta(days=1)}, NOW)
    assert plan.inserts == [] and plan.backfill_updates[0]["id"] == 3
    assert plan.backfill_updates[0]["first_seen_at"] is None


def test_position_groups_and_practice_levels():
    df = pl.DataFrame({"position": ["QB", "OT", "NT", "SS", "LS", "XX"],
                       "practice_status": ["Full Participation in Practice", "Limited Participation in Practice",
                                           "Did Not Participate In Practice", None, "Out (Definitely Will Not Play)",
                                           "Full"]})
    out = df.select(group=position_group(), practice=practice_level())
    assert out["group"].to_list() == ["QB", "OL", "DL", "DB", "ST", "other"]
    assert out["practice"].to_list() == ["Full", "Limited", "DNP", None, None, "Full"]


def test_snap_rows_attach_gsis_ids_and_status_outcomes_join_on_them():
    snaps = pl.DataFrame({
        "game_id": ["2025_01_KC_LAC"] * 2, "pfr_game_id": ["x"] * 2, "season": [2025] * 2, "game_type": ["REG"] * 2,
        "week": [1] * 2, "player": ["A", "B"], "pfr_player_id": ["PA", "PB"], "position": ["WR", "CB"],
        "team": ["KC", "KC"], "opponent": ["LAC"] * 2, "offense_snaps": [40.0, 0.0], "offense_pct": [0.6, 0.0],
        "defense_snaps": [0.0, 0.0], "defense_pct": [0.0, 0.0], "st_snaps": [2.0, 0.0], "st_pct": [0.1, 0.0],
    })
    players = pl.DataFrame({"gsis_id": ["00-1", "00-2"], "pfr_id": ["PA", "PB"]})
    s = snap_rows(snaps, players)
    assert s["gsis_id"].to_list() == ["00-1", "00-2"] and s["offense_snaps"].dtype == pl.Int32
    inj = pl.DataFrame([injury(season=2025, week=1, gsis_id=g, report_status=st)
                        for g, st in (("00-1", "Questionable"), ("00-2", "Questionable"), ("00-3", "Out"))])
    out = status_outcomes(inj, s).sort("gsis_id")
    # 00-2 appears in snap counts with zero snaps: did not play. 00-3 is absent: did not play.
    assert out["played"].to_list() == [1, 0, 0]
    t = rate_table(out, ["report_status"])
    assert t.filter(pl.col("report_status") == "Questionable")["p"].item() == pytest.approx(0.5)


def test_wilson_interval():
    lo, hi = wilson(50, 100)
    assert lo == pytest.approx(0.4038, abs=1e-3) and hi == pytest.approx(0.5962, abs=1e-3)
    assert wilson(0, 10)[0] == pytest.approx(0.0, abs=1e-12)
