"""Venue catalog (MS-028): data/venue_aliases.csv maps nflverse stadium names to venues;
data/venues.csv holds each venue's roof type (curated), coordinates (Wikipedia), and elevation
and IANA time zone (Open-Meteo). Rebuild the measured columns with:

    PYTHONPATH=src .venv/bin/python -m marketscope_football.venues
"""

from __future__ import annotations

import csv
import json
import math
import time
import urllib.parse
import urllib.request
from pathlib import Path

DATA = Path(__file__).resolve().parents[2] / "data"
UA = "MarketScope/0.1 (NFL research portfolio project; https://github.com/jackpendley/MarketScope)"
ROOF_TYPES = {"outdoor", "dome", "retractable"}
VENUE_COLUMNS = ["venue_key", "wikipedia_title", "roof_type", "lat", "lon", "elevation_m", "timezone", "source_url"]


def read_csv(name: str) -> list[dict]:
    with (DATA / name).open() as f:
        return list(csv.DictReader(f))


def venues() -> dict[str, dict]:
    return {v["venue_key"]: v for v in read_csv("venues.csv")}


def aliases() -> dict[str, str]:
    return {a["stadium"]: a["venue_key"] for a in read_csv("venue_aliases.csv")}


def overrides() -> dict[str, str]:
    """game_id -> venue_key where nflverse's stadium is wrong (e.g. international games
    labelled with the home team's own stadium)."""
    return {o["game_id"]: o["venue_key"] for o in read_csv("venue_overrides.csv")}


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _get(url: str) -> dict:
    return json.load(urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=30))


def refresh() -> None:
    rows = read_csv("venues.csv")
    q = urllib.parse.urlencode({"action": "query", "prop": "coordinates|info", "inprop": "url", "colimit": "max",
                                "format": "json", "formatversion": "2", "redirects": "1",
                                "titles": "|".join(r["wikipedia_title"] for r in rows)})
    d = _get(f"https://en.wikipedia.org/w/api.php?{q}")["query"]
    redir = {r["to"]: r["from"] for r in d.get("redirects", [])}
    norm = {n["to"]: n["from"] for n in d.get("normalized", [])}
    found = {}
    for p in d["pages"]:
        asked = redir.get(p["title"], p["title"])
        found[norm.get(asked, asked)] = p
    for r in rows:
        p = found[r["wikipedia_title"]]
        c = p["coordinates"][0]
        r["lat"], r["lon"] = f"{c['lat']:.5f}", f"{c['lon']:.5f}"
        r["source_url"] = p["fullurl"]
        om = _get("https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode(
            {"latitude": r["lat"], "longitude": r["lon"], "timezone": "auto", "forecast_days": 1, "current": "temperature_2m"}))
        r["elevation_m"], r["timezone"] = f"{om['elevation']:.0f}", om["timezone"]
        time.sleep(0.2)
    with (DATA / "venues.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=VENUE_COLUMNS)
        w.writeheader()
        w.writerows(rows)
    print(f"refreshed {len(rows)} venues")


if __name__ == "__main__":
    refresh()
