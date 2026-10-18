"""Coaching staff and play-callers (ADR-031). Pure parsing and assembly, unit-tested.

Sources, in order of authority:
1. Head coaches per game: nflverse schedules (`home_coach`/`away_coach`), which also give the
   exact week of every head-coach change.
2. Coordinators (OC, DC, special teams): the end-of-season staff on each team's Wikipedia
   season article ({{NFL final staff}}), or the team's current staff template for the season
   in progress. Each row cites the exact revision (oldid).
3. Mid-season coordinator changes and play-callers: curated CSVs in apps/football/data/, one
   cited source per row.

Facts only (names, roles, weeks); no text is copied.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

ROLE_LABELS = {
    "head coach": "HC", "interim head coach": "HC",
    "offensive coordinator": "OC", "interim offensive coordinator": "OC", "co-offensive coordinator": "OC",
    "defensive coordinator": "DC", "interim defensive coordinator": "DC", "co-defensive coordinator": "DC",
    "special teams coordinator": "STC", "interim special teams coordinator": "STC",
}
ROLES = ("HC", "OC", "DC", "STC")

LINK = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|([^\]]+))?\]\]")
LINE = re.compile(r"^\*\s*(.+?)\s+[–—-]\s+(.+?)\s*$", re.M)


@dataclass(frozen=True)
class Coach:
    coach_id: str  # Wikipedia article title (underscored) when linked, else "name:<slug>"
    name: str


def slug(name: str) -> str:
    """Comparable form of a name: ASCII, lowercase, no suffix ("Pete Carmichael Jr." == "Pete Carmichael")."""
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[,\s]+(jr|sr|ii|iii|iv)\.?$", "", s.strip())
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def _clean(text: str) -> str:
    text = re.sub(r"<ref[^>]*/>|<ref[^>]*>.*?</ref>", "", text, flags=re.S)
    text = re.sub(r"\{\{[^{}]*\}\}", "", text)
    return re.sub(r"<[^>]+>", "", text).strip()


def coaches_in(value: str) -> list[Coach]:
    """Coaches named in a staff value: every wiki link, or the plain text when unlinked.
    'A and B' (co-coordinators) yields two coaches."""
    value = re.sub(r"\((?:interim|acting)[^)]*\)", "", _clean(value), flags=re.I)
    links = LINK.findall(value)
    if links:
        return [Coach(t.strip().replace(" ", "_"), (label or t).strip()) for t, label in links]
    names = [n.strip() for n in re.split(r"\s+and\s+|,", value) if n.strip()]
    return [Coach(f"name:{slug(n)}", n) for n in names]


def role_of(label: str) -> str | None:
    """'Assistant head coach/defensive coordinator' -> DC; 'Assistant head coach' -> None."""
    label = LINK.sub(lambda m: m.group(2) or m.group(1), _clean(label))
    for part in label.lower().split("/"):
        role = ROLE_LABELS.get(part.strip())
        if role:
            return role
    return None


def staff_block(wikitext: str) -> str | None:
    """The {{NFL final staff ...}} template body, or a current-staff template page."""
    i = wikitext.find("{{NFL final staff")
    if i >= 0:
        depth, j = 0, i
        while j < len(wikitext):
            if wikitext.startswith("{{", j):
                depth, j = depth + 1, j + 2
            elif wikitext.startswith("}}", j):
                depth, j = depth - 1, j + 2
                if depth == 0:
                    return wikitext[i:j]
            else:
                j += 1
        return wikitext[i:]
    # A team staff template (current season): any staff line whose label is the head coach.
    return wikitext if any(role_of(label) == "HC" for label, _ in LINE.findall(wikitext)) else None


def staff_roles(block: str) -> dict[str, list[Coach]]:
    """Role -> coaches, in listed order. A role listed twice (e.g. interim + permanent) keeps both."""
    out: dict[str, list[Coach]] = {}
    for label, value in LINE.findall(block):
        role = role_of(label)
        if role:
            for c in coaches_in(value):
                if c not in out.setdefault(role, []):
                    out[role].append(c)
    return out


def match_coach(name: str, known: list[Coach]) -> Coach:
    """Attach a Wikipedia id to a plain name (e.g. an nflverse head coach) when one is known."""
    for c in known:
        if slug(c.name) == slug(name):
            return c
    return Coach(f"name:{slug(name)}", name)


def validate_staff(rows: list[dict]) -> list[str]:
    """Problems in coaching_staff rows (empty = valid). For every team-season, its weeks are
    covered exactly once by a head coach, an offensive play-caller and a defensive play-caller;
    one coach never holds overlapping spans in one role; every fact carries a source."""
    problems: list[str] = []
    by_ts: dict[tuple, list[dict]] = {}
    for r in rows:
        by_ts.setdefault((int(r["season"]), r["team"]), []).append(r)
    truthy = {True, "True", "true", "t", 1}
    for (season, team), rs in sorted(by_ts.items()):
        first, last = min(int(r["from_week"]) for r in rs), max(int(r["to_week"]) for r in rs)
        for label, pick in (("head coach", lambda r: r["role"] == "HC"),
                            ("offensive play-caller", lambda r: r["offense_playcaller"] in truthy),
                            ("defensive play-caller", lambda r: r["defense_playcaller"] in truthy)):
            count = [0] * (last + 1)
            for r in filter(pick, rs):
                for w in range(int(r["from_week"]), int(r["to_week"]) + 1):
                    count[w] += 1
            bad = [w for w in range(first, last + 1) if count[w] != 1]
            if bad:
                problems.append(f"{season} {team}: {label} count != 1 in weeks {bad[:5]}")
        spans: dict[tuple, list[tuple[int, int]]] = {}
        for r in rs:
            spans.setdefault((r["role"], r["coach_id"]), []).append((int(r["from_week"]), int(r["to_week"])))
            if not r["coach_id"] or not r["coach_name"]:
                problems.append(f"{season} {team}: row without a coach")
            if r["role"] != "PC" and not r["source_url"]:
                problems.append(f"{season} {team} {r['role']} {r['coach_name']}: no source")
            if r["playcaller_basis"] and any(b != "rule" for b in r["playcaller_basis"].split(" | ")) \
                    and not r["playcaller_source_url"]:
                problems.append(f"{season} {team} {r['coach_name']}: play-caller basis without a source")
        for (role, cid), ss in spans.items():
            ss.sort()
            if any(b[0] <= a[1] for a, b in zip(ss, ss[1:])):
                problems.append(f"{season} {team}: overlapping {role} spans for {cid}")
    return problems
