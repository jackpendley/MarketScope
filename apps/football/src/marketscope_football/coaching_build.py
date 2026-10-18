"""Build apps/football/data/coaching_staff.csv (ADR-031).

    PYTHONPATH=src .venv/bin/python -m marketscope_football.coaching_build [--refresh] [--seasons 2016-2026]

Inputs: Wikipedia season articles / current staff templates (MediaWiki API, cached in
.cache/wiki/, cited by revision), nflverse schedules (head coach per game), and the curated
CSVs in data/: coordinator_changes.csv, playcaller_lists.csv, playcaller_overrides.csv.

Play-caller rule per team-week (docs/DATA_DICTIONARY.md): a season list or a dated override
when one applies; otherwise the coordinator for that side, or the head coach when the team has
no coordinator. Every row says which basis it rests on.
"""

from __future__ import annotations

import argparse
import csv
import json
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from .coaching import Coach, slug, staff_block, staff_roles

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
CACHE = ROOT / ".cache" / "wiki"
API = "https://en.wikipedia.org/w/api.php"
UA = "MarketScope/0.1 (NFL research portfolio project; https://github.com/jackpendley/MarketScope)"
OUT_COLUMNS = ["season", "team", "role", "coach_id", "coach_name", "from_week", "to_week", "offense_playcaller",
               "defense_playcaller", "source_url", "playcaller_basis", "playcaller_source_url"]

# Wikipedia team names by nflverse abbreviation (abbreviations change with relocations).
WIKI_TEAM = {
    "ARI": "Arizona Cardinals", "ATL": "Atlanta Falcons", "BAL": "Baltimore Ravens", "BUF": "Buffalo Bills",
    "CAR": "Carolina Panthers", "CHI": "Chicago Bears", "CIN": "Cincinnati Bengals", "CLE": "Cleveland Browns",
    "DAL": "Dallas Cowboys", "DEN": "Denver Broncos", "DET": "Detroit Lions", "GB": "Green Bay Packers",
    "HOU": "Houston Texans", "IND": "Indianapolis Colts", "JAX": "Jacksonville Jaguars", "KC": "Kansas City Chiefs",
    "OAK": "Oakland Raiders", "LV": "Las Vegas Raiders", "SD": "San Diego Chargers", "LAC": "Los Angeles Chargers",
    "LA": "Los Angeles Rams", "MIA": "Miami Dolphins", "MIN": "Minnesota Vikings", "NE": "New England Patriots",
    "NO": "New Orleans Saints", "NYG": "New York Giants", "NYJ": "New York Jets", "PHI": "Philadelphia Eagles",
    "PIT": "Pittsburgh Steelers", "SF": "San Francisco 49ers", "SEA": "Seattle Seahawks", "TB": "Tampa Bay Buccaneers",
    "TEN": "Tennessee Titans", "WAS": "Washington Commanders",
}
WAS_NAME = {2016: "Washington Redskins", 2017: "Washington Redskins", 2018: "Washington Redskins",
            2019: "Washington Redskins", 2020: "Washington Football Team", 2021: "Washington Football Team"}


def wiki_team(abbr: str, season: int) -> str:
    return WAS_NAME.get(season, WIKI_TEAM[abbr]) if abbr == "WAS" else WIKI_TEAM[abbr]


def fetch_pages(titles: list[str]) -> dict[str, dict]:
    """Latest revision of each title (redirects followed): {requested title: {title, revid, content}}."""
    out: dict[str, dict] = {}
    for i in range(0, len(titles), 50):
        batch = titles[i:i + 50]
        q = urllib.parse.urlencode({"action": "query", "prop": "revisions", "rvprop": "content|ids", "rvslots": "main",
                                    "format": "json", "formatversion": "2", "redirects": "1", "titles": "|".join(batch)})
        req = urllib.request.Request(f"{API}?{q}", headers={"User-Agent": UA})
        d = json.load(urllib.request.urlopen(req, timeout=30))
        norm = {n["to"]: n["from"] for n in d["query"].get("normalized", [])}
        redir = {r["to"]: r["from"] for r in d["query"].get("redirects", [])}
        for p in d["query"]["pages"]:
            if "missing" in p:
                continue
            asked = redir.get(p["title"], p["title"])
            asked = norm.get(asked, asked)
            rev = p["revisions"][0]
            out[asked] = {"title": p["title"], "revid": rev["revid"], "content": rev["slots"]["main"]["content"]}
        time.sleep(1)
    return out


