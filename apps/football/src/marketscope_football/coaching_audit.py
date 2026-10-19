"""Audit the coordinator spans in data/coaching_staff.csv against Wikipedia's team staff templates as
they stood before each game (the templates' revision history), so a mid-season change missing from
coordinator_changes.csv shows up instead of the end-of-season coordinator silently covering the
whole season. Flags are leads for curation, not truth: templates lag events and are sometimes wrong.

    PYTHONPATH=src .venv/bin/python -m marketscope_football.coaching_audit [--refresh] [--report reports/coaching-audit.md]
"""

from __future__ import annotations

import argparse
import csv
import json
import time
import urllib.parse
import urllib.request
from bisect import bisect_left
from collections import defaultdict
from datetime import date, datetime, timezone

from .coaching import slug, staff_block, staff_roles
from .coaching_build import API, CACHE, DATA, UA, WIKI_TEAM

ROLES = ("OC", "DC")
CANONICAL = {"OAK": "LV", "SD": "LAC", "STL": "LA"}  # template history follows page moves
CURRENT_NAME = {**WIKI_TEAM, "WAS": "Washington Commanders"}


def template_title(team: str) -> str:
    return f"Template:{CURRENT_NAME[CANONICAL.get(team, team)]} staff"


def _get(params: dict) -> dict:
    q = urllib.parse.urlencode({**params, "format": "json", "formatversion": "2"})
    req = urllib.request.Request(f"{API}?{q}", headers={"User-Agent": UA})
    d = json.load(urllib.request.urlopen(req, timeout=30))
    time.sleep(1)
    return d


def revision_list(title: str, start: str, end: str) -> list[tuple[str, int]]:
    """(timestamp, revid) of every revision of `title` between end and start, oldest first, plus the
    last revision before `end` (the one in effect when the window opens)."""
    out, cont = [], {}
    while True:
        d = _get({"action": "query", "prop": "revisions", "titles": title, "rvprop": "ids|timestamp",
                  "rvlimit": "max", "rvstart": start, "rvend": end, **cont})
        page = d["query"]["pages"][0]
        out += [(r["timestamp"], r["revid"]) for r in page.get("revisions", [])]
        if "continue" not in d:
            break
        cont = d["continue"]
    before = _get({"action": "query", "prop": "revisions", "titles": title, "rvprop": "ids|timestamp",
                   "rvlimit": "1", "rvstart": end})["query"]["pages"][0].get("revisions", [])
    out += [(r["timestamp"], r["revid"]) for r in before]
    return sorted(set(out))


def staff_by_revision(revids: list[int], cached: dict[str, dict]) -> None:
    """Fill cached[str(revid)] = {role: [names]} for the OC and DC lines of each revision."""
    todo = [r for r in revids if str(r) not in cached]
    for i in range(0, len(todo), 50):
        d = _get({"action": "query", "prop": "revisions", "revids": "|".join(map(str, todo[i:i + 50])),
                  "rvprop": "ids|content", "rvslots": "main"})
        for p in d["query"]["pages"]:
            for r in p.get("revisions", []):
                block = staff_block(r["slots"]["main"]["content"])
                roles = staff_roles(block) if block else {}
                cached[str(r["revid"])] = {k: [c.name for c in roles.get(k, [])] for k in ROLES}


def last_name(name: str) -> str:
    return slug(name).rsplit("-", 1)[-1]


