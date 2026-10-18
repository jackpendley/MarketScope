"""Point-in-time weather forecasts for games (MS-028, ADR-032).

Open-Meteo's Previous Runs API returns, for every hour, the value predicted N x 24 h before
that hour (`*_previous_dayN`). A forecast at lead N days is therefore known at least N days
before kickoff, so it can feed a prediction made N days out, reproducibly, from 2024 on.
Lead 0 is the latest run before the hour (close to what was expected at kickoff); it is a
near-kickoff estimate, not an observation.

Only venues where weather can matter are fetched: outdoor and retractable-roof stadiums
(whether a retractable roof will be open is unknown before the game). Values are averaged
over the game window: the kickoff hour and the three hours after it.
"""

from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

import pandas as pd

API = "https://previous-runs-api.open-meteo.com/v1/forecast"
UA = "MarketScope/0.1 (NFL research portfolio project; https://github.com/jackpendley/MarketScope)"
LEADS = (0, 1, 3, 7)  # days
WINDOW_HOURS = 4  # kickoff hour + 3
VARIABLES = {"temperature_2m": "temperature_f", "wind_speed_10m": "wind_mph", "wind_gusts_10m": "gust_mph",
             "precipitation": "precip_in"}
SOURCE = "open-meteo previous-runs (best match)"


def hourly_names() -> list[str]:
    return [f"{v}_previous_day{n}" if n else v for v in VARIABLES for n in LEADS]


def fetch_hourly(lat: float, lon: float, start: str, end: str) -> pd.DataFrame:
    """Hourly forecasts (UTC) for one location and date range, one column per variable x lead."""
    q = urllib.parse.urlencode({
        "latitude": lat, "longitude": lon, "hourly": ",".join(hourly_names()), "start_date": start, "end_date": end,
        "temperature_unit": "fahrenheit", "wind_speed_unit": "mph", "precipitation_unit": "inch", "timezone": "GMT",
    })
    req = urllib.request.Request(f"{API}?{q}", headers={"User-Agent": UA})
    for attempt in range(3):
        try:
            d = json.load(urllib.request.urlopen(req, timeout=60))
            break
        except Exception:  # transient network/API errors: back off, then give up loudly
            if attempt == 2:
                raise
            time.sleep(5 * (attempt + 1))
    df = pd.DataFrame(d["hourly"])
    df["time"] = pd.to_datetime(df["time"], utc=True)
    return df.set_index("time")


def game_rows(games: pd.DataFrame, hourly: pd.DataFrame, now: datetime) -> list[dict]:
    """One row per (game, lead) whose game-window values are all present and whose lead had
    already elapsed at `now` (a forecast for a future kickoff is stored only once it exists)."""
    rows = []
    for g in games.itertuples(index=False):
        start = pd.Timestamp(g.kickoff_utc).floor("h")
        window = hourly.loc[start: start + pd.Timedelta(hours=WINDOW_HOURS - 1)]
        if len(window) < WINDOW_HOURS:
            continue
        for n in LEADS:
            if start.to_pydatetime() - timedelta(days=n) > now:
                continue
            cols = {out: f"{v}_previous_day{n}" if n else v for v, out in VARIABLES.items()}
            vals = window[list(cols.values())]
            if vals.isna().any().any():
                continue
            rows.append({
                "game_id": g.game_id, "lead_days": n, "forecast_hour_utc": start.to_pydatetime(),
                "temperature_f": round(float(vals[cols["temperature_f"]].mean()), 1),
                "wind_mph": round(float(vals[cols["wind_mph"]].mean()), 1),
                "gust_mph": round(float(vals[cols["gust_mph"]].max()), 1),
                "precip_in": round(float(vals[cols["precip_in"]].sum()), 3),
                "source": SOURCE,
            })
    return rows


def fetch_for_games(games: pd.DataFrame, venues: dict[str, dict], now: datetime | None = None) -> list[dict]:
    """`games`: game_id, kickoff_utc, venue_key. One API call per venue and season."""
    now = now or datetime.now(timezone.utc)
    rows: list[dict] = []
    # The API serves at most ~two weeks ahead; games further out get forecasts later.
    kick_all = pd.to_datetime(games["kickoff_utc"], utc=True)
    games = games[kick_all <= pd.Timestamp(now) + pd.Timedelta(days=8)]
    games = games.assign(season_key=pd.to_datetime(games["kickoff_utc"], utc=True).dt.year)
    for (venue_key, _), grp in games.groupby(["venue_key", "season_key"]):
        v = venues[venue_key]
        if v["roof_type"] == "dome":
            continue
        kick = pd.to_datetime(grp["kickoff_utc"], utc=True)
        start = kick.min().strftime("%Y-%m-%d")
        end = (kick.max() + pd.Timedelta(hours=WINDOW_HOURS)).strftime("%Y-%m-%d")
        hourly = fetch_hourly(float(v["lat"]), float(v["lon"]), start, end)
        rows += game_rows(grp, hourly, now)
        time.sleep(0.3)
    return rows