def load_wiki(teams_by_season: dict[int, set[str]], current: int, refresh: bool) -> dict[tuple[int, str], dict]:
    """(season, team) -> page used for coordinators: the season article, or for the season in
    progress the team's current staff template (season articles get {{NFL final staff}} only
    after the season)."""
    path = CACHE / "staff_pages.json"
    cached = json.loads(path.read_text()) if path.exists() and not refresh else {}
    wanted = {}
    for season, teams in teams_by_season.items():
        for t in teams:
            name = wiki_team(t, season)
            wanted[f"{season}|{t}"] = f"Template:{name} staff" if season == current else f"{season} {name} season"
    missing = [k for k in wanted if k not in cached]
    if missing:
        pages = fetch_pages(sorted({wanted[k] for k in missing}))
        for k in missing:
            if wanted[k] in pages:
                cached[k] = pages[wanted[k]]
        CACHE.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(cached))
    return {(int(k.split("|")[0]), k.split("|")[1]): v for k, v in cached.items()}


def permalink(page: dict) -> str:
    return f"https://en.wikipedia.org/w/index.php?oldid={page['revid']}"


@dataclass
class TeamSeason:
    season: int
    team: str
    weeks: list[int]  # game weeks in order (REG + POST)
    kickoff: dict[int, date]  # week -> kickoff date (UTC)
    hc: dict[int, str]  # week -> head coach name (nflverse)

    def first_week_after(self, d: date) -> int | None:
        later = [w for w in self.weeks if self.kickoff[w] > d]
        return later[0] if later else None


def _read(name: str) -> list[dict]:
    with (DATA / name).open() as f:
        return list(csv.DictReader(f))


class Directory:
    """Name -> Coach with a Wikipedia id where any staff page links one."""

    def __init__(self) -> None:
        self.by_slug: dict[str, list[Coach]] = defaultdict(list)

    def add(self, c: Coach) -> None:
        if c not in self.by_slug[slug(c.name)]:
            self.by_slug[slug(c.name)].append(c)

    def resolve(self, name: str, local: list[Coach]) -> Coach:
        s = slug(name)
        for c in local:
            if slug(c.name) == s:
                return c
        linked = [c for c in self.by_slug.get(s, []) if not c.coach_id.startswith("name:")]
        if len(linked) == 1:
            return linked[0]
        return Coach(f"name:{s}", name)


def week_role_assignments(ts: TeamSeason, roles: dict[str, list[Coach]], changes: list[dict],
                          directory: Directory, role_names: tuple[str, ...] = ("OC", "DC", "STC"),
                          ) -> tuple[dict[str, dict[int, list[Coach]]], list[str]]:
    """role -> week -> coaches holding the title that week. Returns problems needing curation."""
    problems: list[str] = []
    out: dict[str, dict[int, list[Coach]]] = {}
    for role in role_names:
        listed = list(roles.get(role, []))
        mine = [c for c in changes if c["role"] == role]
        for c in mine:
            if c["kind"] == "ignore":
                listed = [x for x in listed if slug(x.name) != slug(c["coach_out"])]
            elif c["kind"] == "add":  # a coordinator the staff page omits, whole season
                listed.append(directory.resolve(c["coach_in"], listed))
        spans: dict[str, tuple[Coach, int, int]] = {}
        first, last = ts.weeks[0], ts.weeks[-1]
        for coach in listed:
            spans[slug(coach.name)] = (coach, first, last)
        for c in [x for x in mine if x["kind"] == "change"]:
            wk = ts.first_week_after(date.fromisoformat(c["effective_date"]))
            if wk is None:
                problems.append(f"{ts.season} {ts.team} {role}: change after the last game")
                continue
            prev = [w for w in ts.weeks if w < wk]
            out_coach = spans.get(slug(c["coach_out"]), (directory.resolve(c["coach_out"], listed), first, last))
            if prev:
                spans[slug(c["coach_out"])] = (out_coach[0], out_coach[1], prev[-1])
            else:
                spans.pop(slug(c["coach_out"]), None)
            if c["coach_in"]:
                coach_in = directory.resolve(c["coach_in"], listed)
                end = spans.get(slug(c["coach_in"]), (coach_in, wk, last))[2]
                spans[slug(c["coach_in"])] = (coach_in, wk, end)
        by_week: dict[int, list[Coach]] = {w: [] for w in ts.weeks}
        for coach, a, b in spans.values():
            for w in ts.weeks:
                if a <= w <= b:
                    by_week[w].append(coach)
        co = any(x["kind"] == "co" for x in mine)
        for w, holders in by_week.items():
            if len(holders) > 1 and not co:
                problems.append(f"{ts.season} {ts.team} {role} week {w}: {[h.name for h in holders]} need curation")
                break
        out[role] = by_week
    return out, problems


