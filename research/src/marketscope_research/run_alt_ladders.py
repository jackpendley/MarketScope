"""MS-055b alternate ladders (research/PREREGISTRATION.md Addendum Q). Reads the research lake and the
database read-only.

    STUDY_DATABASE_URL=... .venv/bin/python -m marketscope_research.run_alt_ladders --phase discovery \
        --out reports/alt-ladders-discovery.md

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
from .run_cross_market import NAMES
from .run_football_studies import table


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
    parts_ = []
    for f in manifest.itertuples():
        lad = con.execute("SELECT * FROM ladder WHERE fixture_id = ?", [f.fixture_id]).df()
        lad["created_at"] = pd.to_datetime(lad["created_at"], utc=True)
        parts_.append(cm.alt_positions(lad, f.kickoff, engine).assign(event_id=f.fixture_id))
    alt = pd.concat(parts_, ignore_index=True) if parts_ else pd.DataFrame()

    def boot(d):
        return sm.ratio_bootstrap(d.assign(v=d["value"]), "v") if len(d) else None

    def pct(e):
        return "–" if e is None else f"{100 * e.value:+.2f}% ({100 * e.low:+.2f} to {100 * e.high:+.2f})"

    e = boot(alt)
    tag = " (discovery result; confirmation on weeks 7–14 decides)" if args.phase == "discovery" else ""
    verdict = ("inconclusive (no positions)" if e is None else
               f"**retail alternates above the sharp consensus carry positive value**{tag}" if e.low > 0 else
               f"**the opposite**{tag}" if e.high < 0 else "not distinguishable: no claim")
    rows_key = [[label, len(d), f"{100 * d['value_d'].mean():+.2f}%" if len(d) else "–", pct(boot(d))]
                for label, d in (("Spread alternates spanning 3 or 7", alt[alt["key"]] if len(alt) else alt),
                                 ("Other spread alternates", alt[(alt["market"] == "spreads") & ~alt["key"]] if len(alt) else alt),
                                 ("Total alternates", alt[alt["market"] == "totals"] if len(alt) else alt))]
    rows_dist = [[label, len(d), pct(boot(d))] for label, d in (
        ("0.5–1 point from the main line", alt[alt["distance"] <= 1] if len(alt) else alt),
        ("1.5–3 points", alt[(alt["distance"] > 1) & (alt["distance"] <= 3)] if len(alt) else alt),
        ("More than 3 points", alt[alt["distance"] > 3] if len(alt) else alt))]
    rows_book = [[NAMES[k], len(d), pct(boot(d))] for k, d in alt.groupby("book")] if len(alt) else []

    commit = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True).strip()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    parts = [
        f"# Alternate ladders: {args.phase} (MS-055b)", "",
        f"_Generated {now} · commit `{commit}` · reproduce with "
        f"`research/src/marketscope_research/run_alt_ladders.py --phase {args.phase}`._", "",
        "Design pre-registered in `research/PREREGISTRATION.md` (Addendum Q, committed before this code). Every retail "
        "alternate spread and total (−300 to +300) priced against the sharp-consensus fair probability at its exact "
        "line (engine v2, Shin devig); candidates are the ones worth more than 0 at decision time, scored at the "
        "sharp-consensus close. Game bootstrap (5,000, seed 2026). **Analysis, not betting advice.**", "",
        f"**Sample:** {len(manifest)} games; {len(alt)} candidate alternates.", "",
        f"## Primary\n\nMean value at the close: {pct(e)}. **Primary result:** {verdict}.", "",
        "## Exploratory", "",
        table(rows_key, ["Alternates", "Positions", "Value expected at decision time", "Value at the close"]), "",
        table(rows_dist, ["Distance from the book's main line", "Positions", "Value at the close"]), "",
        table(rows_book, ["Retail book", "Positions", "Value at the close"]), "",
        "## What this can't see", "",
        "Retail limits on alternates (usually lower than on main lines); whether a price would have been accepted.", "",
    ]
    with open(args.out, "w") as fh:
        fh.write("\n".join(parts))
    print("\n".join(p for p in parts if "result" in p.lower() and "**" in p or p.startswith("**Sample")))


if __name__ == "__main__":
    main()
