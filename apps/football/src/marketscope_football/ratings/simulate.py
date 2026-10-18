"""Season simulation (MS-034): playoff, division, #1-seed, conference and Super Bowl odds.

Each simulated season draws the teams' true strengths once from the filter's posterior (so a team's
games are correlated), lets them drift week to week by the filter's process noise, and plays every
remaining game from the key-number margin distribution. Standings go through the NFL tiebreaking
procedures through strength of schedule (then a coin flip; the points-based steps are skipped, as in
nflseedR's default depth), then the playoff bracket is played out.

This module is pure (no model, no I/O): `SeasonInputs` carries what the rating model knows as of a
point in time; `project.py` builds it from the running model.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .margin_dist import MarginDistribution

DIVISIONS = {
    "AFC East": ("BUF", "MIA", "NE", "NYJ"),
    "AFC North": ("BAL", "CIN", "CLE", "PIT"),
    "AFC South": ("HOU", "IND", "JAX", "TEN"),
    "AFC West": ("DEN", "KC", "LAC", "LV"),
    "NFC East": ("DAL", "NYG", "PHI", "WAS"),
    "NFC North": ("CHI", "DET", "GB", "MIN"),
    "NFC South": ("ATL", "CAR", "NO", "TB"),
    "NFC West": ("ARI", "LA", "SEA", "SF"),
}  # unchanged since 2002; franchise codes (OAK/SD/STL resolve to LV/LAC/LA)
TEAMS = tuple(t for d in DIVISIONS.values() for t in d)
IX = {t: i for i, t in enumerate(TEAMS)}
DIV_OF = np.array([k for k, d in enumerate(DIVISIONS.values()) for _ in d])
CONF_OF = np.array([0 if name.startswith("AFC") else 1 for name, d in DIVISIONS.items() for _ in d])
SAME_DIV = DIV_OF[:, None] == DIV_OF[None, :]
SAME_CONF = CONF_OF[:, None] == CONF_OF[None, :]

REST_PROBABILITY = 2 / 3  # ELWAY: teams that have clinched rest their QB in the final week ~2/3 of the time
EPS = 1e-9


def n_seeds(season: int) -> int:
    return 7 if season >= 2020 else 6


def last_regular_week(season: int) -> int:
    return 18 if season >= 2021 else 17


@dataclass
class SeasonInputs:
    """Everything a simulation needs about one season as of a point in time (team order = TEAMS)."""
    season: int
    home: np.ndarray  # regular-season games: team indices
    away: np.ndarray
    week: np.ndarray
    neutral: np.ndarray
    result: np.ndarray  # 1 home win, 0.5 tie, 0 away win; NaN = not played yet
    mean_margin: np.ndarray  # expected home margin for unplayed games (NaN for played)
    strength: np.ndarray  # team strength on the margin scale (playoff games), incl. persistent QB terms
    cov: np.ndarray  # covariance of the strength estimate (32 x 32)
    q_week: float  # per-team weekly drift variance of strength
    hfa: float  # home advantage, points
    base_week: int  # week whose games the current covariance describes (the next unplayed week)
    rest_penalty: np.ndarray = field(default_factory=lambda: np.zeros(len(TEAMS)))


class OutcomeTable:
    """P(home win) and P(tie) as a function of the expected margin, on a fine grid."""

    def __init__(self, dist: MarginDistribution, lo: float = -70.0, hi: float = 70.0, step: float = 0.05):
        self.lo, self.step = lo, step
        grid = np.arange(lo, hi + step / 2, step)
        pmf = dist.pmf(grid)
        from .margin_dist import K
        self.p_win = pmf[:, K > 0].sum(axis=1)
        self.p_tie = pmf[:, K == 0].sum(axis=1)

    def _ix(self, m: np.ndarray) -> np.ndarray:
        return np.clip(np.rint((m - self.lo) / self.step).astype(int), 0, len(self.p_win) - 1)

    def draw(self, m: np.ndarray, u: np.ndarray, ties: bool = True) -> np.ndarray:
        """1 / 0.5 / 0 outcomes. Without ties (playoffs) the tie mass is split evenly (overtime)."""
        i = self._ix(m)
        pw, pt = self.p_win[i], self.p_tie[i]
        if not ties:
            return (u < pw + pt / 2).astype(float)
        return np.where(u < pw, 1.0, np.where(u < pw + pt, 0.5, 0.0))


class Standings:
    """One simulated season's final standings and the NFL tiebreakers (through strength of schedule)."""

    def __init__(self, hp: np.ndarray, hw: np.ndarray, games: np.ndarray, rng: np.random.Generator):
        self.hp, self.hw, self.c, self.rng = hp, hw, games, rng  # points (win 1, tie 0.5), wins, games played
        g = games.sum(1)
        pts = hp.sum(1)
        self.pct = pts / g
        self.div = (hp * SAME_DIV).sum(1) / (games * SAME_DIV).sum(1)
        self.conf = (hp * SAME_CONF).sum(1) / (games * SAME_CONF).sum(1)
        won = hw @ g
        self.sov = np.divide(hw @ pts, won, out=np.zeros(len(g)), where=won > 0)
        self.sos = (games @ pts) / (games @ g)

    # -- tiebreaking steps: each returns one value per club (higher is better) or None if not applicable
    def _h2h(self, group: list[int]) -> np.ndarray | None:
        c = self.c[np.ix_(group, group)].sum(1)
        if (c == 0).any():
            return None
        return self.hp[np.ix_(group, group)].sum(1) / c

    def _h2h_sweep(self, group: list[int]) -> np.ndarray | None:
        sub_c, sub_w, sub_p = (m[np.ix_(group, group)] for m in (self.c, self.hw, self.hp))
        off = ~np.eye(len(group), dtype=bool)
        played_all = (sub_c > 0) | ~off
        swept = [bool(played_all[i].all() and (sub_w[i][off[i]] == sub_c[i][off[i]]).all()) for i in range(len(group))]
        lost_all = [bool(played_all[i].all() and (sub_p[i][off[i]] == 0).all()) for i in range(len(group))]
        if sum(swept) == 1:
            return np.array(swept, float)
        if sum(lost_all) == 1:
            return 1.0 - np.array(lost_all, float)
        return None

    def _common(self, group: list[int], minimum: int) -> np.ndarray | None:
        opp = [set(np.nonzero(self.c[t])[0]) for t in group]
        common = sorted(set.intersection(*opp) - set(group))
        if not common:
            return None
        n = self.c[np.ix_(group, common)].sum(1)
        if n.min() < max(minimum, 1):
            return None
        return self.hp[np.ix_(group, common)].sum(1) / n

    def _select(self, group: list[int], steps) -> int:
        """The top club of a tied group: apply steps in order; any elimination restarts at step 1 with
        the remaining clubs (the NFL's revert rule); a coin flip if nothing separates them."""
        group = list(group)
        while len(group) > 1:
            for step in steps(len(group)):
                v = step(group)
                if v is None:
                    continue
                keep = [t for t, x in zip(group, v) if x >= v.max() - EPS]
                if len(keep) < len(group):
                    group = keep
                    break
            else:
                return group[int(self.rng.integers(len(group)))]
        return group[0]

    def _division_steps(self, n: int):
        return (self._h2h, lambda g: self.div[g], lambda g: self._common(g, 0), lambda g: self.conf[g],
                lambda g: self.sov[g], lambda g: self.sos[g])

    def _wildcard_steps(self, n: int):
        first = (lambda g: self._h2h(g)) if n == 2 else self._h2h_sweep
        return (first, lambda g: self.conf[g], lambda g: self._common(g, 4), lambda g: self.sov[g],
                lambda g: self.sos[g])

    def _order(self, teams: list[int], pick) -> list[int]:
        remaining, out = list(teams), []
        while remaining:
            best = self.pct[remaining].max()
            tied = [t for t in remaining if self.pct[t] >= best - EPS]
            top = tied[0] if len(tied) == 1 else pick(tied)
            out.append(top)
            remaining.remove(top)
        return out

    def division_order(self, teams: list[int]) -> list[int]:
        return self._order(teams, lambda g: self._select(g, self._division_steps))

    def conference_seeds(self, conf: int, seeds: int) -> tuple[list[int], list[int]]:
        """(seeds 1..n as team indices, division winners). Division winners take seeds 1-4 in
        wild-card tiebreak order; wild cards fill the rest, keeping only each division's
        highest-ranked tied club when breaking ties."""
        div_rank: dict[int, int] = {}
        winners = []
        for d in sorted(set(DIV_OF[CONF_OF == conf])):
            order = self.division_order(list(np.nonzero(DIV_OF == d)[0]))
            winners.append(order[0])
            div_rank.update({t: k for k, t in enumerate(order)})

        def pick(tied: list[int]) -> int:
            best: dict[int, int] = {}
            for t in tied:
                d = DIV_OF[t]
                if d not in best or div_rank[t] < div_rank[best[d]]:
                    best[d] = t
            reduced = sorted(best.values())
            return reduced[0] if len(reduced) == 1 else self._select(reduced, self._wildcard_steps)

        top = self._order(winners, pick)
        rest = [t for t in np.nonzero(CONF_OF == conf)[0] if t not in winners]
        wild = []
        while len(wild) < seeds - len(winners):
            best = self.pct[rest].max()
            tied = [t for t in rest if self.pct[t] >= best - EPS]
            t = tied[0] if len(tied) == 1 else pick(tied)
            wild.append(t)
            rest.remove(t)
        return top + wild, winners


