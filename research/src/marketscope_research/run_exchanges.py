"""MS-051 exchanges, price-aware with fees (research/PREREGISTRATION.md Addendum K). Read-only.

    STUDY_DATABASE_URL=... .venv/bin/python -m marketscope_research.run_exchanges --phase discovery \
        --out reports/exchanges-discovery.md

Analysis of closing-line value at Pinnacle's no-vig close, after exchange fees. Not betting advice.
"""

from __future__ import annotations

import argparse
import os
import subprocess
from datetime import datetime, timezone

import pandas as pd

from . import exchanges as ex
from . import market_ml as ml
from . import openers_totals as ot
from . import sharp_market as sm
from .data import _frame, connect
from .run_football_studies import table

NAMES = {"novig": "Novig", "prophetx": "ProphetX", "kalshi": "Kalshi"}


def load(conn, start: pd.Timestamp, end: pd.Timestamp):
    games = _frame(conn, """
        SELECT e.id::text AS event_id, e.commence_time_utc AS kickoff
        FROM nfl_games g JOIN events e ON e.id = g.event_id
        WHERE g.season = 2026 AND g.game_type = 'REG' AND g.home_score IS NOT NULL
          AND e.commence_time_utc >= %s AND e.commence_time_utc < %s""", (start, end))
    games["kickoff"] = pd.to_datetime(games["kickoff"], utc=True)
    moves = _frame(conn, """
        SELECT event_id::text, bookmaker_key, market_type, changed_at, point::float8 AS point, price1, price2,
               limit1::float8 AS limit1, limit2::float8 AS limit2
        FROM line_moves WHERE market_type IN ('spreads', 'totals') AND event_id = ANY(%s::uuid[])
          AND bookmaker_key IN ('pinnacle', 'novig', 'prophetx', 'kalshi')""", (list(games["event_id"]),))
    moves["changed_at"] = pd.to_datetime(moves["changed_at"], utc=True)
    history = _frame(conn, """
        SELECT nflverse_close_home_spread::float8 AS home_line, nflverse_close_total::float8 AS total,
               (home_score - away_score)::float8 AS margin, (home_score + away_score)::float8 AS points
        FROM nfl_games WHERE season BETWEEN 2016 AND 2025 AND game_type = 'REG' AND home_score IS NOT NULL
          AND nflverse_close_home_spread IS NOT NULL AND nflverse_close_total IS NOT NULL""")
    return games, moves, history


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
    st_tables, tt_tables = ml.margin_tables(history), ot.total_tables(history)

    cases, horizon = [], []
    tls = {}
    for market in ("spreads", "totals"):
        m = moves[moves["market_type"] == market]
        tl = sm.timelines(m[m["event_id"].isin(m.loc[m["bookmaker_key"] == "pinnacle", "event_id"])])
        tls[market] = tl
        c = ex.stale_exchange_cases(tl, kicks, market)
        c["value"] = ex.add_values(c, tl, kicks, st_tables, tt_tables, "retail")
        c["value_px1"] = ex.add_values(c, tl, kicks, st_tables, tt_tables, "retail", prophetx_fee=0.01)
        c1000 = ex.stale_exchange_cases(tl, kicks, market, min_size=1000.0)
        c1000["value"] = ex.add_values(c1000, tl, kicks, st_tables, tt_tables, "retail")
        cases.append(c.assign(floor=100))
        cases.append(c1000.assign(floor=1000))
        hz = ex.horizon_exchange_positions(tl, kicks, market)
        hz["value"] = ex.add_values(hz, tl, kicks, st_tables, tt_tables, "exchange")
        horizon.append(hz)
    allc = pd.concat(cases, ignore_index=True).dropna(subset=["value"])
    k1 = allc[allc["floor"] == 100]
    k1_1000 = allc[allc["floor"] == 1000]
    k2 = pd.concat(horizon, ignore_index=True).dropna(subset=["value"])

    def boot(d, col="value"):
        return sm.ratio_bootstrap(d.assign(v=d[col]), "v") if len(d) else None

    def pct(e):
        return "–" if e is None else f"{100 * e.value:+.1f}% ({100 * e.low:+.1f} to {100 * e.high:+.1f})"

    def verdict(e, claim):
        if e is None:
            return "inconclusive (no cases)"
        tag = " (discovery result; confirmation on weeks 7–14 decides)" if args.phase == "discovery" else ""
        return f"**{claim}**{tag}" if e.low > 0 else ("**the opposite**" + tag if e.high < 0 else
                                                       "not distinguishable: no claim")

    e1, e2 = boot(k1), boot(k2)
    nov, nov1000 = k1[k1["retail"] == "novig"], k1_1000[k1_1000["retail"] == "novig"]
    by_x = [[NAMES[x], len(d), f"{d['stale_min'].median():.0f} min", pct(boot(d))] for x, d in k1.groupby("retail")]
    by_m = [[m, len(d), f"{d['clv'].mean():+.2f}", pct(boot(d))] for m, d in k1.groupby("market")]
    k2_x = [[NAMES[x], len(d), pct(boot(d))] for x, d in k2.groupby("exchange")]
    k2_h = [[h, len(d), pct(boot(d))] for h, d in k2.groupby("h", sort=False)]

    commit = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True).strip()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    rows_by_x = moves[moves["bookmaker_key"] != "pinnacle"].groupby("bookmaker_key").size().to_dict()
    parts = [
        f"# Exchanges, price-aware with fees: {args.phase} (MS-051)", "",
        f"_Generated {now} · commit `{commit}` · reproduce with "
        f"`research/src/marketscope_research/run_exchanges.py --phase {args.phase}`._", "",
        "Design pre-registered in `research/PREREGISTRATION.md` (Addendum K, committed before any exchange import or "
        "study code). Value is expected profit per unit at Pinnacle's no-vig close after fees (Novig none; ProphetX 2% "
        "of net winnings; Kalshi 0.07·p·(1−p) per contract). Size floor: 100 at the top of book. Intervals resample "
        "games (5,000 draws, seed 2026). **Analysis, not betting advice.**", "",
        f"**Sample:** {len(games)} games. Exchange rows: "
        + ", ".join(f"{NAMES.get(k, k)} {v:,}" for k, v in rows_by_x.items()) + ".", "",
        "## K1: stale exchange prices", "",
        f"{len(k1)} cases: an exchange still offering Pinnacle's old line 60 s after it moved, on the side Pinnacle "
        f"moved toward, at −125 or better with size ≥ 100. Mean value after fees: {pct(e1)}. **Primary result:** "
        f"{verdict(e1, 'stale exchange prices carry positive value after fees')}.", "",
        table(by_x, ["Exchange", "Cases", "Median time the old line stayed up", "Value"]), "",
        table(by_m, ["Market", "Cases", "Points CLV", "Value"]), "",
        f"Exploratory: with a size floor of 1,000: {len(k1_1000)} cases, {pct(boot(k1_1000))}. "
        f"With ProphetX at 1%: {pct(boot(k1, 'value_px1'))}.", "",
        "### K1n: Novig only (Addendum L; registered after discovery, tested on confirmation)", "",
        (f"Novig cases: {len(nov)}, mean value {pct(boot(nov))}; with a size floor of 1,000: {len(nov1000)}, "
         f"{pct(boot(nov1000))}. "
         + ("**Primary (confirmation):** " + verdict(boot(nov), "stale Novig prices carry positive value").replace(
             " (discovery result; confirmation on weeks 7–14 decides)", "")
            if args.phase == "confirmation" else
            "Discovery numbers motivated this hypothesis, so they are not evidence for it.")), "",
        "## K2: exchange prices better than Pinnacle's at fixed horizons (secondary)", "",
        f"{len(k2)} positions. Mean value after fees: {pct(e2)}. Secondary: "
        f"{verdict(e2, 'better-than-Pinnacle exchange prices carry positive value')}.", "",
        table(k2_x, ["Exchange", "Positions", "Value"]), "",
        table(k2_h, ["Hours before kickoff", "Positions", "Value"]), "",
        "## What this can't see", "",
        "Depth beyond the top of book; whether an order would have filled before the price moved; exchange account "
        "limits; Kalshi fees rounded to cents.", "",
    ]
    with open(args.out, "w") as f:
        f.write("\n".join(parts))
    print("\n".join(p for p in parts if "result" in p.lower() and "**" in p or p.startswith("**Sample")
                    or p.startswith("Exploratory")))


if __name__ == "__main__":
    main()
