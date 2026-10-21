"""MS-054 cross-market value (research/PREREGISTRATION.md Addendum P). Reads the research lake and the
database read-only.

    STUDY_DATABASE_URL=... .venv/bin/python -m marketscope_research.run_cross_market --phase discovery \
        --out reports/cross-market-discovery.md

Analysis of value at the sharp-consensus close; not betting advice.
"""

from __future__ import annotations

import argparse
import os
import subprocess
from datetime import datetime, timezone

import pandas as pd

from . import cross_market as cm
from . import fair_value as fv
from . import sharp_market as sm
from .data import _frame, connect
from .lake import store
from .run_football_studies import table

NAMES = {"draftkings": "DraftKings", "fanduel": "FanDuel", "caesars": "Caesars", "hardrockbet": "Hard Rock"}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", choices=["discovery", "confirmation"], default="discovery")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    dsn = os.environ.get("STUDY_DATABASE_URL")
    if not dsn:
        raise SystemExit("Set STUDY_DATABASE_URL (read-only use).")
    with connect(dsn) as conn:
        history = _frame(conn, """
            SELECT season, nflverse_close_home_spread::float8 AS home_line, nflverse_close_total::float8 AS total,
                   (home_score - away_score)::float8 AS margin, (home_score + away_score)::float8 AS points
            FROM nfl_games WHERE season BETWEEN 2016 AND 2025 AND home_score IS NOT NULL
              AND nflverse_close_home_spread IS NOT NULL AND nflverse_close_total IS NOT NULL""")
    engine = fv.load_engine(history)
    con = store.connect()
    manifest = con.execute("SELECT fixture_id, kickoff FROM manifest").df()
    manifest["kickoff"] = pd.to_datetime(manifest["kickoff"], utc=True)
    lo, hi = ((pd.Timestamp("2026-09-01", tz="UTC"), sm.DISCOVERY_END) if args.phase == "discovery"
              else (sm.DISCOVERY_END, sm.CONFIRMATION_END))
    manifest = manifest[(manifest["kickoff"] >= lo) & (manifest["kickoff"] < hi)]

    a_all, b_all = [], []
    for f in manifest.itertuples():
        lad = con.execute("SELECT * FROM ladder WHERE fixture_id = ?", [f.fixture_id]).df()
        lad["created_at"] = pd.to_datetime(lad["created_at"], utc=True)
        a, b = cm.fixture_positions(lad, f.kickoff, engine)
        a_all.append(a.assign(event_id=f.fixture_id))
        b_all.append(b.assign(event_id=f.fixture_id))
    a = pd.concat(a_all, ignore_index=True) if a_all else pd.DataFrame()
    b = pd.concat(b_all, ignore_index=True) if b_all else pd.DataFrame()

    def boot(d):
        return sm.ratio_bootstrap(d.assign(v=d["value"]), "v") if len(d) else None

    def pct(e):
        return "–" if e is None else f"{100 * e.value:+.2f}% ({100 * e.low:+.2f} to {100 * e.high:+.2f})"

    def verdict(e, claim):
        if e is None:
            return "inconclusive (no positions)"
        tag = " (discovery result; confirmation on weeks 7–14 decides)" if args.phase == "discovery" else ""
        return f"**{claim}**{tag}" if e.low > 0 else ("**the opposite**" + tag if e.high < 0 else
                                                       "not distinguishable: no claim")

    ea, eb = boot(a), boot(b)
    a_book = [[NAMES[k], len(d), f"{100 * d['value_d'].mean():+.2f}%", pct(boot(d))] for k, d in a.groupby("book")] \
        if len(a) else []
    b_market = [[m, len(d), f"{100 * d['value_d'].mean():+.2f}%", pct(boot(d))] for m, d in b.groupby("market")] \
        if len(b) else []
    b_book = [[NAMES[k], len(d), pct(boot(d))] for k, d in b.groupby("book")] if len(b) else []
    b_h = [[h, len(d), pct(boot(d))] for h, d in b.groupby("h", sort=False)] if len(b) else []

    commit = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True).strip()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    parts = [
        f"# Cross-market value on main markets: {args.phase} (MS-054)", "",
        f"_Generated {now} · commit `{commit}` · reproduce with "
        f"`research/src/marketscope_research/run_cross_market.py --phase {args.phase}`._", "",
        "Design pre-registered in `research/PREREGISTRATION.md` (Addendum P, committed before this code). Data: the "
        "research lake (full ladders). Fair probabilities from the frozen engine v2 and Shin devig; the sharp "
        "consensus is the equal-weight mean of Pinnacle, Circa, Bookmaker.eu and Novig. Values are per unit at the "
        "sharp-consensus close. Game bootstrap (5,000, seed 2026). **Analysis, not betting advice.**", "",
        f"**Sample:** {len(manifest)} games in the lake for this phase.", "",
        "## A: moneylines priced better than the book's own spread", "",
        f"{len(a)} positions. Mean value at the close: {pct(ea)}. **Primary result:** "
        f"{verdict(ea, 'moneylines better than their own spread carry positive value')}.", "",
        table(a_book, ["Retail book", "Positions", "Value expected at decision time", "Value at the close"]), "",
        "## B: retail prices better than the sharp consensus at the same line", "",
        f"{len(b)} positions. Mean value at the close: {pct(eb)}. **Primary result:** "
        f"{verdict(eb, 'same-line prices above the sharp consensus carry positive value')}.", "",
        table(b_market, ["Market", "Positions", "Value expected at decision time", "Value at the close"]), "",
        table(b_book, ["Retail book", "Positions", "Value at the close"]), "",
        table(b_h, ["Hours before kickoff", "Positions", "Value at the close"]), "",
        "## What this can't see", "",
        "Alternate ladders (MS-055b); retail limits; whether a price would have been accepted at size.", "",
    ]
    with open(args.out, "w") as fh:
        fh.write("\n".join(parts))
    print("\n".join(p for p in parts if "result" in p.lower() and "**" in p or p.startswith("**Sample")))


if __name__ == "__main__":
    main()