def head_to_head(n_sims: int, home: np.ndarray, away: np.ndarray, results: np.ndarray):
    """Points (win 1, tie 0.5) and wins of row team vs column team per sim, and games played."""
    n = len(TEAMS)
    hp = np.zeros((n_sims, n, n))
    hw = np.zeros((n_sims, n, n))
    games = np.zeros((n, n))
    for g in range(len(home)):
        h, a, r = home[g], away[g], results[:, g]
        hp[:, h, a] += r
        hp[:, a, h] += 1 - r
        hw[:, h, a] += r == 1
        hw[:, a, h] += r == 0
        games[h, a] += 1
        games[a, h] += 1
    return hp, hw, games


@dataclass
class SimulationResult:
    sims: int
    wins: np.ndarray  # (sims, 32) regular-season wins
    playoffs: np.ndarray  # (32,) counts
    division: np.ndarray
    seed1: np.ndarray
    conference: np.ndarray
    champion: np.ndarray

    def summary(self) -> dict[str, np.ndarray]:
        n = self.sims
        dist = np.stack([(self.wins == k).mean(axis=0) for k in range(18)], axis=1)
        return {"mean_wins": self.wins.mean(axis=0), "win_dist": dist, "playoff_p": self.playoffs / n,
                "division_p": self.division / n, "seed1_p": self.seed1 / n, "conf_p": self.conference / n,
                "sb_p": self.champion / n}


