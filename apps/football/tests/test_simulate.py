"""Season simulation (MS-034): tiebreakers reproduce the real playoff fields, the simulator's
probabilities are coherent, and the rest/bracket mechanics behave."""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from marketscope_football.ratings.margin_dist import MarginDistribution
from marketscope_football.ratings.simulate import (
    CONF_OF, DIV_OF, IX, TEAMS, OutcomeTable, SeasonInputs, Standings, head_to_head, n_seeds, simulate,
)

# nflverse results (CC-BY 4.0), franchise codes; regular season plus playoff games.
RESULTS = pd.read_csv(Path(__file__).parent / "fixtures" / "results_2016_2024.csv")
DIST = MarginDistribution(13.0, [1.0] * 22)


def standings_for(season: int, rng=None) -> Standings:
    g = RESULTS[(RESULTS.season == season) & (RESULTS.game_type == "REG")]
    home = g.home.map(IX).to_numpy()
    away = g.away.map(IX).to_numpy()
    margin = (g.home_score - g.away_score).to_numpy()
    res = np.where(margin > 0, 1.0, np.where(margin < 0, 0.0, 0.5))[None, :]
    hp, hw, games = head_to_head(1, home, away, res)
    return Standings(hp[0], hw[0], games, rng or np.random.default_rng(0))


@pytest.mark.parametrize("season", range(2016, 2025))
def test_seeding_reproduces_the_actual_playoff_field(season):
    st = standings_for(season)
    po = RESULTS[RESULTS.season == season]
    wc = po[po.game_type == "WC"]
    div = po[po.game_type == "DIV"]
    for conf in (0, 1):
        seeds, winners = st.conference_seeds(conf, n_seeds(season))
        names = [TEAMS[t] for t in seeds]
        k = len(names)
        byes = 1 if k == 7 else 2
        expected_wc = {(names[hi], names[k - 1 - (hi - byes)]) for hi in range(byes, (k + byes) // 2)}
        conf_teams = {t for t in TEAMS if CONF_OF[IX[t]] == conf}
        actual_wc = {(h, a) for h, a in zip(wc.home, wc.away) if h in conf_teams}
        assert expected_wc == actual_wc, (season, conf, names)
        in_div = set(div.home) | set(div.away)
        in_wc = set(wc.home) | set(wc.away)
        assert set(names[:byes]) == (in_div - in_wc) & conf_teams
        assert len(winners) == 4 and len({DIV_OF[t] for t in winners}) == 4


def test_division_tiebreak_head_to_head_and_coin_flip():
    # Two teams, split head-to-head, nothing else to separate them -> a coin flip, reproducible by seed.
    n = len(TEAMS)
    hp = np.zeros((n, n))
    hw = np.zeros((n, n))
    games = np.zeros((n, n))
    a, b = IX["KC"], IX["DEN"]
    games[a, b] = games[b, a] = 2
    hp[a, b] = hp[b, a] = 1
    hw[a, b] = hw[b, a] = 1
    with np.errstate(invalid="ignore"):  # the other 30 teams have no games here
        picks = {Standings(hp, hw, games, np.random.default_rng(s))._select([a, b], lambda k: ()) for s in range(20)}
    assert picks == {a, b}


def test_wildcard_sweep_rule_needs_one_club_beating_all_others():
    st = standings_for(2016)
    group = [IX["MIA"], IX["DEN"], IX["BAL"]]
    v = st._h2h_sweep(group)
    assert v is None or set(v) <= {0.0, 1.0}


def _inputs(season=2024, played_through=0, strength=None):
    g = RESULTS[(RESULTS.season == season) & (RESULTS.game_type == "REG")]
    margin = (g.home_score - g.away_score).to_numpy()
    res = np.where(margin > 0, 1.0, np.where(margin < 0, 0.0, 0.5))
    week = g.week.to_numpy()
    res = np.where(week <= played_through, res, np.nan)
    s = np.zeros(len(TEAMS)) if strength is None else strength
    home, away = g.home.map(IX).to_numpy(), g.away.map(IX).to_numpy()
    mean = np.where(np.isnan(res), s[home] - s[away] + 1.5, np.nan)
    return SeasonInputs(season, home, away, week, g.neutral.to_numpy(), res, mean, s, np.eye(len(TEAMS)) * 4.0,
                        0.05, 1.5, played_through + 1)


def test_simulated_probabilities_are_coherent():
    rng = np.random.default_rng(7)
    strength = np.linspace(-6, 6, len(TEAMS))
    r = simulate(_inputs(strength=strength), OutcomeTable(DIST), 400, rng).summary()
    assert r["playoff_p"].sum() == pytest.approx(14.0)
    assert r["division_p"].sum() == pytest.approx(8.0)
    assert r["seed1_p"].sum() == pytest.approx(2.0)
    assert r["conf_p"].sum() == pytest.approx(2.0)
    assert r["sb_p"].sum() == pytest.approx(1.0)
    assert (r["division_p"] <= r["playoff_p"] + 1e-12).all() and (r["seed1_p"] <= r["division_p"] + 1e-12).all()
    assert np.allclose(r["win_dist"].sum(axis=1), 1.0)
    assert 255 < r["mean_wins"].sum() <= 272  # one win per game, minus ties
    afc = CONF_OF == 0
    assert r["playoff_p"][afc][-1] > r["playoff_p"][afc][0]  # stronger teams make it more often


def test_a_finished_season_has_certain_seeds_and_the_same_field():
    r = simulate(_inputs(played_through=18), OutcomeTable(DIST), 50, np.random.default_rng(1)).summary()
    st = standings_for(2024)
    for conf in (0, 1):
        seeds, _ = st.conference_seeds(conf, 7)
        assert all(r["playoff_p"][t] == 1.0 for t in seeds)
        assert r["seed1_p"][seeds[0]] == 1.0
    assert set(np.unique(r["playoff_p"])) <= {0.0, 1.0}


def test_rating_uncertainty_widens_the_win_distribution():
    strength = np.linspace(-6, 6, len(TEAMS))
    t = OutcomeTable(DIST)
    sure = simulate(_inputs(strength=strength), t, 600, np.random.default_rng(3), uncertainty=False)
    unsure = simulate(_inputs(strength=strength), t, 600, np.random.default_rng(3))
    assert unsure.wins.std(axis=0).mean() > sure.wins.std(axis=0).mean()
