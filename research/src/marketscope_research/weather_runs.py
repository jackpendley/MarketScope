"""Archived weather-model runs per game (MS-056, research/PREREGISTRATION.md Addendum U).

Open-Meteo's Single Runs API serves each run of a model by its initialisation time (00/06/12/18
UTC), from 2 April 2026. For each run we ask, in one request, for every outdoor or retractable-roof
venue with a kickoff 7–84 hours after the run, and keep the game-window values: the mean wind and
the max gust over the kickoff hour and the three hours after it, and the precipitation sum. That
covers runs available (run + 6 h) between kickoff − 72 h and kickoff − 1 h, plus each one's
predecessor for the revision.

Results are cached as Parquet under fixtures/open-meteo/local/ (gitignored; rebuildable). Weather
data by Open-Meteo.com (CC BY 4.0).
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import pandas as pd

API = "https://single-runs-api.open-meteo.com/v1/forecast"
UA = "MarketScope/0.1 (NFL research portfolio project; https://github.com/jackpendley/MarketScope)"
WINDOW_HOURS = 4
RUN_HOURS = 6
MIN_LEAD, MAX_LEAD = pd.Timedelta(hours=7), pd.Timedelta(hours=84)
COLUMNS = ["game_id", "model", "run", "wind_mph", "gust_mph", "precip_in"]
CACHE = Path(__file__).resolve().parents[3] / "fixtures" / "open-meteo" / "local"


def runs_for(kickoffs: pd.Series) -> list[pd.Timestamp]:
    """Every 6-hourly run with some kickoff 7–84 h after it."""
    first = (kickoffs.min() - MAX_LEAD).floor(f"{RUN_HOURS}h")
    last = kickoffs.max() - MIN_LEAD
    return [r for r in pd.date_range(first, last, freq=f"{RUN_HOURS}h")
            if ((kickoffs - r >= MIN_LEAD) & (kickoffs - r <= MAX_LEAD)).any()]


def fetch_run(model: str, run: pd.Timestamp, coords: list[tuple[float, float]]) -> list[pd.DataFrame] | None:
    """Hourly wind, gust and precipitation from one run at several locations (one frame each, UTC
    index), or None if the archive does not have the run."""
    q = urllib.parse.urlencode({
        "latitude": ",".join(f"{lat:.4f}" for lat, _ in coords),
        "longitude": ",".join(f"{lon:.4f}" for _, lon in coords),
        "hourly": "wind_speed_10m,wind_gusts_10m,precipitation", "models": model,
        "run": run.strftime("%Y-%m-%dT%H:%M"), "wind_speed_unit": "mph", "precipitation_unit": "inch",
        "timezone": "GMT",
    })
    req = urllib.request.Request(f"{API}?{q}", headers={"User-Agent": UA})
    for attempt in range(3):
        try:
            d = json.load(urllib.request.urlopen(req, timeout=90))
            break
        except urllib.error.HTTPError as e:
            if e.code == 400:  # "The requested model run is not available"
                return None
            if attempt == 2:
                raise
        except Exception:  # transient network errors: back off, then give up loudly
            if attempt == 2:
                raise
        time.sleep(5 * (attempt + 1))
    out = []
    for loc in d if isinstance(d, list) else [d]:
        h = pd.DataFrame(loc["hourly"])
        h["time"] = pd.to_datetime(h["time"], utc=True)
        out.append(h.set_index("time"))
    return out


def window_values(hourly: pd.DataFrame, kickoff: pd.Timestamp) -> dict | None:
    """Game-window values, or None if any hour is missing."""
    start = kickoff.floor("h")
    w = hourly.loc[start: start + pd.Timedelta(hours=WINDOW_HOURS - 1)]
    if len(w) < WINDOW_HOURS or w[["wind_speed_10m", "wind_gusts_10m", "precipitation"]].isna().any().any():
        return None
    return {"wind_mph": float(w["wind_speed_10m"].mean()), "gust_mph": float(w["wind_gusts_10m"].max()),
            "precip_in": float(w["precipitation"].sum())}


def build(games: pd.DataFrame, model: str, cache: Path = CACHE, now: pd.Timestamp | None = None) -> pd.DataFrame:
    """games: game_id, kickoff (UTC), lat, lon. Fetches only runs not yet cached (and already
    available at `now`); returns every cached row for these games."""
    now = now or pd.Timestamp.now(tz="UTC")
    path = cache / f"runs_{model}.parquet"
    have = pd.read_parquet(path) if path.exists() else pd.DataFrame(columns=COLUMNS)
    done = set(zip(have["game_id"], pd.to_datetime(have["run"], utc=True)))
    rows = []
    for run in runs_for(games["kickoff"]):
        if run + pd.Timedelta(hours=RUN_HOURS) > now:
            continue
        lead = games["kickoff"] - run
        todo = games[(lead >= MIN_LEAD) & (lead <= MAX_LEAD)]
        todo = todo[[(g, run) not in done for g in todo["game_id"]]]
        if not len(todo):
            continue
        frames = fetch_run(model, run, list(zip(todo["lat"], todo["lon"])))
        time.sleep(0.5)
        if frames is None:
            continue
        for g, hourly in zip(todo.itertuples(), frames):
            v = window_values(hourly, g.kickoff)
            if v is not None:
                rows.append({"game_id": g.game_id, "model": model, "run": run, **v})
    if rows:
        have = pd.concat([have, pd.DataFrame(rows, columns=COLUMNS)], ignore_index=True)
        cache.mkdir(parents=True, exist_ok=True)
        have.to_parquet(path, index=False)
    have["run"] = pd.to_datetime(have["run"], utc=True)
    return have[have["game_id"].isin(set(games["game_id"]))].reset_index(drop=True)
