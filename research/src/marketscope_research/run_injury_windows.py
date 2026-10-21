"""MS-047 injury-report windows (research/PREREGISTRATION.md Addendum I). Read-only.

    STUDY_DATABASE_URL=... .venv/bin/python -m marketscope_research.run_injury_windows --phase discovery \
        --out reports/injury-windows-discovery.md

Analysis of line movement and closing-line value, not betting advice.
"""

from __future__ import annotations

import argparse
import os
import subprocess
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from . import football_studies as fs
from . import injury_windows as iw
from . import market_ml as ml
from . import sharp_market as sm
from .data import _frame, connect
from .run_football_studies import ci, table

PHASES = {"discovery": (2, sm.DISCOVERY_END), "confirmation": (7, sm.CONFIRMATION_END)}


def load(conn, first_week: int, end: pd.Timestamp):
    games = _frame(conn, """
        SELECT e.id::text AS event_id, e.commence_time_utc AS kickoff, g.season, g.week,
               ht.franchise AS home, aw.franchise AS away
        FROM nfl_games g JOIN events e ON e.id = g.event_id
        JOIN nfl_teams ht ON ht.abbr = g.home_team JOIN nfl_teams aw ON aw.abbr = g.away_team
        WHERE g.season = 2026 AND g.game_type = 'REG' AND g.home_score IS NOT NULL AND g.week >= %s
          AND e.commence_time_utc < %s""", (first_week, end))
    games["kickoff"] = pd.to_datetime(games["kickoff"], utc=True)
    final = _frame(conn, """
        SELECT DISTINCT ON (season, week, team, gsis_id) season, week,
               (SELECT franchise FROM nfl_teams WHERE abbr = team) AS team, gsis_id, position, report_status
        FROM nfl_injury_reports WHERE season = 2026 AND game_type = 'REG' AND gsis_id IS NOT NULL
        ORDER BY season, week, team, gsis_id, id DESC""")
    snaps = _frame(conn, """
        SELECT season, week, (SELECT franchise FROM nfl_teams WHERE abbr = team) AS team, gsis_id,
               offense_pct, defense_pct
        FROM nfl_player_game_snaps WHERE season = 2026 AND gsis_id IS NOT NULL""")
    moves = _frame(conn, """
        SELECT event_id::text, bookmaker_key, changed_at, point::float8 AS point, price1, price2,
               limit1::float8 AS limit1
        FROM line_moves WHERE market_type = 'spreads' AND event_id = ANY(%s::uuid[])""",
                   (list(games["event_id"]),))
    moves["changed_at"] = pd.to_datetime(moves["changed_at"], utc=True)
    history = _frame(conn, """
        SELECT nflverse_close_home_spread::float8 AS home_line, (home_score - away_score)::float8 AS margin
        FROM nfl_games WHERE season BETWEEN 2016 AND 2025 AND game_type = 'REG' AND home_score IS NOT NULL
          AND nflverse_close_home_spread IS NOT NULL""")
    return games, final, snaps, moves, history


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", choices=PHASES, default="discovery")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    dsn = os.environ.get("STUDY_DATABASE_URL")
    if not dsn:
        raise SystemExit("Set STUDY_DATABASE_URL (read-only use).")
    first_week, end = PHASES[args.phase]
    with connect(dsn) as conn:
        games, final, snaps, moves, history = load(conn, first_week, end)
    if args.phase == "confirmation":
        games = games[games["kickoff"] >= sm.DISCOVERY_END]

    events = fs.injury_events(final, snaps)
    events = events[events["week"].isin(set(games["week"]))]
    net = iw.net_events(games, events)
    tl = sm.timelines(moves[moves["event_id"].isin(moves.loc[moves["bookmaker_key"] == "pinnacle", "event_id"])])

    # I1
    wm = iw.window_moves(tl, games, net)
    ev_in = int(events.merge(games[games["event_id"].isin(wm["event_id"])], left_on=["season", "week", "team"],
                             right_on=["season", "week", "home"]).shape[0]
                + events.merge(games[games["event_id"].isin(wm["event_id"])], left_on=["season", "week", "team"],
                               right_on=["season", "week", "away"]).shape[0])
    gate1 = ev_in >= iw.I1_MIN_EVENTS
    e1 = iw.slope_ci(wm, "window_move", "n") if len(wm) > 2 else None
    news = wm[wm["n"] != 0].dropna(subset=["full_move"])
    oriented = news.assign(w=news["window_move"] * np.sign(news["n"]), f=news["full_move"] * np.sign(news["n"]))
    share = float(oriented["w"].sum() / oriented["f"].sum()) if len(oriented) and oriented["f"].sum() else np.nan

    # I2
    kicks = games.set_index("event_id")["kickoff"]
    tl_g = {e: b for e, b in tl.items() if e in set(games["event_id"])}
    closes = {e: x for e, b in tl_g.items() if (x := sm.close_line(b.get("pinnacle"), kicks[e])) is not None}
    cases = sm.s2_events(tl_g, kicks, closes)
    cases["value"] = ml.price_aware_values(cases, tl_g, kicks, ml.margin_tables(history))
    cases["news"] = iw.tag_news_window(cases, games, net)
    nw = cases[cases["news"]]
    gate2 = len(nw) >= iw.I2_MIN_CASES
    e2 = sm.ratio_bootstrap(nw.assign(v=nw["value"]), "v") if len(nw) else None
    e2d = iw.diff_bootstrap(cases, "value", "news") if len(nw) and (~cases["news"]).any() else None

    def verdict(e, gate, claim):
        if not gate:
            return "inconclusive (gate not met)"
        if e is None:
            return "inconclusive (no cases)"
        tag = " (discovery result; confirmation on weeks 7–14 decides)" if args.phase == "discovery" else ""
        return f"**{claim}**{tag}" if e.low > 0 else ("**the opposite**" + tag if e.high < 0 else
                                                       "not distinguishable: no claim")

    def pct(e):
        return "–" if e is None else f"{100 * e.value:+.1f}% ({100 * e.low:+.1f} to {100 * e.high:+.1f})"

    by_n = [[n, len(d), f"{d['window_move'].mean():+.2f}"] for n, d in wm.groupby("n")]
    stale = [[label, len(d), f"{d['stale_min'].median():.0f} min" if len(d) else "–",
              f"{100 * d['value'].mean():+.1f}%" if len(d) else "–"]
             for label, d in (("News-window cases", nw), ("All other cases", cases[~cases["news"]]))]
    commit = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True).strip()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    parts = [
        f"# Injury-report windows and the line: {args.phase} (MS-047)", "",
        f"_Generated {now} · commit `{commit}` · reproduce with "
        f"`research/src/marketscope_research/run_injury_windows.py --phase {args.phase}`._", "",
        "Design pre-registered in `research/PREREGISTRATION.md` (Addendum I, committed before this code). The window "
        "runs from 4 hours before to 2 hours after the 4 pm ET game-status deadline (the day before Thursday games, "
        "two days before others). Events: starters newly listed Out (R2w's definition). Intervals resample games "
        "(5,000 draws, seed 2026). Value is closing-line value at Pinnacle's no-vig close. **Analysis, not betting "
        "advice.**", "",
        f"**Sample:** {len(games)} games from week {first_week}; {len(wm)} with Pinnacle on the board at both window "
        f"edges; {int((wm['n'] != 0).sum())} with net news (N ≠ 0); {ev_in} events in qualifying games.", "",
        "## I1: does Pinnacle price the news inside the window?", "",
        f"Slope of Pinnacle's window move (margin points, toward the healthier side) on N: {ci(e1)} points per net "
        f"event. Gate: {iw.I1_MIN_EVENTS} events ({'met' if gate1 else 'not met'}). **Primary result:** "
        f"{verdict(e1, gate1, 'Pinnacle moves on the news inside the window')}.", "",
        table(by_n, ["N (away − home events)", "Games", "Mean window move (points)"]), "",
        f"Exploratory: in games with N ≠ 0, the window holds {'–' if np.isnan(share) else f'{share:.0%}'} of the "
        "net move from 6 days out to the close, oriented by the news.", "",
        "## I2: are retail books slower on injury news?", "",
        f"News-window cases: {len(nw)} stale retail numbers after a Pinnacle move in the direction of the news, inside "
        f"the window. Gate: {iw.I2_MIN_CASES} ({'met' if gate2 else 'not met'}).", "",
        f"Mean price-aware value: {pct(e2)}. **Primary result:** "
        f"{verdict(e2, gate2, 'retail numbers lagging injury news carry positive value')}.", "",
        f"Difference from all other stale numbers: {pct(e2d)}. Secondary: "
        f"{verdict(e2d, gate2, 'news-window numbers are worth more than other stale numbers')}.", "",
        table(stale, ["Cases", "Count", "Median time the old number stayed up", "Mean value per unit"]), "",
        "## What this can't see", "",
        "The minute each designation became public (only the deadline is known); practice-report news earlier in the "
        "week; Questionable and Doubtful designations.", "",
    ]
    with open(args.out, "w") as f:
        f.write("\n".join(parts))
    print("\n".join(p for p in parts if "Primary result" in p or p.startswith("**Sample") or "Secondary" in p))


if __name__ == "__main__":
    main()
