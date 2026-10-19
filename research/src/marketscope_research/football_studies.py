"""MS-035 football studies R1, R3, R4 and R5, implementing research/PREREGISTRATION.md (committed
before this code). Pure functions over pandas DataFrames; loading lives in run_football_studies.py.

Orientation: margins are home minus away; close margin = -(nflverse home closing spread);
consensus margin = -(board consensus home spread); ATS residual = actual margin - close margin.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

RESAMPLES = 5000
SEED = 2026
RATING_SEASONS = range(2016, 2025)  # 2025 is the untouched ratings-v1 test season
HOME_ADVANTAGE = 1.6  # ratings-v1 home advantage, points (RATINGS.md parameter table)

R1_LEADS = {"6 days": (pd.Timedelta(days=6), pd.Timedelta(hours=12)),
            "3 days": (pd.Timedelta(days=3), pd.Timedelta(hours=12)),
            "1 day": (pd.Timedelta(days=1), pd.Timedelta(hours=6))}
R1_CLOSE_WITHIN = pd.Timedelta(hours=6)
R1_MIN_GAMES = 60
R1_MIN_BOOK_GAMES = 40
R3_MIN_GAMES, R3_MIN_WINDY, R3_WINDY = 200, 30, 15.0
R3_MIN_CROSSINGS = 15
R4_MIN_MOVE_GAMES = 60
R5_FROM_WEEK = 5
R5_SPLIT_WEEK = 9


@dataclass
class Estimate:
    value: float
    low: float
    high: float
    n: int
    se: float | None = None

    def excludes_zero(self) -> str:
        if self.low > 0:
            return "above 0"
        if self.high < 0:
            return "below 0"
        return "includes 0"


def _rng() -> np.random.Generator:
    return np.random.default_rng(SEED)


def ols(y: np.ndarray, x: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """OLS with an intercept: (coefficients, HC1 standard errors); x is (n,) or (n, k)."""
    X = np.column_stack([np.ones(len(y)), np.asarray(x, float).reshape(len(y), -1)])
    xtx_inv = np.linalg.inv(X.T @ X)
    beta = xtx_inv @ X.T @ y
    e = y - X @ beta
    n, k = X.shape
    meat = (X * e[:, None] ** 2).T @ X
    cov = xtx_inv @ meat @ xtx_inv * n / (n - k)
    return beta, np.sqrt(np.diag(cov))


def slope(y: np.ndarray, x: np.ndarray, resamples: int = RESAMPLES) -> Estimate:
    """Slope on x with a bootstrap interval resampling rows (each row one game or team-season)."""
    y, x = np.asarray(y, float), np.asarray(x, float)
    beta, se = ols(y, x)
    rng = _rng()
    n = len(y)
    boots = np.empty(resamples)
    for b in range(resamples):
        i = rng.integers(0, n, n)
        boots[b] = ols(y[i], x[i])[0][1]
    lo, hi = np.quantile(boots, [0.025, 0.975])
    return Estimate(float(beta[1]), float(lo), float(hi), n, float(se[1]))


def mean_ci(values: np.ndarray, resamples: int = RESAMPLES) -> Estimate:
    v = np.asarray(values, float)
    rng = _rng()
    boots = v[rng.integers(0, len(v), (resamples, len(v)))].mean(axis=1)
    lo, hi = np.quantile(boots, [0.025, 0.975])
    return Estimate(float(v.mean()), float(lo), float(hi), len(v))


# --- R1: market accuracy over time -----------------------------------------------------------

def consensus_at_leads(consensus: pd.DataFrame, kickoffs: pd.Series) -> pd.DataFrame:
    """Per event: the consensus home spread at each lead (nearest snapshot within tolerance) and at
    the close (last pregame snapshot within 6 h of kickoff). NaN where no snapshot qualifies."""
    c = consensus.copy()
    c["kickoff"] = c["event_id"].map(kickoffs)
    c = c[c["observed_at"] < c["kickoff"]]
    rows = []
    for eid, g in c.groupby("event_id"):
        kick = g["kickoff"].iloc[0]
        row = {"event_id": eid}
        for name, (lead, tol) in R1_LEADS.items():
            target = kick - lead
            w = g[(g["observed_at"] - target).abs() <= tol]
            row[name] = float(w.iloc[(w["observed_at"] - target).abs().argsort().iloc[0]]["consensus"]) if len(w) else np.nan
        last = g.sort_values("observed_at").iloc[-1]
        row["close"] = float(last["consensus"]) if kick - last["observed_at"] <= R1_CLOSE_WITHIN else np.nan
        row["close_observed_at"] = last["observed_at"]
        rows.append(row)
    return pd.DataFrame(rows)


def r1_accuracy(df: pd.DataFrame) -> dict:
    """df: event_id, margin, the lead columns and close (home spreads), nflverse_close (home spread)."""
    leads = [*R1_LEADS, "close"]
    full = df.dropna(subset=leads)
    err = {k: (-full[k] - full["margin"]).abs().to_numpy() for k in leads}
    out = {"games": len(full), "gate": len(full) >= R1_MIN_GAMES,
           "mae": {k: float(v.mean()) for k, v in err.items()},
           "diff_vs_close": {k: mean_ci(err[k] - err["close"]) for k in R1_LEADS}}
    if "nflverse_close" in full and full["nflverse_close"].notna().all():
        nv = (-full["nflverse_close"] - full["margin"]).abs().to_numpy()
        out["mae"]["nflverse close"] = float(nv.mean())
        out["diff_vs_close"]["nflverse close"] = mean_ci(nv - err["close"])
    return out


def r1_books(board: pd.DataFrame, closes: pd.DataFrame, margins: pd.Series) -> pd.DataFrame:
    """Each board book's home spread in the close snapshot vs the consensus, paired by game.
    board: event_id, observed_at, board_book, point; closes: event_id, close_observed_at, close."""
    m = board.merge(closes, left_on=["event_id", "observed_at"], right_on=["event_id", "close_observed_at"])
    m["margin"] = m["event_id"].map(margins)
    m = m.dropna(subset=["margin", "close"])
    rows = []
    for book, g in m.groupby("board_book"):
        book_err = (-g["point"] - g["margin"]).abs().to_numpy()
        cons_err = (-g["close"] - g["margin"]).abs().to_numpy()
        est = mean_ci(book_err - cons_err) if len(g) >= R1_MIN_BOOK_GAMES else None
        rows.append({"book": book, "games": len(g), "mae": float(book_err.mean()), "vs_consensus": est})
    return pd.DataFrame(rows)


# --- R3: weather and totals ------------------------------------------------------------------

def r3_pricing(df: pd.DataFrame) -> dict:
    """df: wind_mph, precip_in, total (actual), close_total, season (one row per game)."""
    resid = (df["total"] - df["close_total"]).to_numpy(float)
    windy = df["wind_mph"] >= R3_WINDY
    out = {"games": len(df), "windy": int(windy.sum()),
           "gate": len(df) >= R3_MIN_GAMES and windy.sum() >= R3_MIN_WINDY,
           "slope": slope(resid, df["wind_mph"].to_numpy(float)),
           "buckets": []}
    bins = pd.cut(df["wind_mph"], [-np.inf, 10, R3_WINDY, np.inf], right=False, labels=["< 10", "10-15", ">= 15"])
    for label, g in df.assign(resid=resid).groupby(bins, observed=True):
        out["buckets"].append({"wind": str(label), "games": len(g), "mean_residual": mean_ci(g["resid"].to_numpy()),
                               "mean_close": float(g["close_total"].mean())})
    seasons = pd.get_dummies(df["season"], drop_first=True).to_numpy(float)
    x = np.column_stack([df["wind_mph"].to_numpy(float), seasons])
    beta, se = ols(df["close_total"].to_numpy(float), x)
    out["close_per_mph"] = (float(beta[1]), float(se[1]))
    wet = df["precip_in"] > 0
    out["precip"] = {"wet_games": int(wet.sum()),
                     "wet_mean_residual": float(resid[wet.to_numpy()].mean()) if wet.any() else np.nan,
                     "dry_mean_residual": float(resid[~wet.to_numpy()].mean())}
    return out


def r3_movement(df: pd.DataFrame) -> dict:
    """df: crossed (bool), move (totals consensus close - 3 days)."""
    crossed = df[df["crossed"]]
    out = {"games": len(df), "crossings": len(crossed), "gate": len(crossed) >= R3_MIN_CROSSINGS}
    if out["gate"]:
        out["crossed_move"] = mean_ci(crossed["move"].to_numpy())
        out["other_move"] = mean_ci(df[~df["crossed"]]["move"].to_numpy())
    return out


# --- R4 / R5: ratings, luck and the close ----------------------------------------------------

def rating_games(games: pd.DataFrame, snaps: pd.DataFrame) -> pd.DataFrame:
    """Attach each team's snapshot after the previous week (point in time) to every game.
    games: game_id, season, week, home, away (franchise codes), neutral, margin, close_margin.
    snaps: season, week, team, adj_em, luck."""
    s = snaps.rename(columns={"week": "snap_week"})
    g = games.assign(snap_week=games["week"] - 1)
    for side in ("home", "away"):
        g = g.merge(s.rename(columns={"team": side, "adj_em": f"{side}_em", "luck": f"{side}_luck"}),
                    on=["season", "snap_week", side], how="left")
    g["rating_margin"] = g["home_em"] - g["away_em"] + np.where(g["neutral"], 0.0, HOME_ADVANTAGE)
    g["gap"] = g["rating_margin"] - g["close_margin"]
    g["ats"] = g["margin"] - g["close_margin"]
    g["rating_resid"] = g["margin"] - g["rating_margin"]
    g["luck_diff"] = g["home_luck"] - g["away_luck"]
    return g.dropna(subset=["home_em", "away_em", "close_margin", "margin"])


def r4_priced(g: pd.DataFrame) -> dict:
    est = slope(g["ats"].to_numpy(), g["gap"].to_numpy())
    per_season = {int(s): float(ols(x["ats"].to_numpy(float), x["gap"].to_numpy(float))[0][1])
                  for s, x in g.groupby("season")}
    late = g[g["season"] >= 2023]
    positive = sum(v > 0 for v in per_season.values())
    return {"games": len(g), "slope": est, "per_season": per_season, "positive_seasons": positive,
            "claim": est.low > 0 and positive >= 6,
            "out_of_sample": slope(late["ats"].to_numpy(), late["gap"].to_numpy()),
            "mean_abs_gap": float(g["gap"].abs().mean())}


def r4_move(df: pd.DataFrame) -> dict:
    """df: gap6 (rating margin - 6-day consensus margin), move (close - 6-day, margin orientation)."""
    d = df.dropna(subset=["gap6", "move"])
    out = {"games": len(d), "gate": len(d) >= R4_MIN_MOVE_GAMES}
    if out["gate"]:
        out["slope"] = slope(d["move"].to_numpy(), d["gap6"].to_numpy())
    return out


def r5_luck(g: pd.DataFrame) -> dict:
    d = g[(g["week"] >= R5_FROM_WEEK)].dropna(subset=["luck_diff"])
    return {"games": len(d), "market": slope(d["ats"].to_numpy(), d["luck_diff"].to_numpy()),
            "ratings": slope(d["rating_resid"].to_numpy(), d["luck_diff"].to_numpy()),
            "luck_sd": float(d["luck_diff"].std())}


def r5_persistence(snaps: pd.DataFrame, last_week: dict[int, int]) -> dict:
    """Team-seasons: luck after week 9 vs luck gained from week 10 to the end of the regular season."""
    a = snaps[snaps["week"] == R5_SPLIT_WEEK][["season", "team", "luck"]]
    ends = snaps[snaps["week"] == snaps["season"].map(last_week)][["season", "team", "luck"]]
    m = a.merge(ends, on=["season", "team"], suffixes=("_early", "_end"))
    m["later"] = m["luck_end"] - m["luck_early"]
    return {"team_seasons": len(m), "slope": slope(m["later"].to_numpy(), m["luck_early"].to_numpy())}
