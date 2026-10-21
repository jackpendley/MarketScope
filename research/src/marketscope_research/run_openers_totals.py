"""MS-050 openers and totals, price-aware (research/PREREGISTRATION.md Addendum J). Read-only.

    STUDY_DATABASE_URL=... .venv/bin/python -m marketscope_research.run_openers_totals --phase discovery \
        --out reports/openers-totals-discovery.md

Analysis of closing-line value at Pinnacle's no-vig close, not betting advice.
"""

from __future__ import annotations

import argparse
import os
import subprocess
from datetime import datetime, timezone

import pandas as pd

from . import market_ml as ml
from . import openers_totals as ot
from . import sharp_market as sm
from .data import _frame, connect
from .run_football_studies import ci, table

NAMES = {"draftkings": "DraftKings", "fanduel": "FanDuel", "williamhill_us": "Caesars", "hardrockbet": "Hard Rock"}


def load(conn, start: pd.Timestamp, end: pd.Timestamp):
    games = _frame(conn, """
        SELECT e.id::text AS event_id, e.commence_time_utc AS kickoff
        FROM nfl_games g JOIN events e ON e.id = g.event_id
        WHERE g.season = 2026 AND g.game_type = 'REG' AND g.home_score IS NOT NULL
          AND e.commence_time_utc >= %s AND e.commence_time_utc < %s""", (start, end))
    games["kickoff"] = pd.to_datetime(games["kickoff"], utc=True)
    moves = _frame(conn, """
        SELECT event_id::text, bookmaker_key, market_type, changed_at, point::float8 AS point, price1, price2,
               limit1::float8 AS limit1
        FROM line_moves WHERE market_type IN ('spreads', 'totals') AND event_id = ANY(%s::uuid[])""",
                   (list(games["event_id"]),))
    moves["changed_at"] = pd.to_datetime(moves["changed_at"], utc=True)
    history = _frame(conn, """
        SELECT nflverse_close_home_spread::float8 AS home_line, nflverse_close_total::float8 AS total,
               (home_score - away_score)::float8 AS margin, (home_score + away_score)::float8 AS points
        FROM nfl_games WHERE season BETWEEN 2016 AND 2025 AND game_type = 'REG' AND home_score IS NOT NULL
          AND nflverse_close_home_spread IS NOT NULL AND nflverse_close_total IS NOT NULL""")
    return games, moves, history


