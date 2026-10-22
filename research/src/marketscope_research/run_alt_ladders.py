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
    runs = {}
    for coherent in (False, True):
        parts_ = []
        for f in manifest.itertuples():
            lad = con.execute("SELECT * FROM ladder WHERE fixture_id = ?", [f.fixture_id]).df()
            lad["created_at"] = pd.to_datetime(lad["created_at"], utc=True)
            parts_.append(cm.alt_positions(lad, f.kickoff, engine, coherent=coherent).assign(event_id=f.fixture_id))
        runs[coherent] = pd.concat(parts_, ignore_index=True) if parts_ else pd.DataFrame()
    alt, calt = runs[False], runs[True]

    def boot(d, col="value"):
        d = d.dropna(subset=[col]) if len(d) else d
        return sm.ratio_bootstrap(d.assign(v=d[col]), "v") if len(d) else None

    def pct(e):
        return "–" if e is None else f"{100 * e.value:+.2f}% ({100 * e.low:+.2f} to {100 * e.high:+.2f})"

    def nd(d):
        return int(d["value_direct"].notna().sum()) if len(d) else 0

    e = boot(alt)
    tag = " (discovery result; confirmation on weeks 7–14 decides)" if args.phase == "discovery" else ""
    verdict = ("inconclusive (no positions)" if e is None else
               f"**retail alternates above the sharp consensus carry positive value**{tag}" if e.low > 0 else
               f"**the opposite**{tag}" if e.high < 0 else "not distinguishable: no claim")

    def groups(d):
        if not len(d):
            return []
        return [("Spread alternates spanning 3 or 7", d[d["key"]]),
                ("Other spread alternates", d[(d["market"] == "spreads") & ~d["key"]]),
                ("Total alternates", d[d["market"] == "totals"]),
                ("0.5–1 point from the main line", d[d["distance"] <= 1]),
                ("1.5–3 points", d[(d["distance"] > 1) & (d["distance"] <= 3)]),
                ("More than 3 points", d[d["distance"] > 3])] + [(NAMES[k], g) for k, g in d.groupby("book")]

    rows_reg = [[label, len(d), f"{100 * d['value_d'].mean():+.2f}%" if len(d) else "–", pct(boot(d))]
                for label, d in groups(alt)]
    rows_cor = [[label, len(d), pct(boot(d)), nd(d), pct(boot(d, "value_direct"))]
                for label, d in [("All", calt)] + groups(calt)]
    ec, ecd = boot(calt), boot(calt, "value_direct")
    both = ec is not None and ecd is not None and ec.low > 0 and ecd.low > 0
    near = calt[calt["distance"] <= 1] if len(calt) else calt
    if args.phase == "confirmation":
        primary = ("**Primary result (Addendum R):** "
                   + ("**retail alternates above the sharp consensus carry positive value** (engine- and "
                      "direct-scored intervals both above 0)" if both else
                      "no claim (both intervals must lie above 0)") + f". Secondary, alternates within 1 point "
                   f"(direct): {pct(boot(near, 'value_direct'))}.")
    else:
        primary = ("Under Addendum R a claim needs both intervals above 0; these discovery numbers were computed "
                   "after the problems were found, so they are descriptive only.")

    commit = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True).strip()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    parts = [
        f"# Alternate ladders: {args.phase} (MS-055b)", "",
        f"_Generated {now} · commit `{commit}` · reproduce with "
        f"`research/src/marketscope_research/run_alt_ladders.py --phase {args.phase}`._", "",
        "Design pre-registered in `research/PREREGISTRATION.md` (Addendum Q, committed before this code; corrections "
        "in Addendum R). Every retail alternate spread and total (−300 to +300) priced against the sharp-consensus "
        "fair probability at its exact line (engine v2, Shin devig); candidates are the ones worth more than 0 at "
        "decision time, scored at the sharp-consensus close. Game bootstrap (5,000, seed 2026). **Analysis, not "
        "betting advice.**", "",
        f"**Sample:** {len(manifest)} games; {len(alt)} candidate alternates as registered, {len(calt)} after the "
        "coherence rule.", "",
        "## As registered (Addendum Q)", "",
        f"Mean value at the close: {pct(e)}. **Primary result:** {verdict}.", "",
        table(rows_reg, ["Alternates", "Positions", "Value expected at decision time", "Value at the close"]), "",
        "## Corrected (Addendum R): ghost markets removed, direct scoring", "",
        "The engine moves a sharp price to another line by adding the main-line calibration shift unchanged at every "
        "line, which overstates the tails far from the main line. Direct value scores half-point alternates against "
        "the sharp books' own prices at that exact line instead (Pinnacle, Circa, Bookmaker.eu, Shin devig). The "
        "coherence rule removes ghost markets.", "",
        f"Engine-scored {pct(ec)}; direct-scored {pct(ecd)} on {nd(calt)} alternates with a direct price.", "",
        primary, "",
        table(rows_cor, ["Alternates", "Count", "Engine-scored value", "With a direct price", "Direct-scored value"]),
        "",
        "## What this can't see", "",
        "Retail limits on alternates (usually lower than on main lines); whether a price would have been accepted; "
        "sharp alternate prices carry more margin than main lines, so the direct fair price is itself approximate.",
        "",
    ]
    with open(args.out, "w") as fh:
        fh.write("\n".join(parts))
    print("\n".join(p for p in parts if ("result" in p.lower() and "**" in p) or p.startswith("**Sample")
                    or p.startswith("Engine-scored")))


if __name__ == "__main__":
    main()