def build(seasons: list[int], refresh: bool) -> tuple[list[dict], list[str]]:
    import nflreadpy as nfl

    sched = nfl.load_schedules(seasons).to_pandas()
    current = max(seasons)
    team_seasons: dict[tuple[int, str], TeamSeason] = {}
    for g in sched.itertuples(index=False):
        d = date.fromisoformat(g.gameday)
        for team, coach in ((g.home_team, g.home_coach), (g.away_team, g.away_coach)):
            ts = team_seasons.setdefault((g.season, team), TeamSeason(g.season, team, [], {}, {}))
            ts.weeks.append(int(g.week))
            ts.kickoff[int(g.week)] = d
            if isinstance(coach, str):
                ts.hc[int(g.week)] = coach
    for ts in team_seasons.values():
        ts.weeks.sort()
        # Future games have no coach yet: assume the latest known head coach stays.
        known = [w for w in ts.weeks if w in ts.hc]
        for w in ts.weeks:
            if w not in ts.hc and known:
                ts.hc[w] = ts.hc[max([k for k in known if k <= w] or [known[0]])]

    teams_by_season: dict[int, set[str]] = defaultdict(set)
    for s, t in team_seasons:
        teams_by_season[s].add(t)
    pages = load_wiki(teams_by_season, current, refresh)

    directory = Directory()
    roles_by_ts: dict[tuple[int, str], dict[str, list[Coach]]] = {}
    for key, page in pages.items():
        block = staff_block(page["content"])
        roles_by_ts[key] = staff_roles(block) if block else {}
        for coaches in roles_by_ts[key].values():
            for c in coaches:
                directory.add(c)

    changes = defaultdict(list)
    for c in _read("coordinator_changes.csv"):
        changes[(int(c["season"]), c["team"])].append(c)
    lists = {(int(r["season"]), r["team"], r["side"]): r for r in _read("playcaller_lists.csv")}
    overrides = defaultdict(list)
    for r in _read("playcaller_overrides.csv"):
        overrides[(int(r["season"]), r["team"], r["side"])].append(r)

    rows: list[dict] = []
    problems: list[str] = []
    stale_report: list[str] = []
    for key in sorted(team_seasons):
        ts = team_seasons[key]
        season, team = key
        if season not in seasons:
            continue
        page = pages.get(key)
        roles = roles_by_ts.get(key, {})
        if page is None or not roles:
            problems.append(f"{season} {team}: no Wikipedia staff found")
        local = [c for cs in roles.values() for c in cs]
        assign, issues = week_role_assignments(ts, roles, changes[key], directory)
        problems += issues
        # Head coaches: nflverse per game, unless it is stale. Staff pages often list only the
        # end-of-season head coach, while nflverse misses interims from 2024 on and lags a season
        # for the season in progress. nflverse is trusted when it names every head coach the
        # staff page lists (matched on last name, which also absorbs typos like "Jay Rosburg").
        wiki_hc = roles.get("HC", [])
        def last(name: str) -> str:
            return slug(name).rsplit("-", 1)[-1]
        def to_coach(name: str) -> Coach:
            same = [h for h in wiki_hc if last(h.name) == last(name)]
            return same[0] if len(same) == 1 else directory.resolve(name, local)
        hc_coach = {w: to_coach(n) for w, n in ts.hc.items()}
        hc_source = {w: "nflverse schedules (home_coach/away_coach)" for w in ts.weeks}
        named = {last(c.name) for c in hc_coach.values()}
        if wiki_hc and not {last(h.name) for h in wiki_hc} <= named:
            hc_assign, issues = week_role_assignments(ts, roles, changes[key], directory, ("HC",))
            problems += issues
            change_hc = {slug(c["coach_in"]): c["source_url"] for c in changes[key] if c["role"] == "HC"}
            for w in ts.weeks:
                hc_coach[w] = hc_assign["HC"][w][0]
                hc_source[w] = change_hc.get(slug(hc_coach[w].name)) or (permalink(page) if page else "")
            stale_report.append(f"{season} {team}")

        callers: dict[str, dict[int, tuple[Coach, str, str]]] = {}
        for side, role in (("offense", "OC"), ("defense", "DC")):
            def rule(w: int) -> tuple[Coach, str, str]:
                holders = assign[role][w]
                return (holders[0], "rule", "") if holders else (hc_coach[w], "rule", "")

            events: list[tuple[int, Coach | None, str, str]] = []
            lst = lists.get((season, team, side))
            if lst:
                coach = directory.resolve(lst["coach"], local + list(hc_coach.values()))
                if slug(coach.name) != slug(rule(ts.weeks[0])[0].name):
                    events.append((ts.weeks[0], coach, "list", lst["source_url"]))
            for o in sorted(overrides[(season, team, side)], key=lambda r: r["effective_date"]):
                wk = ts.weeks[0] if not o["effective_date"] else ts.first_week_after(
                    date.fromisoformat(o["effective_date"]))
                if wk is None:
                    problems.append(f"{season} {team} {side}: override after the last game")
                    continue
                coach = None if o["coach"] == "=rule" else directory.resolve(o["coach"], local + list(hc_coach.values()))
                events.append((wk, coach, o["source_kind"], o["source_url"]))
            events.sort(key=lambda e: e[0])
            current_override = None
            by_week = {}
            for w in ts.weeks:
                for e in [e for e in events if e[0] == w]:
                    current_override = e
                if current_override and current_override[1] is not None:
                    by_week[w] = (current_override[1], current_override[2], current_override[3])
                elif current_override:  # explicit return to the rule, sourced
                    r = rule(w)
                    by_week[w] = (r[0], current_override[2], current_override[3])
                elif lst and slug(rule(w)[0].name) == slug(lst["coach"]):
                    by_week[w] = (rule(w)[0], "list", lst["source_url"])  # the rule, confirmed by a list
                else:
                    by_week[w] = rule(w)
            callers[side] = by_week

        # Titled holders per week, then play-calling-only rows for anyone else who called.
        holders: dict[tuple[str, str], dict[int, Coach]] = defaultdict(dict)
        for w in ts.weeks:
            holders[("HC", hc_coach[w].coach_id)][w] = hc_coach[w]
            for role in ("OC", "DC", "STC"):
                for c in assign[role][w]:
                    holders[(role, c.coach_id)][w] = c
        for side in ("offense", "defense"):
            for w, (c, _, _) in callers[side].items():
                titled = any(cid == c.coach_id and w in weeks for (_, cid), weeks in holders.items())
                if not titled:
                    holders[("PC", c.coach_id)][w] = c

        def flag_role(side: str, w: int) -> str:
            """The one row that carries a play-caller flag when the caller holds several titles
            (e.g. an interim head coach who stays OC): the side's coordinator row, else HC."""
            cid = callers[side][w][0].coach_id
            held = [role for (role, c), weeks in holders.items() if c == cid and w in weeks]
            for role in ("OC" if side == "offense" else "DC", "HC", "OC", "DC", "STC", "PC"):
                if role in held:
                    return role
            return "PC"

        change_src = {slug(c["coach_in"] or c["coach_out"]): c["source_url"] for c in changes[key]}
        for (role, cid), weeks in holders.items():
            coach = next(iter(weeks.values()))
            seg = None
            for w in ts.weeks:
                if w not in weeks:
                    if seg:
                        rows.append(seg)
                        seg = None
                    continue
                off = callers["offense"][w][0].coach_id == cid and flag_role("offense", w) == role
                de = callers["defense"][w][0].coach_id == cid and flag_role("defense", w) == role
                bases = [callers[s][w] for s, f in (("offense", off), ("defense", de)) if f]
                basis = " | ".join(b[1] for b in bases)
                src = " | ".join(b[2] for b in bases if b[2])
                sig = (off, de, basis, src)
                if seg and seg["_sig"] == sig:
                    seg["to_week"] = w
                    continue
                if seg:
                    rows.append(seg)
                # Spans are continuous across bye weeks: every segment starts right after the
                # previous game week, so a change made during a bye covers the bye.
                i = ts.weeks.index(w)
                start = ts.weeks[i - 1] + 1 if i > 0 else w
                if role == "HC":
                    source = hc_source[w]
                elif role == "PC":
                    source = src
                else:
                    source = change_src.get(slug(coach.name)) or (permalink(page) if page else "")
                seg = {"season": season, "team": team, "role": role, "coach_id": cid, "coach_name": coach.name,
                       "from_week": start, "to_week": w, "offense_playcaller": off, "defense_playcaller": de,
                       "source_url": source, "playcaller_basis": basis, "playcaller_source_url": src, "_sig": sig}
            if seg:
                rows.append(seg)
    if stale_report:
        problems.append("INFO head coaches taken from staff pages (nflverse stale): " + ", ".join(stale_report))
    for r in rows:
        r.pop("_sig")
    rows.sort(key=lambda r: (r["season"], r["team"], ["HC", "OC", "DC", "STC", "PC"].index(r["role"]), r["from_week"]))
    return rows, problems


