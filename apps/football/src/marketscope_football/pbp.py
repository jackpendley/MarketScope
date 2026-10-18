"""Local play-by-play cache (ADR-028): nflverse play-by-play is large and never stored in
Postgres. Each season is cached as Parquet under apps/football/.cache/pbp/ (gitignored), with
a manifest recording the nflreadpy version, row count and content hash, so every aggregate in
the database can name the exact data it was built from."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import nflreadpy as nfl
import polars as pl

CACHE_DIR = Path(__file__).resolve().parents[2] / ".cache" / "pbp"

# Only the columns the aggregations use; keeps each season's file small (~5 MB).
PBP_COLUMNS = [
    "game_id", "play_id", "season", "season_type", "week", "home_team", "away_team", "posteam", "defteam",
    "play_type", "pass", "rush", "special", "qb_dropback", "qb_kneel", "qb_spike", "qb_scramble", "sack",
    "down", "ydstogo", "yardline_100", "qtr", "half_seconds_remaining", "game_seconds_remaining",
    "fixed_drive", "epa", "qb_epa", "wp", "success", "yards_gained", "cpoe", "xpass", "shotgun", "no_huddle",
    "interception", "pass_defense_1_player_id", "fumble", "fumbled_1_team", "fumble_lost",
    "posteam_score", "posteam_score_post", "fourth_down_converted", "fourth_down_failed",
    "penalty", "penalty_team", "penalty_yards", "field_goal_attempt", "field_goal_result", "kick_distance",
    "extra_point_attempt", "extra_point_result", "return_touchdown", "td_team",
    "passer_id",  # the dropback player (scrambles and sacks included): QB ratings (MS-031)
]


def _manifest_path() -> Path:
    return CACHE_DIR / "manifest.json"


def read_manifest() -> dict:
    p = _manifest_path()
    return json.loads(p.read_text()) if p.exists() else {}


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_season(season: int, refresh: bool = False) -> pl.DataFrame:
    """One season's play-by-play (selected columns). Downloads on a cache miss or `refresh`."""
    path = CACHE_DIR / f"pbp_{season}.parquet"
    if refresh or not path.exists():
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        df = nfl.load_pbp([season]).select(PBP_COLUMNS)
        df.write_parquet(path)
        manifest = read_manifest()
        manifest[str(season)] = {
            "nflreadpy": nfl.__version__,
            "rows": df.height,
            "games": df["game_id"].n_unique(),
            "sha256": file_sha256(path),
            "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        _manifest_path().write_text(json.dumps(manifest, indent=2, sort_keys=True))
    return pl.read_parquet(path)


def source_version(seasons: list[int]) -> str:
    """Compact provenance string for nfl_ingest_runs.source_version."""
    manifest = read_manifest()
    digest = hashlib.sha256(
        "".join(manifest.get(str(s), {}).get("sha256", "?") for s in seasons).encode()
    ).hexdigest()[:16]
    return f"nflreadpy {nfl.__version__}; pbp {seasons[0]}-{seasons[-1]} sha256:{digest}"
