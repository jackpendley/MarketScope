"""Betting-system definitions for the backtester (MS-044). Each system turns games into legs; the
backtest module grades and scores them. Wong teasers follow research/PREREGISTRATION.md Addendum E.
"""

from __future__ import annotations

from typing import Literal

import numpy as np
import pandas as pd

from .backtest import grade_spread

Variant = Literal["V0", "V1", "V2"]
VARIANTS: dict[Variant, str] = {
    "V0": "every Wong leg",
    "V1": "closing total 49 or less",
    "V2": "total 49 or less, road teams only",
}
PRICES = (-110, -120, -125, -130, -135, -140)
PRIMARY_PRICE = -125
TEASE = 6.0
TOTAL_MAX = 49.0


def in_wong_range(team_line: float) -> bool:
    """Favourite -7.5 to -8.5 (teased through 7 and 3) or underdog +1.5 to +2.5 (through 3 and 7)."""
    return -8.5 <= team_line <= -7.5 or 1.5 <= team_line <= 2.5


def wong_legs(games: pd.DataFrame, variant: Variant = "V0") -> pd.DataFrame:
    """Legs from games with columns: game_id, season, week, kickoff, home, away, home_line (the home
    team's closing spread), total (closing total), margin (home minus away, final).

    At most one leg per game: if the home line is in range the home team is the leg, else the away
    team (away line = -home line) if that is in range."""
    rows = []
    for g in games.itertuples():
        for team, road, line, margin in ((g.home, False, g.home_line, g.margin),
                                         (g.away, True, -g.home_line, -g.margin)):
            if not in_wong_range(line):
                continue
            if variant in ("V1", "V2") and not (g.total <= TOTAL_MAX):
                break
            if variant == "V2" and not road:
                break
            teased = line + TEASE
            rows.append({"game_id": g.game_id, "season": g.season, "week": g.week, "kickoff": g.kickoff,
                         "team": team, "road": road, "role": "favourite" if line < 0 else "underdog",
                         "line": line, "teased": teased, "total": g.total,
                         "result": grade_spread(margin, teased)})
            break
    return pd.DataFrame(rows, columns=["game_id", "season", "week", "kickoff", "team", "road", "role",
                                       "line", "teased", "total", "result"])


# --- Catalogue F1–F10 (PREREGISTRATION.md Addendum F) ------------------------------------------
#
# Input: one row per game with columns game_id, season, week, kickoff, home, away, neutral,
# division, home_line, total, margin (home - away), points (home + away), et_hour, and per side
# (prefix home_/away_): rest, bye, short, travel_km, tz_shift, body_clock, alt_change.

BREAK_EVEN_110 = 110 / 210
CATALOGUE: dict[str, str] = {
    "F1": "Home underdogs",
    "F2": "Divisional underdogs",
    "F3": "Underdogs of 7 or more",
    "F4": "Off a bye vs a team that is not",
    "F5": "Home team vs a road team on a short week",
    "F6": "Home team vs a road team on an early body clock",
    "F7": "Divisional unders",
    "F8": "Primetime unders",
    "F9": "Unders on totals of 50 or more",
    "F10": "ML: walk-forward logistic regression",
}
POSITION_COLUMNS = ["system", "game_id", "season", "week", "kickoff", "market", "side", "line", "result"]


def _side(g, system: str, home: bool) -> dict:
    team = g.home if home else g.away
    line = g.home_line if home else -g.home_line
    margin = g.margin if home else -g.margin
    return {"system": system, "game_id": g.game_id, "season": g.season, "week": g.week, "kickoff": g.kickoff,
            "market": "spread", "side": team, "line": line, "result": grade_spread(margin, line)}


def _under(g, system: str) -> dict:
    v = g.total - g.points
    return {"system": system, "game_id": g.game_id, "season": g.season, "week": g.week, "kickoff": g.kickoff,
            "market": "total", "side": "under", "line": g.total,
            "result": "win" if v > 0 else "push" if v == 0 else "loss"}


def rule_positions(games: pd.DataFrame) -> pd.DataFrame:
    """F1–F9: deterministic rules on pre-kickoff fields and the closing line."""
    rows = []
    for g in games.itertuples():
        if g.home_line >= 0.5 and not g.neutral:
            rows.append(_side(g, "F1", home=True))
        if g.division and g.home_line != 0:
            rows.append(_side(g, "F2", home=g.home_line > 0))
        if abs(g.home_line) >= 7:
            rows.append(_side(g, "F3", home=g.home_line > 0))
        if bool(g.home_bye) != bool(g.away_bye) and (g.home_bye or g.away_bye):
            rows.append(_side(g, "F4", home=bool(g.home_bye)))
        if g.away_short:
            rows.append(_side(g, "F5", home=True))
        if g.away_body_clock <= 10.5:
            rows.append(_side(g, "F6", home=True))
        if g.division:
            rows.append(_under(g, "F7"))
        if g.et_hour >= 19:
            rows.append(_under(g, "F8"))
        if g.total >= 50:
            rows.append(_under(g, "F9"))
    return pd.DataFrame(rows, columns=POSITION_COLUMNS)


F10_FEATURES = ["home_line", "total", "division", "neutral", "home_rest", "away_rest", "home_bye", "away_bye",
                "home_short", "away_short", "away_travel_km", "away_tz_shift", "away_body_clock", "away_alt_change"]
F10_THRESHOLD = 0.55
F10_FIRST_SEASON = 2018


def f10_matrix(games: pd.DataFrame) -> np.ndarray:
    return games[F10_FEATURES].astype(float).fillna(0.0).to_numpy()


def f10_model(train: pd.DataFrame):
    """Standardised L2 logistic regression (C = 1.0) on home cover (pushes dropped)."""
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    t = train[train["margin"] + train["home_line"] != 0]
    y = (t["margin"] + t["home_line"] > 0).astype(int)
    return make_pipeline(StandardScaler(), LogisticRegression(C=1.0, max_iter=1000)).fit(f10_matrix(t), y)


def f10_positions(games: pd.DataFrame, first_season: int = F10_FIRST_SEASON) -> pd.DataFrame:
    """Walk-forward: season s is predicted by a model fitted only on seasons before s."""
    rows = []
    for s in sorted(x for x in games["season"].unique() if x >= first_season):
        train, test = games[games["season"] < s], games[games["season"] == s]
        if train.empty or test.empty:
            continue
        p_home = f10_model(train).predict_proba(f10_matrix(test))[:, 1]
        for g, p in zip(test.itertuples(), p_home):
            if p >= F10_THRESHOLD:
                rows.append({**_side(g, "F10", home=True), "p": p})
            elif 1 - p >= F10_THRESHOLD:
                rows.append({**_side(g, "F10", home=False), "p": 1 - p})
    return pd.DataFrame(rows, columns=POSITION_COLUMNS + ["p"])


def holm(pvalues: dict[str, float], alpha: float = 0.05) -> dict[str, bool]:
    """Holm–Bonferroni step-down: which hypotheses are rejected at family-wise alpha."""
    order = sorted(pvalues, key=pvalues.get)
    m, out, still = len(order), {}, True
    for i, k in enumerate(order):
        still = still and pvalues[k] <= alpha / (m - i)
        out[k] = still
    return out