def simulate(inp: SeasonInputs, table: OutcomeTable, n_sims: int, rng: np.random.Generator,
             uncertainty: bool = True, chunk: int = 2000) -> SimulationResult:
    """Simulate the rest of the season `n_sims` times (in chunks to bound memory)."""
    out = SimulationResult(0, np.zeros((0, len(TEAMS))), *(np.zeros(len(TEAMS)) for _ in range(5)))
    done = 0
    while done < n_sims:
        k = min(chunk, n_sims - done)
        part = _simulate_chunk(inp, table, k, rng, uncertainty)
        out = SimulationResult(out.sims + part.sims, np.vstack([out.wins, part.wins]),
                               *(getattr(out, f) + getattr(part, f)
                                 for f in ("playoffs", "division", "seed1", "conference", "champion")))
        done += k
    return out


def _simulate_chunk(inp: SeasonInputs, table: OutcomeTable, n: int, rng: np.random.Generator,
                    uncertainty: bool) -> SimulationResult:
    nt = len(TEAMS)
    last_reg = last_regular_week(inp.season)
    horizon = last_reg + 5 - inp.base_week  # through the Super Bowl
    if uncertainty:
        chol = np.linalg.cholesky(inp.cov + 1e-9 * np.eye(nt))
        delta = rng.standard_normal((n, nt)) @ chol.T
        steps = rng.standard_normal((max(horizon, 1), n, nt)) * np.sqrt(inp.q_week)
        steps[0] = 0.0
        drift = np.cumsum(steps, axis=0) + delta[None]
    else:
        drift = np.zeros((max(horizon, 1), n, nt))

    def shift(week: int) -> np.ndarray:
        return drift[min(max(week - inp.base_week, 0), len(drift) - 1)]

    results = np.repeat(np.nan_to_num(inp.result, nan=0.0)[None, :], n, axis=0)
    unplayed = np.isnan(inp.result)
    for w in sorted(set(inp.week[unplayed])):
        idx = np.nonzero(unplayed & (inp.week == w))[0]
        d = shift(w)
        m = inp.mean_margin[idx][None, :] + d[:, inp.home[idx]] - d[:, inp.away[idx]]
        if w == last_reg and inp.rest_penalty.any():
            rest = _resting(inp, results, unplayed, w, rng) * inp.rest_penalty[None, :]
            m = m - rest[:, inp.home[idx]] + rest[:, inp.away[idx]]
        results[:, idx] = table.draw(m, rng.random(m.shape))

    hp, hw, games = head_to_head(n, inp.home, inp.away, results)
    wins = hw.sum(axis=2)
    seeds_n = n_seeds(inp.season)
    seeds = np.zeros((n, 2, seeds_n), int)
    playoffs, division, seed1 = (np.zeros(nt) for _ in range(3))
    for s in range(n):
        st = Standings(hp[s], hw[s], games, rng)
        for conf in (0, 1):
            sd, winners = st.conference_seeds(conf, seeds_n)
            seeds[s, conf] = sd
            playoffs[sd] += 1
            division[winners] += 1
            seed1[sd[0]] += 1
    conference, champion = _bracket(inp, table, seeds, shift, last_reg, rng)
    return SimulationResult(n, wins, playoffs, division, seed1, conference, champion)


