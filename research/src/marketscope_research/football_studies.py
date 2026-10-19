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


# --- R7: play-caller impact (addendum A) -----------------------------------------------------

R7_PAIR_SEASONS = range(2016, 2024)  # pairs (s, s + 1) with s + 1 <= 2024
R7_MIN_CHANGED = 40


def last_regular_week(season: int) -> int:
    return 18 if season >= 2021 else 17


def coef_ci(y: np.ndarray, X: np.ndarray, j: int, resamples: int = RESAMPLES) -> Estimate:
    """Coefficient j (0 = intercept) of OLS y ~ X with a bootstrap interval resampling rows."""
    y, X = np.asarray(y, float), np.asarray(X, float)
    beta, se = ols(y, X)
    rng = _rng()
    n = len(y)
    boots = np.empty(resamples)
    for b in range(resamples):
        i = rng.integers(0, n, n)
        boots[b] = ols(y[i], X[i])[0][j]
    lo, hi = np.quantile(boots, [0.025, 0.975])
    return Estimate(float(beta[j]), float(lo), float(hi), n, float(se[j]))


def season_units(team_games: pd.DataFrame) -> pd.DataFrame:
    """Per (season, team): offensive points per drive and points per drive allowed, each centred on
    the season's league mean. team_games: season, team, opponent, drives, drive_points (regular season)."""
    off = team_games.groupby(["season", "team"])[["drives", "drive_points"]].sum()
    allowed = team_games.groupby(["season", "opponent"])[["drives", "drive_points"]].sum()
    allowed.index = allowed.index.set_names(["season", "team"])
    league = team_games.groupby("season")[["drives", "drive_points"]].sum()
    mean = league["drive_points"] / league["drives"]
    out = pd.DataFrame({"off": off["drive_points"] / off["drives"], "def": allowed["drive_points"] / allowed["drives"]})
    seasons = out.index.get_level_values("season")
    out["off"] -= mean.loc[seasons].to_numpy()
    out["def"] -= mean.loc[seasons].to_numpy()
    return out.reset_index()


def caller_at(staff: pd.DataFrame, side: str, week_of: dict[int, int]) -> pd.Series:
    """The {side} play-caller's coach_id per (season, team) at week week_of[season].
    staff: season, team, coach_id, from_week, to_week, offense_playcaller, defense_playcaller."""
    s = staff[staff[f"{side}_playcaller"]]
    wk = s["season"].map(week_of)
    s = s[(s["from_week"] <= wk) & (s["to_week"] >= wk)]
    dup = s.duplicated(["season", "team"], keep=False)
    if dup.any():
        raise ValueError(f"more than one {side} play-caller: {s[dup][['season', 'team']].drop_duplicates().values.tolist()}")
    return s.set_index(["season", "team"])["coach_id"]


def main_caller(staff: pd.DataFrame, side: str) -> pd.Series:
    """The {side} play-caller with the most regular-season weeks per (season, team)."""
    s = staff[staff[f"{side}_playcaller"]].copy()
    last = s["season"].map(last_regular_week)
    s["weeks"] = (np.minimum(s["to_week"], last) - s["from_week"] + 1).clip(lower=0)
    s = s.sort_values(["season", "team", "weeks", "from_week"], ascending=[True, True, False, False])
    return s.drop_duplicates(["season", "team"]).set_index(["season", "team"])["coach_id"]


def main_qb(starts: pd.DataFrame) -> pd.Series:
    """The QB with the most regular-season starts per (season, team); ties go to the later starter.
    starts: season, week, team, qb_id (one row per team-game)."""
    agg = starts.groupby(["season", "team", "qb_id"]).agg(n=("week", "size"), last=("week", "max")).reset_index()
    agg = agg.sort_values(["season", "team", "n", "last"], ascending=[True, True, False, False])
    return agg.drop_duplicates(["season", "team"]).set_index(["season", "team"])["qb_id"]