def audit(seasons: list[int], refresh: bool) -> list[dict]:
    import nflreadpy as nfl

    sched = nfl.load_schedules(seasons).to_pandas()
    games: dict[tuple[int, str], dict[int, date]] = defaultdict(dict)
    for g in sched.itertuples(index=False):
        if isinstance(g.result, float) and g.result != g.result and date.fromisoformat(g.gameday) > date.today():
            continue  # unplayed
        for t in (g.home_team, g.away_team):
            games[(g.season, t)][int(g.week)] = date.fromisoformat(g.gameday)

    rev_path, staff_path = CACHE / "template_revisions.json", CACHE / "template_staff.json"
    revs = json.loads(rev_path.read_text()) if rev_path.exists() and not refresh else {}
    staff = json.loads(staff_path.read_text()) if staff_path.exists() else {}
    start = f"{max(seasons) + 1}-03-01T00:00:00Z"
    end = f"{min(seasons)}-06-01T00:00:00Z"
    for title in sorted({template_title(t) for _, t in games}):
        if title not in revs:
            revs[title] = revision_list(title, start, end)
            CACHE.mkdir(parents=True, exist_ok=True)
            rev_path.write_text(json.dumps(revs))

    # The revision in effect before each game (game day, 00:00 UTC).
    effective: dict[tuple[int, str, int], int] = {}
    for (season, team), weeks in games.items():
        r = revs[template_title(team)]
        stamps = [ts for ts, _ in r]
        for w, d in weeks.items():
            i = bisect_left(stamps, f"{d.isoformat()}T00:00:00Z") - 1
            if i >= 0:
                effective[(season, team, w)] = r[i][1]
    staff_by_revision(sorted(set(effective.values())), staff)
    staff_path.write_text(json.dumps(staff))

    with (DATA / "coaching_staff.csv").open() as f:
        rows = [r for r in csv.DictReader(f) if r["role"] in ROLES]
    ours: dict[tuple[int, str, int, str], set[str]] = defaultdict(set)
    for r in rows:
        for w in range(int(r["from_week"]), int(r["to_week"]) + 1):
            ours[(int(r["season"]), r["team"], w, r["role"])].add(r["coach_name"])

    flags = []
    for (season, team, w), revid in sorted(effective.items()):
        tpl = staff.get(str(revid), {})
        for role in ROLES:
            mine, theirs = ours.get((season, team, w, role), set()), set(tpl.get(role, []))
            if not theirs:
                continue  # template had no such line: nothing to compare
            if {last_name(n) for n in mine} != {last_name(n) for n in theirs}:
                flags.append({"season": season, "team": team, "week": w, "role": role, "csv": sorted(mine),
                              "template": sorted(theirs), "revid": revid})
    accepted = {(int(a["season"]), a["team"], a["role"], int(a["from_week"])): a["reason"]
                for a in csv.DictReader((DATA / "coaching_audit_accepted.csv").open())}
    found = spans(flags)
    for f in found:
        f["accepted"] = accepted.get((f["season"], f["team"], f["role"], f["from_week"]), "")
    return found


def spans(flags: list[dict]) -> list[dict]:
    """Merge consecutive flagged weeks with the same disagreement."""
    out: list[dict] = []
    for f in flags:
        p = out[-1] if out else None
        if p and (p["season"], p["team"], p["role"], p["csv"], p["template"]) == \
                (f["season"], f["team"], f["role"], f["csv"], f["template"]):
            p["to_week"] = f["week"]
            continue
        out.append({**{k: f[k] for k in ("season", "team", "role", "csv", "template", "revid")},
                    "from_week": f["week"], "to_week": f["week"]})
    return out


def report(found: list[dict]) -> list[str]:
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    L = ["# Coordinator audit against Wikipedia staff-template history", "",
         f"Generated by `python -m marketscope_football.coaching_audit` on {stamp}. For every game, the team's "
         "staff template as it stood before game day is compared with `data/coaching_staff.csv`. Each row is a "
         "span of weeks where the coordinator differs. Rows are leads to check against a dated source, not "
         "corrections: templates are often updated late, and early-season rows usually mean the template "
         "still showed last season's staff.", "",
         f"{len(found)} spans flagged, {sum(1 for f in found if not f['accepted'])} unexplained. Explained spans are "
         "listed with their reason in `data/coaching_audit_accepted.csv`; an unexplained span needs a dated "
         "source and a row in `coordinator_changes.csv` (or an accepted reason).", "",
         "| Season | Team | Role | Weeks | CSV | Template | Revision | Explained |", "|---|---|---|---|---|---|---|---|"]
    for f in found:
        L.append(f"| {f['season']} | {f['team']} | {f['role']} | {f['from_week']}–{f['to_week']} | "
                 f"{', '.join(f['csv']) or '–'} | {', '.join(f['template'])} | "
                 f"[{f['revid']}](https://en.wikipedia.org/w/index.php?oldid={f['revid']}) | {f['accepted'] or '**no**'} |")
    return L + [""]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seasons", default="2016-2026")
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--report")
    args = ap.parse_args()
    a, b = (int(x) for x in args.seasons.split("-"))
    found = audit(list(range(a, b + 1)), args.refresh)
    lines = report(found)
    if args.report:
        with open(args.report, "w") as f:
            f.write("\n".join(lines))
    print(f"{len(found)} spans flagged, {sum(1 for f in found if not f['accepted'])} unexplained")


if __name__ == "__main__":
    main()