def _resting(inp: SeasonInputs, results: np.ndarray, unplayed: np.ndarray, week: int,
             rng: np.random.Generator) -> np.ndarray:
    """(sims, 32) 1 where a team that has clinched its conference's #1 seed before the final week
    rests its starting QB (with REST_PROBABILITY). Clinched = more win points than any conference
    rival could reach."""
    before = ~(unplayed & (inp.week >= week))
    n, nt = results.shape[0], len(TEAMS)
    pts = np.zeros((n, nt))
    left = np.zeros(nt)
    for g in range(len(inp.home)):
        if before[g]:
            pts[:, inp.home[g]] += results[:, g]
            pts[:, inp.away[g]] += 1 - results[:, g]
        else:
            left[inp.home[g]] += 1
            left[inp.away[g]] += 1
    reach = pts + left[None, :]
    clinched = np.zeros((n, nt), bool)
    for conf in (0, 1):
        idx = np.nonzero(CONF_OF == conf)[0]
        for t in idx:
            rivals = idx[idx != t]
            clinched[:, t] = pts[:, t] > reach[:, rivals].max(axis=1) + EPS
    return (clinched & (rng.random((n, nt)) < REST_PROBABILITY)).astype(float)


def _bracket(inp: SeasonInputs, table: OutcomeTable, seeds: np.ndarray, shift, last_reg: int,
             rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray]:
    """Play the bracket: higher seed hosts; #1 (and #2 before 2020) get byes; the divisional round
    re-seeds (the top seed hosts the lowest remaining); the Super Bowl is neutral."""
    n, nt = seeds.shape[0], len(TEAMS)
    rows = np.arange(n)
    conference, champion = np.zeros(nt), np.zeros(nt)

    def play(home_t: np.ndarray, away_t: np.ndarray, week: int, neutral: bool = False) -> np.ndarray:
        d = shift(week)
        m = inp.strength[home_t] - inp.strength[away_t] + d[rows, home_t] - d[rows, away_t] + (0 if neutral else inp.hfa)
        return table.draw(m, rng.random(n), ties=False) == 1  # True = home (higher seed) wins

    finalists = []
    for conf in (0, 1):
        sd = seeds[:, conf]  # (n, k) team indices by seed (column 0 = #1)
        k = sd.shape[1]
        byes = 1 if k == 7 else 2
        alive = [np.full(n, s) for s in range(byes)]  # seed positions still alive
        for hi in range(byes, (k + byes) // 2):
            lo = k - 1 - (hi - byes)
            win = play(sd[rows, hi], sd[rows, lo], last_reg + 1)
            alive.append(np.where(win, hi, lo))
        a = np.sort(np.stack(alive, axis=1), axis=1)  # 4 seed positions per sim, best first
        w1 = play(sd[rows, a[:, 0]], sd[rows, a[:, 3]], last_reg + 2)
        w2 = play(sd[rows, a[:, 1]], sd[rows, a[:, 2]], last_reg + 2)
        s1, s2 = np.where(w1, a[:, 0], a[:, 3]), np.where(w2, a[:, 1], a[:, 2])
        top, bottom = np.minimum(s1, s2), np.maximum(s1, s2)
        wc = play(sd[rows, top], sd[rows, bottom], last_reg + 3)
        champ = sd[rows, np.where(wc, top, bottom)]
        np.add.at(conference, champ, 1)
        finalists.append(champ)
    afc_wins = play(finalists[0], finalists[1], last_reg + 4, neutral=True)
    np.add.at(champion, np.where(afc_wins, finalists[0], finalists[1]), 1)
    return conference, champion