def check_current(season: int) -> list[str]:
    """Compare each team's current Wikipedia staff template with the latest CSV holders of HC,
    OC and DC for `season`. Returns human-readable differences (a prompt to curate, not an error:
    Wikipedia can lag, and interim titles are often edited in late)."""
    rows = _read("coaching_staff.csv")
    latest: dict[tuple[str, str], set[str]] = defaultdict(set)
    last_week = defaultdict(int)
    for r in rows:
        if int(r["season"]) == season:
            last_week[r["team"]] = max(last_week[r["team"]], int(r["to_week"]))
    for r in rows:
        if int(r["season"]) == season and int(r["to_week"]) == last_week[r["team"]] and r["role"] in ("HC", "OC", "DC"):
            latest[(r["team"], r["role"])].add(slug(r["coach_name"]))
    teams = sorted(last_week)
    pages = fetch_pages([f"Template:{wiki_team(t, season)} staff" for t in teams])
    diffs = []
    for t in teams:
        page = pages.get(f"Template:{wiki_team(t, season)} staff")
        if not page:
            diffs.append(f"{t}: staff template not found")
            continue
        roles = staff_roles(staff_block(page["content"]) or "")
        for role in ("HC", "OC", "DC"):
            wiki = {slug(c.name) for c in roles.get(role, [])}
            if wiki != latest[(t, role)]:
                diffs.append(f"{t} {role}: Wikipedia {sorted(wiki) or '-'} vs CSV {sorted(latest[(t, role)]) or '-'}")
    return diffs