def r7_pairs(units: pd.DataFrame, staff: pd.DataFrame, starts: pd.DataFrame) -> pd.DataFrame:
    """One row per team and pair (s, s + 1): x/y offence and defence, same_off/same_def caller, same_qb."""
    u = units.set_index(["season", "team"])
    end = {s: last_regular_week(s) for s in staff["season"].unique()}
    first = {s: 1 for s in staff["season"].unique()}
    off_end, off_first = caller_at(staff, "offense", end), caller_at(staff, "offense", first)
    def_end, def_first = caller_at(staff, "defense", end), caller_at(staff, "defense", first)
    qb = main_qb(starts)
    rows = []
    for (s, team), r in u.iterrows():
        if s not in R7_PAIR_SEASONS or (s + 1, team) not in u.index:
            continue
        nxt = u.loc[(s + 1, team)]
        rows.append({"season": s, "team": team, "x_off": r["off"], "y_off": nxt["off"],
                     "x_def": r["def"], "y_def": nxt["def"],
                     "same_off": off_end.get((s, team)) == off_first.get((s + 1, team)),
                     "same_def": def_end.get((s, team)) == def_first.get((s + 1, team)),
                     "same_qb": qb.get((s, team)) == qb.get((s + 1, team))})
    return pd.DataFrame(rows)


def r7_carryover(p: pd.DataFrame, resamples: int = RESAMPLES) -> dict:
    C, Q, x = p["same_off"].to_numpy(float), p["same_qb"].to_numpy(float), p["x_off"].to_numpy(float)
    X = np.column_stack([x, C, Q, x * C, x * Q])
    changed_c, changed_q = int((C == 0).sum()), int((Q == 0).sum())
    out = {"pairs": len(p), "changed_caller": changed_c, "changed_qb": changed_q,
           "gate": changed_c >= R7_MIN_CHANGED and changed_q >= R7_MIN_CHANGED,
           "interaction": coef_ci(p["y_off"].to_numpy(), X, 4, resamples),
           "qb_interaction": coef_ci(p["y_off"].to_numpy(), X, 5, resamples),
           "overall": slope(p["y_off"].to_numpy(), x, resamples), "groups": []}
    for (c, q), g in p.groupby(["same_off", "same_qb"]):
        out["groups"].append({"same_caller": bool(c), "same_qb": bool(q), "pairs": len(g),
                              "slope": slope(g["y_off"].to_numpy(), g["x_off"].to_numpy(), resamples)})
    d, xd = p["same_def"].to_numpy(float), p["x_def"].to_numpy(float)
    out["defense"] = {"changed": int((d == 0).sum()),
                      "interaction": coef_ci(p["y_def"].to_numpy(), np.column_stack([xd, d, xd * d]), 3, resamples),
                      "same": slope(p.loc[p["same_def"], "y_def"].to_numpy(), p.loc[p["same_def"], "x_def"].to_numpy(), resamples),
                      "changed_slope": slope(p.loc[~p["same_def"], "y_def"].to_numpy(), p.loc[~p["same_def"], "x_def"].to_numpy(), resamples)}
    return out


def scheme_movers(traits: pd.DataFrame, callers: pd.Series) -> pd.DataFrame:
    """Play-callers who were the main offensive caller at team A in s and at team B != A in s + 1.
    traits: season, team and trait columns (team-season means); callers: main_caller(staff, "offense")."""
    t = traits.set_index(["season", "team"])
    by = callers.rename("coach_id").reset_index()
    rows = []
    for _, a in by.iterrows():
        nxt = by[(by["season"] == a["season"] + 1) & (by["coach_id"] == a["coach_id"]) & (by["team"] != a["team"])]
        for _, b in nxt.iterrows():
            ka, kb_prev, kb = (a["season"], a["team"]), (a["season"], b["team"]), (b["season"], b["team"])
            if ka in t.index and kb_prev in t.index and kb in t.index:
                row = {"coach_id": a["coach_id"], "season": int(a["season"]), "from": a["team"], "to": b["team"]}
                for c in t.columns:
                    row |= {f"{c}_caller": t.loc[ka, c], f"{c}_prior": t.loc[kb_prev, c], f"{c}_new": t.loc[kb, c]}
                rows.append(row)
    return pd.DataFrame(rows)


