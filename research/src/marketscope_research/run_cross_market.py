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
    manifest = con.execute("SELECT fixture_id, event_id, kickoff FROM manifest").df()
    manifest["kickoff"] = pd.to_datetime(manifest["kickoff"], utc=True)
    lo, hi = ((pd.Timestamp("2026-09-01", tz="UTC"), sm.DISCOVERY_END) if args.phase == "discovery"
              else (sm.DISCOVERY_END, sm.CONFIRMATION_END))
    manifest = manifest[(manifest["kickoff"] >= lo) & (manifest["kickoff"] < hi)]

    engine3 = fv.load_engine(history, v3=True)  # MS-059 line conversion (Addendum T secondary)
    configs = (("registered", engine, False), ("coherent", engine, True), ("v3", engine3, True))
    runs = {key: ([], []) for key, _, _ in configs}
    for f in manifest.itertuples():
        lad = con.execute("SELECT * FROM ladder WHERE fixture_id = ?", [f.fixture_id]).df()
        lad["created_at"] = pd.to_datetime(lad["created_at"], utc=True)
        for key, eng, coherent in configs:
            a, b = cm.fixture_positions(lad, f.kickoff, eng, coherent=coherent)
            runs[key][0].append(a.assign(event_id=f.fixture_id))
            runs[key][1].append(b.assign(event_id=f.fixture_id))
    runs = {key: (pd.concat(a_all, ignore_index=True) if a_all else pd.DataFrame(),
                  pd.concat(b_all, ignore_index=True) if b_all else pd.DataFrame())
            for key, (a_all, b_all) in runs.items()}

    def boot(d, col="value"):
        d = d.dropna(subset=[col]) if len(d) else d
        return sm.ratio_bootstrap(d.assign(v=d[col]), "v") if len(d) else None

    def pct(e):
        return "–" if e is None else f"{100 * e.value:+.2f}% ({100 * e.low:+.2f} to {100 * e.high:+.2f})"

    def verdict(e, claim, registered=True):
        if e is None:
            return "inconclusive (no positions)"
        if registered and args.phase == "discovery":
            tag = " (discovery result; confirmation on weeks 7–14 decides)"
        elif not registered and args.phase == "discovery":
            tag = " (post hoc: cannot support a claim)"
        else:
            tag = ""
        return f"**{claim}**{tag}" if e.low > 0 else ("**the opposite**" + tag if e.high < 0 else
                                                       "not distinguishable: no claim")

    def n_direct(d):
        return int(d["value_direct"].notna().sum()) if len(d) else 0

    a, b = runs["registered"]
    ca, cb = runs["coherent"]
    _a3, b3 = runs["v3"]  # A is unchanged under v3: the moneyline conversion stayed v2
    # Addendum S: was the price also seen by our own collector (The Odds API) while it was in effect?
    with connect(dsn) as conn:
        obs = _frame(conn, """
            SELECT event_id::text, bookmaker_key, market_type::text, selection::text, point::float8 AS point,
                   american_price, observed_at
            FROM odds_observations WHERE source = 'the-odds-api' AND event_id = ANY(%s::uuid[])
              AND bookmaker_key IN ('draftkings', 'fanduel', 'hardrockbet')""", (list(manifest["event_id"]),))
    obs["observed_at"] = pd.to_datetime(obs["observed_at"], utc=True)
    ev = manifest.set_index("fixture_id")["event_id"]

    def corroborate(d):
        if not len(d):
            return d, d
        d = d.assign(fixture_id=d["event_id"], event_id=d["event_id"].map(ev))
        d["corroborated"] = cm.corroborated(d, obs)
        d["event_id"] = d["fixture_id"]
        return d, d[d["corroborated"].fillna(False).astype(bool)]

    cb, seen = corroborate(cb)
    b3, seen3 = corroborate(b3)
    e3, e3d, e3s, e3sd = boot(b3), boot(b3, "value_direct"), boot(seen3), boot(seen3, "value_direct")
    eseen, eseen_d = boot(seen), boot(seen, "value_direct")
    checkable = int(cb["corroborated"].notna().sum()) if len(cb) else 0
    ea, eb = boot(a), boot(b)
    a_book = [[NAMES[k], len(d), f"{100 * d['value_d'].mean():+.2f}%", pct(boot(d))] for k, d in a.groupby("book")] \
        if len(a) else []
    b_market = [[m, len(d), f"{100 * d['value_d'].mean():+.2f}%", pct(boot(d))] for m, d in b.groupby("market")] \
        if len(b) else []
    b_book = [[NAMES[k], len(d), pct(boot(d))] for k, d in b.groupby("book")] if len(b) else []
    b_h = [[h, len(d), pct(boot(d))] for h, d in b.groupby("h", sort=False)] if len(b) else []
    c_rows = [[label, len(d), pct(boot(d)), n_direct(d), pct(boot(d, "value_direct"))]
              for label, d in [("All", cb)] + ([(m, d) for m, d in cb.groupby("market")] if len(cb) else [])
              + ([(NAMES[k], d) for k, d in cb.groupby("book")] if len(cb) else [])]
    eca, ecb, ecd = boot(ca), boot(cb), boot(cb, "value_direct")
    both = eseen is not None and eseen_d is not None and eseen.low > 0 and eseen_d.low > 0
    c_rows.append(["Corroborated (Addendum S primary)", len(seen), pct(eseen), n_direct(seen), pct(eseen_d)])

    commit = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True).strip()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    if args.phase == "confirmation":
        primary_b = (f"**Primary result (Addendum S):** "
                     + ("**same-line prices above the sharp consensus carry positive value** (corroborated "
                        "positions; engine- and direct-scored intervals both above 0)" if both else
                        "no claim (on corroborated positions, both intervals must lie above 0)") + ".")
    else:
        primary_b = ("Under Addenda R and S a claim needs corroborated positions with both intervals above 0. These "
                     "discovery numbers were computed after the problems were found, so they are descriptive only, "
                     "and our collector only started on 2026-10-16, so few discovery prices can be corroborated.")
    parts = [
        f"# Cross-market value on main markets: {args.phase} (MS-054)", "",
        f"_Generated {now} · commit `{commit}` · reproduce with "
        f"`research/src/marketscope_research/run_cross_market.py --phase {args.phase}`._", "",
        "Design pre-registered in `research/PREREGISTRATION.md` (Addendum P, committed before this code; corrections "
        "in Addendum R). Data: the research lake (full ladders). Fair probabilities from the frozen engine v2 and Shin "
        "devig; the sharp consensus is the equal-weight mean of Pinnacle, Circa, Bookmaker.eu and Novig. Values are "
        "per unit at the sharp-consensus close. Game bootstrap (5,000, seed 2026). **Analysis, not betting "
        "advice.**", "",
        f"**Sample:** {len(manifest)} games in the lake for this phase.", "",
        "## As registered (Addendum P)", "",
        "### A: moneylines priced better than the book's own spread", "",
        f"{len(a)} positions. Mean value at the close: {pct(ea)}. **Primary result:** "
        f"{verdict(ea, 'moneylines better than their own spread carry positive value')}.", "",
        table(a_book, ["Retail book", "Positions", "Value expected at decision time", "Value at the close"]), "",
        "### B: retail prices better than the sharp consensus at the same line", "",
        f"{len(b)} positions. Mean value at the close: {pct(eb)}. **Primary result:** "
        f"{verdict(eb, 'same-line prices above the sharp consensus carry positive value')}.", "",
        table(b_market, ["Market", "Positions", "Value expected at decision time", "Value at the close"]), "",
        table(b_book, ["Retail book", "Positions", "Value at the close"]), "",
        table(b_h, ["Hours before kickoff", "Positions", "Value at the close"]), "",
        "## Corrected (Addendum R): ghost markets removed, direct scoring", "",
        "The feed sometimes leaves a sportsbook market marked active after the book stopped updating it. The "
        "registered main-line rule can pick such a ghost when it is priced closer to even than the real line. The "
        "coherence rule keeps a market only if its price is consistent with the book's fresher markets. Direct value "
        "scores half-point spreads and totals against the sharp books' own prices at that exact line, with no engine "
        "conversion.", "",
        f"A: {len(ca)} positions, {pct(eca)}: {verdict(eca, 'positive', registered=False)}. "
        f"B: {len(cb)} positions, engine-scored {pct(ecb)}; direct-scored {pct(ecd)} on {n_direct(cb)} positions "
        f"with a direct price. Corroborated by our own collector: {len(seen)} of {checkable} checkable positions "
        "(DraftKings, FanDuel, Hard Rock).", "",
        primary_b, "",
        table(c_rows, ["Positions", "Count", "Engine-scored value", "With a direct price", "Direct-scored value"]), "",
        "## Engine v3 (Addendum T secondary)", "",
        "Positions selected and scored with the MS-059 line conversion (logit scale for spreads and totals, fitted "
        "to the sharp books' own alternate prices), coherence rule applied. Moneyline conversion stayed v2, so A is "
        "the corrected A above. Secondary: the registered primaries stay on engine v2"
        + (" (post hoc on discovery games: descriptive only)." if args.phase == "discovery" else "."), "",
        f"B: {len(b3)} positions, engine-scored {pct(e3)}; direct-scored {pct(e3d)} on {n_direct(b3)} positions with "
        f"a direct price. Corroborated: {len(seen3)} positions, engine-scored {pct(e3s)}; direct-scored {pct(e3sd)} "
        f"on {n_direct(seen3)}.", "",
        "## What this can't see", "",
        "Alternate ladders (MS-055b); retail limits; whether a price would have been accepted at size; feed errors "
        "that are not ghost markets.", "",
    ]
    with open(args.out, "w") as fh:
        fh.write("\n".join(parts))
    print("\n".join(p for p in parts if ("result" in p.lower() and "**" in p) or p.startswith("**Sample")
                    or p.startswith("A: ")))


if __name__ == "__main__":
    main()