def main() -> None:
    from .ingest import parse_seasons

    ap = argparse.ArgumentParser()
    ap.add_argument("--seasons", default="2016-2026")
    ap.add_argument("--refresh", action="store_true", help="re-fetch Wikipedia pages")
    ap.add_argument("--report", help="write the markdown summary of data/coaching_staff.csv to this path")
    ap.add_argument("--check", action="store_true",
                    help="only compare the current season with Wikipedia (prints GitHub warnings)")
    args = ap.parse_args()
    if args.report:
        Path(args.report).write_text("\n".join(report(_read("coaching_staff.csv"))) + "\n")
        print(f"wrote {args.report}")
        return
    if args.check:
        season = parse_seasons("current")[0]
        diffs = check_current(season)
        for d in diffs:
            print(f"::warning title=Coaching staff drift {season}::{d}")
        print(f"coaching check {season}: {len(diffs)} difference(s)")
        return
    rows, problems = build(parse_seasons(args.seasons), args.refresh)
    with (DATA / "coaching_staff.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=OUT_COLUMNS)
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {len(rows)} rows to data/coaching_staff.csv")
    for p in problems:
        print("NEEDS CURATION:", p)



FRANCHISE = {"OAK": "LV", "SD": "LAC", "STL": "LA"}


def report(rows: list[dict]) -> list[str]:
    """Markdown summary of coaching_staff.csv: how each play-caller fact is supported, and
    play-caller continuity (an input to the ratings' season-to-season carryover, RATINGS.md)."""
    weeks: dict[tuple, dict[str, tuple[str, str]]] = defaultdict(dict)  # (season, team, week) -> side -> (coach, basis)
    hc: dict[tuple, str] = {}
    for r in rows:
        for w in range(int(r["from_week"]), int(r["to_week"]) + 1):
            k = (int(r["season"]), FRANCHISE.get(r["team"], r["team"]), w)
            if r["role"] == "HC":
                hc[k] = r["coach_id"]
            bases = r["playcaller_basis"].split(" | ")
            if r["offense_playcaller"] == "True":
                weeks[k]["offense"] = (r["coach_id"], bases[0])
            if r["defense_playcaller"] == "True":
                weeks[k]["defense"] = (r["coach_id"], bases[-1])
    lines = ["# Coaching staff and play-callers", "",
             "Generated by `python -m marketscope_football.coaching_build --report` from `data/coaching_staff.csv` "
             "(ADR-031). Counts are team-weeks, 2016–2026 (2026 through the scheduled end of the regular season).", "",
             "## How each play-caller is supported", "",
             "| Basis | Offense | Defense | Meaning |", "| --- | --- | --- | --- |"]
    meaning = {"list": "named in a season-wide list of every team's play-caller (ESPN 2023–26, 4for4 2020, partial "
                       "2016/2018 lists)",
               "direct": "a source about that coach and season (or the dated change)",
               "bracketed": "same coach and team named in lists before and after, no reported change in between",
               "stint": "a source covering the coach's tenure, not that exact season",
               "rule": "no source: the coordinator for that side (or the head coach when there is none)"}
    total = len(weeks)
    for basis in ("list", "direct", "bracketed", "stint", "rule"):
        o = sum(1 for v in weeks.values() if v["offense"][1] == basis)
        d = sum(1 for v in weeks.values() if v["defense"][1] == basis)
        lines.append(f"| {basis} | {o / total:.0%} | {d / total:.0%} | {meaning[basis]} |")
    lines += ["", "Defensive play-calling is rarely reported team by team, so most defensive weeks rest on the rule. "
              "Known exceptions (head coaches or untitled assistants calling the defense) are sourced overrides.", "",
              "## Play-caller continuity by season", "",
              "| Season | Teams | New offensive play-caller | New defensive play-caller | Head coach calls offense "
              "| Mid-season offensive changes |", "| --- | --- | --- | --- | --- | --- |"]
    seasons = sorted({k[0] for k in weeks})
    for s in seasons:
        teams = sorted({k[1] for k in weeks if k[0] == s})
        new_o = new_d = hc_o = mid = 0
        for t in teams:
            ws = sorted(k[2] for k in weeks if k[0] == s and k[1] == t)
            first = weeks[(s, t, ws[0])]
            prev = [k for k in weeks if k[0] == s - 1 and k[1] == t]
            if prev:
                last_prev = weeks[max(prev, key=lambda k: k[2])]
                new_o += first["offense"][0] != last_prev["offense"][0]
                new_d += first["defense"][0] != last_prev["defense"][0]
            hc_o += first["offense"][0] == hc.get((s, t, ws[0]))
            callers = [weeks[(s, t, w)]["offense"][0] for w in ws]
            mid += sum(a != b for a, b in zip(callers, callers[1:])) > 0
        lines.append(f"| {s} | {len(teams)} | {new_o if s > seasons[0] else '—'} | {new_d if s > seasons[0] else '—'} "
                     f"| {hc_o} | {mid} |")
    lines += ["", "New = the Week 1 play-caller differs from the previous season's final one (relocated franchises "
              "are followed). RATINGS.md conditions offensive carryover on the same play-caller and the same QB.", "",
              "## Head-coach source", "",
              "Head coaches come from nflverse schedules (`home_coach`/`away_coach`), which give the exact week of a "
              "change, except where nflverse is stale: it does not record several interim head coaches (e.g. 2016 LA, "
              "2019 CAR, 2024 CHI/NO/NYJ, 2025 NYG/TEN), and for the season in progress it still shows the previous "
              "season's coaches. There the Wikipedia staff page and dated changes in `coordinator_changes.csv` are used."]
    return lines


if __name__ == "__main__":
    main()