def with_pinnacle(moves: pd.DataFrame) -> dict:
    return sm.timelines(moves[moves["event_id"].isin(moves.loc[moves["bookmaker_key"] == "pinnacle", "event_id"])])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", choices=["discovery", "confirmation"], default="discovery")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    dsn = os.environ.get("STUDY_DATABASE_URL")
    if not dsn:
        raise SystemExit("Set STUDY_DATABASE_URL (read-only use).")
    start, end = ((pd.Timestamp("2026-09-01", tz="UTC"), sm.DISCOVERY_END) if args.phase == "discovery"
                  else (sm.DISCOVERY_END, sm.CONFIRMATION_END))
    with connect(dsn) as conn:
        games, moves, history = load(conn, start, end)
    kicks = games.set_index("event_id")["kickoff"]
    spread_tables = ml.margin_tables(history)
    totals_tables = ot.total_tables(history)
    tl_s = with_pinnacle(moves[moves["market_type"] == "spreads"])
    tl_t = with_pinnacle(moves[moves["market_type"] == "totals"])

    # J1 openers
    op = ot.opener_positions(tl_s, kicks, spread_tables)
    e1 = sm.ratio_bootstrap(op.assign(v=op["value"]), "v") if len(op) else None
    # J2 stale totals
    closes_t = {e: x for e, b in tl_t.items() if (x := sm.close_line(b.get("pinnacle"), kicks[e])) is not None}
    st = sm.s2_events(tl_t, kicks, closes_t, market="totals")
    st["value"] = ot.stale_total_values(st, tl_t, kicks, totals_tables)
    st = st.dropna(subset=["value"])
    e2 = sm.ratio_bootstrap(st.assign(v=st["value"]), "v") if len(st) else None
    # J3 totals at horizons
    ht = ot.horizon_totals(tl_t, kicks, totals_tables)
    e3 = sm.ratio_bootstrap(ht.assign(v=ht["value"]), "v") if len(ht) else None

    def pct(e):
        return "–" if e is None else f"{100 * e.value:+.1f}% ({100 * e.low:+.1f} to {100 * e.high:+.1f})"

    def mean_pct(d):
        return pct(sm.ratio_bootstrap(d.assign(v=d["value"]), "v")) if len(d) else "–"

    def verdict(e, claim):
        if e is None:
            return "inconclusive (no cases)"
        tag = " (discovery result; confirmation on weeks 7–14 decides)" if args.phase == "discovery" else ""
        return f"**{claim}**{tag}" if e.low > 0 else ("**the opposite**" + tag if e.high < 0 else
                                                       "not distinguishable: no claim")

    op_books = [[NAMES[b], len(d), mean_pct(d)] for b, d in op.groupby("book")]
    op_hours = [[label, len(d), mean_pct(d)] for label, d in (
        ("More than 7 days before kickoff", op[op["hours_out"] > 168]),
        ("2–7 days", op[(op["hours_out"] > 48) & (op["hours_out"] <= 168)]),
        ("Within 2 days", op[op["hours_out"] <= 48]))]
    st_price = [[label, len(d), f"{d['clv'].mean():+.2f}" if len(d) else "–", mean_pct(d)] for label, d in (
        ("All stale totals", st), ("At −110 or better", st[st["price"] >= -110]),
        ("At −111 to −125", st[st["price"] < -110]))]
    ht_rows = [[h, len(d), mean_pct(d)] for h, d in ht.groupby("h", sort=False)]
    ht_sides = [[s, len(d), mean_pct(d)] for s, d in ht.groupby("side")]

    commit = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True).strip()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    parts = [
        f"# Openers and totals, price-aware: {args.phase} (MS-050)", "",
        f"_Generated {now} · commit `{commit}` · reproduce with "
        f"`research/src/marketscope_research/run_openers_totals.py --phase {args.phase}`._", "",
        "Design pre-registered in `research/PREREGISTRATION.md` (Addendum J, committed before this code). Value is "
        "expected profit per unit at Pinnacle's no-vig close, converted between lines with empirical 2016–25 margin "
        "and total-points distributions. Intervals resample games (5,000 draws, seed 2026). **Analysis, not betting "
        "advice.**", "",
        f"**Sample:** {len(games)} games; {len(tl_s)} with Pinnacle spreads, {len(tl_t)} with Pinnacle totals.", "",
        "## J1: retail openers better than Pinnacle's line at the time", "",
        f"{len(op)} positions. Mean value: {pct(e1)}. **Primary result:** "
        f"{verdict(e1, 'retail openers that beat Pinnacle carry positive value')}.", "",
        table(op_books, ["Retail book", "Positions", "Value"]), "",
        table(op_hours, ["Opened", "Positions", "Value"]), "",
        "## J2: stale totals", "",
        f"{len(st)} cases. Mean value: {pct(e2)}. **Primary result:** "
        f"{verdict(e2, 'stale retail totals carry positive value')}.", "",
        table(st_price, ["Cases", "Count", "Points CLV", "Value"]), "",
        "## J3: totals at fixed horizons (secondary)", "",
        f"{len(ht)} retail totals better than Pinnacle's for the side, at −125 or better. Mean value: {pct(e3)}. "
        f"Secondary: {verdict(e3, 'better-than-Pinnacle retail totals carry positive value')}.", "",
        table(ht_rows, ["Hours before kickoff", "Positions", "Value"]), "",
        table(ht_sides, ["Side", "Positions", "Value"]), "",
        "## What this can't see", "",
        "Openers more than 14 days before kickoff appear as the line in effect 14 days out; exchange totals; who bet.",
        "",
    ]
    with open(args.out, "w") as f:
        f.write("\n".join(parts))
    print("\n".join(p for p in parts if "result" in p.lower() and "**" in p or p.startswith("**Sample")))


if __name__ == "__main__":
    main()
