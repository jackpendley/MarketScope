"""QB layer (MS-031a): who is expected to start, how good he is, and how far that is from the QB
quality the team's pass ratings were learned from.

Expected starter (rule R5, chosen on 2016-22; it names the actual starter 92.3% of the time vs 88.2%
for "last game's starter"): the team's previous starter, unless the injury report lists him Out or
Doubtful (then depth-chart QB1, or QB2 when QB1 is the injured starter); in a team's first game of a
season, depth-chart QB1. A Questionable starter plays with probability P_PLAYS_QUESTIONABLE
(2016-22: 63.7% of 124), else his replacement. Depth charts: weekly through 2024; from 2025 the
latest timestamped chart at least 24 h before kickoff. The injury report is the final weekly report.

QB rating: exponentially time-decayed, shrunk mean of the QB's adjusted EPA per dropback relative to
the league (same measurement as the pass channel), with `prior_dropbacks` of replacement level.
Team baseline: the dropback-weighted, time-decayed average of the CURRENT ratings of the QBs who
threw the team's recent passes - the QB quality its pass ratings were learned from.
Game feature: league dropbacks per game x (E[rating of the starter] - baseline), home minus away.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass

import nflreadpy as nfl
import pandas as pd
import polars as pl

from ..pbp import load_season
from ..schedules import FRANCHISE
from .observations import CACHE_DIR, qb_game_frame

P_PLAYS_QUESTIONABLE = 0.637
TIMESTAMPED_DEPTH_FROM = 2025
DEPTH_LEAD = pd.Timedelta(hours=24)
LEAGUE_HALF_LIFE_DAYS = 182.0


def _fr(t):
    return FRANCHISE.get(t, t)


@dataclass
class QBParams:
    half_life_days: float  # QB rating memory
    prior_dropbacks: float  # shrinkage toward replacement level
    baseline_half_life_days: float  # memory of the team's QB baseline
    replacement: float  # replacement-level EPA/dropback relative to league (fitted on 2013-22 debuts)
    p_questionable: float = P_PLAYS_QUESTIONABLE


# ---- Data (cached) --------------------------------------------------------------------------

def load_qb_games(seasons: list[int], refresh: bool = False) -> pd.DataFrame:
    path = CACHE_DIR / f"qb_games_{seasons[0]}_{seasons[-1]}.parquet"
    if path.exists() and not refresh:
        return pd.read_parquet(path)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    df = pl.concat([qb_game_frame(load_season(s)) for s in seasons]).to_pandas()
    df["team"] = df["team"].map(_fr)
    df.to_parquet(path)
    return df


def load_depth(seasons: list[int], refresh: bool = False) -> pd.DataFrame:
    """QB depth-chart rows: season, week (weekly charts), dt (timestamped charts), team, rank, gsis_id."""
    path = CACHE_DIR / f"qb_depth_{seasons[0]}_{seasons[-1]}.parquet"
    if path.exists() and not refresh:
        return pd.read_parquet(path)
    frames = []
    for s in seasons:
        d = nfl.load_depth_charts([s]).to_pandas()
        if s < TIMESTAMPED_DEPTH_FROM:
            d = d[(d["position"] == "QB") & d["week"].notna() & d["depth_team"].astype(str).isin(["1", "2"])]
            frames.append(pd.DataFrame({"season": s, "week": d["week"].astype(int), "dt": pd.NaT,
                                        "team": d["club_code"].map(_fr), "rank": d["depth_team"].astype(int),
                                        "gsis_id": d["gsis_id"]}))
        else:
            d = d[(d["pos_abb"] == "QB") & d["pos_rank"].isin([1, 2])]
            frames.append(pd.DataFrame({"season": s, "week": -1, "dt": pd.to_datetime(d["dt"], utc=True),
                                        "team": d["team"].map(_fr), "rank": d["pos_rank"].astype(int),
                                        "gsis_id": d["gsis_id"]}))
    df = pd.concat(frames, ignore_index=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path)
    return df


def load_injury_status(seasons: list[int], refresh: bool = False) -> pd.DataFrame:
    """Final weekly injury-report status per player: season, week, team, gsis_id, position, report_status."""
    path = CACHE_DIR / f"injuries_{seasons[0]}_{seasons[-1]}.parquet"
    if path.exists() and not refresh:
        return pd.read_parquet(path)
    d = nfl.load_injuries(seasons).to_pandas()
    df = pd.DataFrame({"season": d["season"].astype(int), "week": d["week"].astype(int), "team": d["team"].map(_fr),
                       "gsis_id": d["gsis_id"], "position": d["position"], "report_status": d["report_status"]})
    df = df.drop_duplicates(["season", "week", "team", "gsis_id"], keep="last")
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path)
    return df


def player_names(refresh: bool = False) -> dict[str, str]:
    """gsis_id -> display name (nflverse players), for reports."""
    path = CACHE_DIR / "players.parquet"
    if refresh or not path.exists():
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        nfl.load_players().select("gsis_id", "display_name").write_parquet(path)
    p = pd.read_parquet(path).dropna(subset=["gsis_id"])
    return dict(zip(p["gsis_id"], p["display_name"]))


# ---- Expected starter -----------------------------------------------------------------------

def team_games(games: pd.DataFrame) -> pd.DataFrame:
    """One row per team per game in kickoff order, with the actual starting QB (nflverse)."""
    rows = []
    for side in ("home", "away"):
        rows.append(pd.DataFrame({"game_id": games["game_id"], "season": games["season"], "week": games["week"],
                                  "kickoff_utc": games["kickoff_utc"], "team": games[side],
                                  "actual_qb": games[f"{side}_qb_id"]}))
    return pd.concat(rows, ignore_index=True).sort_values(["kickoff_utc", "game_id", "team"]).reset_index(drop=True)


def depth_at(depth: pd.DataFrame, tg: pd.DataFrame) -> pd.DataFrame:
    """Depth-chart QB1/QB2 known before each team-game (weekly charts by week; timestamped charts:
    the latest snapshot at least DEPTH_LEAD before kickoff)."""
    weekly = depth[depth["week"] >= 0]
    w = weekly.pivot_table(index=["season", "week", "team"], columns="rank", values="gsis_id", aggfunc="first")
    out = []
    stamped = depth[depth["week"] < 0].sort_values("dt")
    by_team = {t: g for t, g in stamped.groupby("team")}
    for r in tg.itertuples(index=False):
        if r.season < TIMESTAMPED_DEPTH_FROM:
            key = (r.season, r.week, r.team)
            row = w.loc[key] if key in w.index else None
            out.append((None if row is None else row.get(1), None if row is None else row.get(2)))
        else:
            g = by_team.get(r.team)
            if g is None:
                out.append((None, None))
                continue
            g = g[g["dt"] <= r.kickoff_utc - DEPTH_LEAD]
            if g.empty:
                out.append((None, None))
                continue
            last = g[g["dt"] == g["dt"].iloc[-1]]
            out.append((last.loc[last["rank"] == 1, "gsis_id"].squeeze() if (last["rank"] == 1).any() else None,
                        last.loc[last["rank"] == 2, "gsis_id"].squeeze() if (last["rank"] == 2).any() else None))
    return pd.DataFrame(out, columns=["dc1", "dc2"], index=tg.index)


def expected_starters(tg: pd.DataFrame, depth: pd.DataFrame, injuries: pd.DataFrame,
                      p_questionable: float = P_PLAYS_QUESTIONABLE) -> pd.DataFrame:
    """Adds prev_qb, dc1, dc2, status, exp_qb (most likely starter), alt_qb (if he doesn't play) and
    p_exp (probability exp_qb plays). Uses only information available before each game."""
    tg = tg.copy()
    done = tg["actual_qb"].notna()
    prev, last = [], {}
    first = []
    seen_season = set()
    for r in tg.itertuples(index=False):
        prev.append(last.get(r.team))
        first.append((r.team, r.season) not in seen_season)
        seen_season.add((r.team, r.season))
        if isinstance(r.actual_qb, str):
            last[r.team] = r.actual_qb
    tg["prev_qb"], tg["first_game"] = prev, first
    tg = tg.join(depth_at(depth, tg))
    st = injuries.set_index(["season", "week", "team", "gsis_id"])["report_status"]
    tg["status"] = [st.get((r.season, r.week, r.team, r.prev_qb)) for r in tg.itertuples(index=False)]
    exp, alt, p = [], [], []
    for r in tg.itertuples(index=False):
        repl = r.dc1 if r.dc1 != r.prev_qb else r.dc2
        if r.first_game or r.prev_qb is None:
            e, a = r.dc1 if isinstance(r.dc1, str) else r.prev_qb, r.dc2
            pe = 1.0
        elif r.status in ("Out", "Doubtful"):
            e, a, pe = repl, None, 1.0
        elif r.status == "Questionable":
            e, a, pe = r.prev_qb, repl, p_questionable
        else:
            e, a, pe = r.prev_qb, repl, 1.0
        exp.append(e if isinstance(e, str) else None)
        alt.append(a if isinstance(a, str) else None)
        p.append(pe)
    tg["exp_qb"], tg["alt_qb"], tg["p_exp"] = exp, alt, p
    tg.loc[~done, "actual_qb"] = None
    return tg


# ---- Ratings --------------------------------------------------------------------------------

class QBTracker:
    """Point-in-time QB ratings and team baselines. `rating`/`baseline` read the state before a game;
    `update` adds a completed game's dropbacks."""

    def __init__(self, p: QBParams):
        self.p = p
        self.qb: dict[str, list[float]] = {}  # id -> [sum w, sum w*(x - league), t]
        self.league = [0.0, 0.0, None]  # decayed sum w, sum w*x, t
        self.team_hist: dict[str, deque] = defaultdict(lambda: deque(maxlen=60))

    @staticmethod
    def _decay(age_days: float, half_life: float) -> float:
        return 0.5 ** (age_days / half_life)

    def _days(self, a, b) -> float:
        return (a - b).total_seconds() / 86400

    def league_mean(self, t) -> float:
        sw, swx, t0 = self.league
        return swx / sw if sw > 0 else 0.0

    def rating(self, qb: str | None, t) -> float:
        k, r = self.p.prior_dropbacks, self.p.replacement
        if qb is None or qb not in self.qb:
            return r
        sw, swr, t0 = self.qb[qb]
        f = self._decay(self._days(t, t0), self.p.half_life_days)
        return (k * r + f * swr) / (k + f * sw)

    def baseline(self, team: str, t) -> float:
        num = den = 0.0
        for t_g, qb, n in self.team_hist[team]:
            w = n * self._decay(self._days(t, t_g), self.p.baseline_half_life_days)
            num += w * self.rating(qb, t)
            den += w
        return num / den if den > 0 else self.p.replacement

    def expected_rating(self, exp_qb, alt_qb, p_exp: float, t) -> float:
        return p_exp * self.rating(exp_qb, t) + (1 - p_exp) * self.rating(alt_qb, t)

    def update(self, t, team: str, rows: list[tuple[str, int, float, float]]) -> None:
        """rows: (passer_id, dropbacks, sum of weights, sum of weighted adjusted EPA) for one team-game."""
        sw, swx, t0 = self.league
        f = self._decay(self._days(t, t0), LEAGUE_HALF_LIFE_DAYS) if t0 is not None else 0.0
        mean = self.league_mean(t)
        for qb, n, w, wx in rows:
            s = self.qb.get(qb)
            if s is None:
                s = [0.0, 0.0, t]
            g = self._decay(self._days(t, s[2]), self.p.half_life_days)
            self.qb[qb] = [g * s[0] + w, g * s[1] + (wx - w * mean), t]
            self.team_hist[team].append((t, qb, n))
        add_w = sum(r[2] for r in rows)
        add_x = sum(r[3] for r in rows)
        self.league = [f * sw + add_w, f * swx + add_x, t]


def replacement_level(qb_games: pd.DataFrame, games: pd.DataFrame, debut_seasons: range, first_dropbacks: int = 150) -> float:
    """Mean adjusted EPA/dropback relative to the league of QBs' first `first_dropbacks` career
    dropbacks, for QBs whose first dropback in our data falls in `debut_seasons` (earlier debuts
    are unknowable from 2012 data)."""
    g = qb_games.merge(games[["game_id", "season", "kickoff_utc"]], on="game_id").sort_values("kickoff_utc")
    league = g.groupby("season").apply(lambda x: x["swx"].sum() / x["sw"].sum(), include_groups=False)
    g["rel"] = g["swx"] - g["sw"] * g["season"].map(league)
    first = g.groupby("passer_id")["season"].transform("min")
    g = g[first.isin(list(debut_seasons))]
    g["cum"] = g.groupby("passer_id")["dropbacks"].cumsum()
    early = g[g["cum"] - g["dropbacks"] < first_dropbacks]
    return float(early["rel"].sum() / early["sw"].sum())


class QBAdjuster:
    """The QB game feature for the walk-forward model. mode "expected": the pre-game expected starter
    (the model); "oracle": the actual starter, known only at kickoff (hindsight, for the leakage lesson)."""

    def __init__(self, p: QBParams, starters: pd.DataFrame, qb_games: pd.DataFrame, n_pass: float,
                 mode: str = "expected"):
        self.tracker, self.n_pass, self.mode = QBTracker(p), n_pass, mode
        self.starters = {(r.game_id, r.team): (r.exp_qb, r.alt_qb, r.p_exp, r.actual_qb)
                         for r in starters.itertuples(index=False)}
        self.rows: dict[tuple[str, str], list[tuple]] = defaultdict(list)
        for r in qb_games.itertuples(index=False):
            self.rows[(r.game_id, r.team)].append((r.passer_id, int(r.dropbacks), float(r.sw), float(r.swx)))

    def side(self, game_id: str, team: str, t) -> float:
        s = self.starters.get((game_id, team))
        if s is None:
            return 0.0
        exp, alt, p, actual = s
        tr = self.tracker
        v = tr.rating(actual, t) if self.mode == "oracle" else tr.expected_rating(exp, alt, p, t)
        return self.n_pass * (v - tr.baseline(team, t))

    def feature(self, g) -> float:
        return self.side(g.game_id, g.home, g.kickoff_utc) - self.side(g.game_id, g.away, g.kickoff_utc)

    def update(self, results: pd.DataFrame) -> None:
        for g in results.sort_values("kickoff_utc").itertuples(index=False):
            for team in (g.home, g.away):
                rows = self.rows.get((g.game_id, team))
                if rows:
                    self.tracker.update(g.kickoff_utc, team, rows)
