"""Games frame for evaluation: nflverse schedules 1999 onward, cached locally (gitignored) with
a manifest, one row per game, franchises unified so ratings follow relocated teams."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import nflreadpy as nfl
import numpy as np
import pandas as pd

from ..pbp import file_sha256
from ..schedules import FRANCHISE, kickoff_utc
from .design import WARMUP_FROM

CACHE_DIR = Path(__file__).resolve().parents[3] / ".cache" / "schedules"
COLUMNS = ["game_id", "season", "game_type", "week", "gameday", "gametime", "home_team", "away_team", "location",
           "home_score", "away_score", "result", "total", "spread_line", "total_line", "home_moneyline",
           "away_moneyline", "div_game", "home_qb_id", "away_qb_id",
           "stadium", "home_rest", "away_rest", "home_coach", "away_coach"]
# Columns a model must never see before its game is played (the runner drops them).
RESULT_COLUMNS = ("home_score", "away_score", "margin", "total", "home_win")


def load_schedules(last_season: int, refresh: bool = False) -> pd.DataFrame:
    path = CACHE_DIR / f"schedules_{WARMUP_FROM}_{last_season}.parquet"
    if refresh or not path.exists():
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        df = nfl.load_schedules(list(range(WARMUP_FROM, last_season + 1))).select(COLUMNS)
        df.write_parquet(path)
        manifest = {"nflreadpy": nfl.__version__, "rows": df.height, "sha256": file_sha256(path),
                    "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        (CACHE_DIR / f"{path.stem}.manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True))
    return pd.read_parquet(path)


def manifest(last_season: int) -> dict:
    p = CACHE_DIR / f"schedules_{WARMUP_FROM}_{last_season}.manifest.json"
    return json.loads(p.read_text()) if p.exists() else {}


def no_vig_home(home_ml: float, away_ml: float) -> float:
    """Home win probability from American moneylines, vig removed proportionally."""
    def implied(ml: float) -> float:
        return 100 / (ml + 100) if ml > 0 else -ml / (-ml + 100)
    h, a = implied(home_ml), implied(away_ml)
    return h / (h + a)


def games_frame(schedules: pd.DataFrame) -> pd.DataFrame:
    """One row per game, in kickoff order. `close_margin` is the nflverse closing line as an
    expected home margin (spread_line is home-positive; verified in MS-026)."""
    g = schedules.copy()
    g["kickoff_utc"] = [kickoff_utc(d, None if pd.isna(t) else t) for d, t in zip(g["gameday"], g["gametime"])]
    g["kickoff_utc"] = pd.to_datetime(g["kickoff_utc"], utc=True)
    g["home"] = g["home_team"].map(lambda t: FRANCHISE.get(t, t))
    g["away"] = g["away_team"].map(lambda t: FRANCHISE.get(t, t))
    g["neutral"] = g["location"].eq("Neutral")
    g["division"] = g["div_game"].fillna(0).astype(bool)
    g["margin"] = g["home_score"] - g["away_score"]
    g["home_win"] = np.where(g["margin"] > 0, 1.0, np.where(g["margin"] < 0, 0.0, 0.5))
    g.loc[g["margin"].isna(), "home_win"] = np.nan
    g["close_margin"] = g["spread_line"].astype(float)
    g["close_total"] = g["total_line"].astype(float)
    ok = g["home_moneyline"].notna() & g["away_moneyline"].notna()
    g["close_p_home"] = np.nan
    g.loc[ok, "close_p_home"] = [no_vig_home(h, a) for h, a in zip(g.loc[ok, "home_moneyline"], g.loc[ok, "away_moneyline"])]
    cols = ["game_id", "season", "game_type", "week", "kickoff_utc", "home", "away", "neutral", "division", "home_qb_id",
            "away_qb_id", "home_score",
            "away_score", "margin", "total", "home_win", "close_margin", "close_total", "close_p_home"]
    return g[cols].sort_values(["kickoff_utc", "game_id"]).reset_index(drop=True)