def r7_scheme(movers: pd.DataFrame, trait: str, resamples: int = RESAMPLES) -> dict:
    X = movers[[f"{trait}_caller", f"{trait}_prior"]].to_numpy(float)
    y = movers[f"{trait}_new"].to_numpy(float)
    return {"movers": len(movers), "caller": coef_ci(y, X, 1, resamples), "prior": coef_ci(y, X, 2, resamples)}


# --- R2w: market moves on newly confirmed absences (addendum B) ------------------------------

R2W_MIN_EVENTS, R2W_MIN_QB = 30, 10
R2W_SNAP_SHARE = 0.5


def injury_events(final_status: pd.DataFrame, snaps: pd.DataFrame) -> pd.DataFrame:
    """Starters newly out: listed Out on the final report for (season, week, team), averaged at least
    50% of offensive or defensive snaps over their snap rows in the team's previous three game weeks,
    and played in the team's previous game.
    final_status: season, week, team, gsis_id, position, report_status (one row per player-week).
    snaps: season, week, team, gsis_id, offense_pct, defense_pct."""
    s = snaps.assign(share=np.maximum(snaps["offense_pct"].fillna(0), snaps["defense_pct"].fillna(0)))
    team_weeks = s.groupby(["season", "team"])["week"].apply(lambda w: sorted(set(w))).to_dict()
    share = s.set_index(["season", "team", "gsis_id", "week"])["share"]
    rows = []
    for r in final_status[final_status["report_status"] == "Out"].itertuples(index=False):
        prior = [w for w in team_weeks.get((r.season, r.team), []) if w < r.week][-3:]
        if not prior:
            continue
        mine = [share.get((r.season, r.team, r.gsis_id, w)) for w in prior]
        played = [x for x in mine if x is not None]
        last = mine[-1]
        if played and last is not None and last > 0 and float(np.mean(played)) >= R2W_SNAP_SHARE:
            rows.append({"season": r.season, "week": r.week, "team": r.team, "gsis_id": r.gsis_id,
                         "qb": r.position == "QB"})
    return pd.DataFrame(rows, columns=["season", "week", "team", "gsis_id", "qb"])


def r2w(games: pd.DataFrame, events: pd.DataFrame, resamples: int = RESAMPLES) -> dict:
    """games: season, week, home, away, move (consensus margin, close - 6 days), one row per game."""
    cnt = events.groupby(["season", "week", "team"]).agg(n=("gsis_id", "size"), q=("qb", "sum"))
    def count(side: str, col: str) -> np.ndarray:
        idx = pd.MultiIndex.from_frame(games[["season", "week", side]])
        return cnt[col].reindex(idx).fillna(0).to_numpy(float)
    g = games.assign(home_n=count("home", "n"), away_n=count("away", "n"),
                     home_q=count("home", "q"), away_q=count("away", "q"))
    g["N"] = g["away_n"] - g["home_n"]
    g["Q"] = g["away_q"] - g["home_q"]
    n_events, n_qb = int(g["home_n"].sum() + g["away_n"].sum()), int(g["home_q"].sum() + g["away_q"].sum())
    out = {"games": len(g), "events": n_events, "qb_events": n_qb, "gate": n_events >= R2W_MIN_EVENTS,
           "qb_gate": n_qb >= R2W_MIN_QB, "games_with_events": int(((g["home_n"] + g["away_n"]) > 0).sum())}
    if out["gate"]:
        out["slope"] = slope(g["move"].to_numpy(), g["N"].to_numpy(), resamples)
        # Robustness, added after seeing the primary result (labelled as such in the report).
        out["slope_non_qb"] = slope(g["move"].to_numpy(), (g["N"] - g["Q"]).to_numpy(), resamples)
    qb_games = g[g["Q"] != 0]
    out["qb_moves"] = (np.sign(qb_games["Q"]) * qb_games["move"]).round(1).tolist()
    return out
