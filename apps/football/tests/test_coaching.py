"""Coaching staff parsing, assembly and validation (ADR-031)."""

import csv
from datetime import date
from pathlib import Path

from marketscope_football.coaching import (Coach, coaches_in, role_of, slug, staff_block, staff_roles,
                                           validate_staff)
from marketscope_football.coaching_build import Directory, TeamSeason, week_role_assignments

FINAL_STAFF = """{{NFL final staff
|Year=2023
|Head Coaches=
*Head coach – [[Mike Tomlin]]
*Assistant head coach – [[John Mitchell (American football)|John Mitchell]]
|Offensive Coaches=
*Offensive coordinator – [[Matt Canada]]
*Interim offensive coordinator/running backs – [[Eddie Faulkner]] (interim)
*Quarterbacks – [[Mike Sullivan (American football coach)|Mike Sullivan]]
|Defensive Coaches=
*Defensive coordinator – [[Teryl Austin]]<ref>x</ref>
*Co-defensive coordinator – Plain Name and Other Person
|Special Teams Coaches=
*Special teams coordinator – [[Danny Smith (coach)|Danny Smith]]
}}"""

TEMPLATE = """'''Head coaches'''
* [[List of head coaches|Head coach]] – [[Dan Quinn (American football)|Dan Quinn]]
'''Offensive coaches'''
* [[Offensive coordinator]] – [[David Blough]]"""


def test_roles_are_read_from_final_staff_and_current_templates():
    roles = staff_roles(staff_block("intro\n" + FINAL_STAFF + "\nmore"))
    assert [c.name for c in roles["HC"]] == ["Mike Tomlin"]
    assert [c.coach_id for c in roles["OC"]] == ["Matt_Canada", "Eddie_Faulkner"]
    assert [c.name for c in roles["DC"]] == ["Teryl Austin", "Plain Name", "Other Person"]
    assert roles["DC"][1].coach_id == "name:plain-name"
    assert roles["STC"][0].coach_id == "Danny_Smith_(coach)"
    t = staff_roles(staff_block(TEMPLATE))
    assert t["HC"][0].coach_id == "Dan_Quinn_(American_football)" and t["OC"][0].name == "David Blough"
    assert staff_block("no staff here\n*Owner – Someone") is None


def test_role_labels_and_names():
    assert role_of("Assistant head coach/defensive coordinator") == "DC"
    assert role_of("Assistant head coach") is None
    assert role_of("Assistant special teams coordinator") is None
    assert role_of("Head coach/executive vice president of football operations") == "HC"
    assert coaches_in("[[Ron Rivera]] (interim)") == [Coach("Ron_Rivera", "Ron Rivera")]
    assert slug("Pete Carmichael Jr.") == slug("Pete Carmichael") == "pete-carmichael"
    assert slug("Derius Swinton II") == "derius-swinton"


def season(weeks=(1, 2, 3, 5, 6)) -> TeamSeason:
    kick = {w: date(2023, 9, 1 + 7 * i) for i, w in enumerate(weeks)}
    return TeamSeason(2023, "PIT", list(weeks), kick, {w: "Mike Tomlin" for w in weeks})


def test_coordinator_changes_split_the_season_and_co_and_ignore_are_explicit():
    ts = season()
    roles = {"OC": [Coach("A", "Old Coach"), Coach("B", "New Coach")], "DC": [Coach("C", "D One"), Coach("D", "D Two")],
             "STC": [Coach("E", "Gone Early"), Coach("F", "Stayed")]}
    changes = [
        {"role": "OC", "kind": "change", "coach_out": "Old Coach", "coach_in": "New Coach", "effective_date": "2023-09-10"},
        {"role": "DC", "kind": "co", "coach_out": "D One", "coach_in": "D Two", "effective_date": ""},
        {"role": "STC", "kind": "ignore", "coach_out": "Gone Early", "coach_in": "", "effective_date": ""},
    ]
    assign, problems = week_role_assignments(ts, roles, changes, Directory())
    assert problems == []
    assert [assign["OC"][w][0].name for w in ts.weeks] == ["Old Coach", "Old Coach", "New Coach", "New Coach", "New Coach"]
    assert all(len(assign["DC"][w]) == 2 for w in ts.weeks)
    assert all([c.name for c in assign["STC"][w]] == ["Stayed"] for w in ts.weeks)


def test_two_coordinators_without_curation_are_flagged():
    _, problems = week_role_assignments(season(), {"OC": [Coach("A", "X"), Coach("B", "Y")]}, [], Directory())
    assert problems and "need curation" in problems[0]


def row(**kw) -> dict:
    r = {"season": "2023", "team": "PIT", "role": "HC", "coach_id": "Mike_Tomlin", "coach_name": "Mike Tomlin",
         "from_week": "1", "to_week": "18", "offense_playcaller": "False", "defense_playcaller": "False",
         "source_url": "nflverse", "playcaller_basis": "", "playcaller_source_url": ""}
    r.update(kw)
    return r


def test_validation_requires_exactly_one_caller_per_week_and_sources():
    ok = [row(), row(role="OC", coach_id="O", coach_name="O", offense_playcaller="True", playcaller_basis="rule"),
          row(role="DC", coach_id="D", coach_name="D", defense_playcaller="True", playcaller_basis="rule")]
    assert validate_staff(ok) == []
    gap = ok[:2] + [row(role="DC", coach_id="D", coach_name="D", defense_playcaller="True", to_week="10",
                        playcaller_basis="rule")]
    assert "defensive play-caller" in validate_staff(gap)[0]
    unsourced = ok[:2] + [row(role="PC", coach_id="X", coach_name="X", defense_playcaller="True",
                              playcaller_basis="direct", source_url="")]
    assert any("without a source" in p for p in validate_staff(ok[:2] + unsourced[2:]))
    overlap = ok + [row(from_week="5", to_week="9")]
    assert any("overlapping HC" in p for p in validate_staff(overlap)) or any("head coach" in p for p in validate_staff(overlap))


def test_committed_coaching_staff_csv_is_valid():
    path = Path(__file__).resolve().parents[1] / "data" / "coaching_staff.csv"
    with path.open() as f:
        rows = list(csv.DictReader(f))
    assert len(rows) > 1000
    assert validate_staff(rows) == []
    assert {r["role"] for r in rows} <= {"HC", "OC", "DC", "STC", "PC"}
