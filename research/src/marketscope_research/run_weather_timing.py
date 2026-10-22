"""MS-056 weather-forecast revisions and totals timing (research/PREREGISTRATION.md Addendum U). Reads the
database read-only, the research lake, and archived Open-Meteo runs (fetched once into
fixtures/open-meteo/local/; weather data by Open-Meteo.com, CC BY 4.0).

    STUDY_DATABASE_URL=... .venv/bin/python -m marketscope_research.run_weather_timing --phase discovery \
        --out reports/weather-timing-discovery.md

Analysis of value at the sharp-consensus close; not betting advice.
"""

from __future__ import annotations

import argparse
import csv
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from . import provenance
from . import results
from . import cross_market as cm
from . import fair_value as fv
from . import injury_windows as iw
from . import sharp_market as sm
from . import weather_runs as wr
from . import weather_timing as wt
from .data import _frame, connect
from .lake import store
from .run_cross_market import NAMES
from .run_football_studies import table

VENUES = Path(__file__).resolve().parents[3] / "apps" / "football" / "data" / "venues.csv"
CONFIRMATION_END = pd.Timestamp("2027-01-12", tz="UTC")  # after week 18 (Sunday 2027-01-10, Monday night)
EXPLORATORY = (("gfs_global", "wind_mph", wt.MIN_REVISION, wt.MIN_WIND, wt.EARLIEST, "GFS wind"),
               ("ncep_hrrr_conus", "wind_mph", wt.MIN_REVISION, wt.MIN_WIND, pd.Timedelta(hours=48),
                "HRRR wind (within 48 h)"),
               (wt.MODEL, "precip_in", 0.1, 0.0, wt.EARLIEST, "ECMWF precipitation (≥ 0.1 in)"))


def load_games(conn) -> pd.DataFrame:
    games = _frame(conn, """
        SELECT g.game_id, g.week, g.kickoff_utc AS kickoff, g.event_id::text AS event_id,
               c.venue_key, c.roof_type
        FROM nfl_games g
        JOIN (SELECT DISTINCT game_id, venue_key, roof_type FROM nfl_game_context) c USING (game_id)
        WHERE g.season = 2026 AND g.game_type = 'REG'""")
    games["kickoff"] = pd.to_datetime(games["kickoff"], utc=True)
    with VENUES.open() as f:
        coords = {v["venue_key"]: (float(v["lat"]), float(v["lon"])) for v in csv.DictReader(f)}
    games = games[games["roof_type"].isin(["outdoor", "retractable"]) & games["venue_key"].isin(coords)]
    return games.assign(lat=games["venue_key"].map(lambda k: coords[k][0]),
                        lon=games["venue_key"].map(lambda k: coords[k][1])).reset_index(drop=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", choices=["discovery", "confirmation"], default="discovery")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    dsn = os.environ.get("STUDY_DATABASE_URL")
    if not dsn:
        raise SystemExit("Set STUDY_DATABASE_URL (read-only use).")
    with connect(dsn) as conn:
        games = load_games(conn)
        history = _frame(conn, """
            SELECT season, nflverse_close_home_spread::float8 AS home_line, nflverse_close_total::float8 AS total,
                   (home_score - away_score)::float8 AS margin, (home_score + away_score)::float8 AS points
            FROM nfl_games WHERE season BETWEEN 2016 AND 2025 AND home_score IS NOT NULL
              AND nflverse_close_home_spread IS NOT NULL AND nflverse_close_total IS NOT NULL""")
    engine = fv.load_engine(history, v3=True)  # Addendum U: engine v3's totals conversion

    lo, hi = ((pd.Timestamp("2026-09-01", tz="UTC"), sm.DISCOVERY_END) if args.phase == "discovery"
              else (sm.DISCOVERY_END, CONFIRMATION_END))
    con = store.connect()
    manifest = con.execute("SELECT fixture_id, event_id FROM manifest").df()
    fixture_of = dict(zip(manifest["event_id"], manifest["fixture_id"]))
    games = games[(games["kickoff"] >= lo) & (games["kickoff"] < hi)]
    in_lake = games[games["event_id"].isin(fixture_of)]

    runs = {m: wr.build(games, m) for m in {wt.MODEL} | {e[0] for e in EXPLORATORY}}

    pos, placebo, react, first, explo = [], [], [], [], {e[5]: [] for e in EXPLORATORY}
    n_event_games = 0
    for g in in_lake.itertuples():
        lad = con.execute("SELECT * FROM ladder WHERE fixture_id = ?", [fixture_of[g.event_id]]).df()
        lad["created_at"] = pd.to_datetime(lad["created_at"], utc=True)
        cands = cm.book_candidates(lad)  # built once per game
        mine = runs[wt.MODEL][runs[wt.MODEL]["game_id"] == g.game_id]
        revs = wt.revisions(mine, g.kickoff)
        n_event_games += bool(revs["event"].any())
        pos.append(wt.positions(lad, g.kickoff, revs, engine, cands=cands).assign(event_id=g.game_id, week=g.week))
        placebo.append(wt.positions(lad, g.kickoff, revs, engine, wt.PLACEBO, cands=cands)
                       .assign(event_id=g.game_id))
        react.append(wt.reaction(lad, g.kickoff, revs, cands=cands).assign(event_id=g.game_id))
        first.append(wt.minutes_to_first_move(lad, g.kickoff, revs, cands=cands).assign(event_id=g.game_id))
        for model, col, min_rev, min_level, earliest, label in EXPLORATORY:
            rm = runs[model][runs[model]["game_id"] == g.game_id]
            r2 = wt.revisions(rm, g.kickoff, col, min_rev, min_level, earliest)
            explo[label].append(wt.positions(lad, g.kickoff, r2, engine, cands=cands).assign(event_id=g.game_id))

    def cat(parts):
        return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()

    pos, placebo, react, first = cat(pos), cat(placebo), cat(react), cat(first)

    def boot(d, col="value"):
        return sm.ratio_bootstrap(d.assign(v=d[col]), "v") if len(d) else None

    def pct(e):
        return "–" if e is None else f"{100 * e.value:+.2f}% ({100 * e.low:+.2f} to {100 * e.high:+.2f})"

    e1, ep = boot(pos), boot(placebo)
    tag = " (discovery result; confirmation on weeks 7–18 decides)" if args.phase == "discovery" else ""
    verdict = ("inconclusive (no positions)" if e1 is None else
               f"**taking the forecast's side when a run becomes public carries positive value**{tag}"
               if e1.low > 0 else f"**the opposite**{tag}" if e1.high < 0 else "not distinguishable: no claim")
    react = react.sort_values(["event_id", "run"]).reset_index(drop=True) if len(react) else react
    s6 = iw.slope_ci(react, "move_6h", "dw") if len(react) > 2 else None
    sc = iw.slope_ci(react, "move_close", "dw") if len(react) > 2 else None

    def slope(e):
        return "–" if e is None else f"{e.value:+.3f} ({e.low:+.3f} to {e.high:+.3f})"

    names = {**NAMES, "pinnacle": "Pinnacle"}
    by_book = [[names.get(k, k), len(d), pct(boot(d))] for k, d in pos.groupby("book")] if len(pos) else []
    if len(pos):
        by_book += [["Retail books", int((pos["book"] != "pinnacle").sum()), pct(boot(pos[pos["book"] != "pinnacle"]))]]
    explo_rows = [[label, len(d := cat(parts)), d["event_id"].nunique() if len(d) else 0, pct(boot(d))]
                  for label, parts in explo.items()]

    def med(x):
        x = x.dropna()
        return f"{x.median():.0f} min ({len(x)} runs)" if len(x) else "–"

    first_line = ("–" if not len(first) else
                  f"events {med(first.loc[first['event'], 'minutes'])}; other in-window runs "
                  f"{med(first.loc[~first['event'], 'minutes'])}")

    commit = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True).strip()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    parts = [
        f"# Weather-forecast revisions and totals timing: {args.phase} (MS-056)", "",
        f"_Generated {now} · commit `{commit}` · reproduce with "
        f"`research/src/marketscope_research/run_weather_timing.py --phase {args.phase}`._", "",
        "Design pre-registered in `research/PREREGISTRATION.md` (Addendum U, committed before this code). Archived "
        "ECMWF IFS runs (Open-Meteo Single Runs API; weather data by Open-Meteo.com, CC BY 4.0), available 6 hours "
        "after initialisation. An event is a game-window wind revision of at least 4 mph (either run at least 12 "
        "mph), public 72 to 1 hours before kickoff. Positions take the forecast's side of each book's main total 10 "
        "minutes after availability; value at the sharp-consensus close (engine v3, MS-058 ghost rule). Game "
        "bootstrap (5,000, seed 2026). **Analysis, not betting advice.**", "",
        f"**Sample:** {len(games)} outdoor or retractable-roof games, {len(in_lake)} in the lake; {n_event_games} "
        f"with at least one event; {len(pos)} positions.", "",
        "## Primary", "",
        f"Mean value at the close: {pct(e1)}. **Primary result:** {verdict}.", "",
        # Reporting addition after the first run (not part of Addendum U's decision rule):
        f"_Positions come from {pos['event_id'].nunique() if len(pos) else 0} games in "
        f"{pos['week'].nunique() if len(pos) else 0} weeks._"
        + (" _With fewer than 10 games a game bootstrap cannot support any conclusion; read the primary as "
           "inconclusive whatever its interval (reporting note added after the first run)._"
           if len(pos) and pos["event_id"].nunique() < 10 else ""), "",
        table(by_book, ["Book", "Positions", "Value at the close"]), "",
        "## Secondary", "",
        f"Placebo, the same positions 3 hours before the run existed: {len(placebo)} positions, {pct(ep)}.", "",
        f"Reaction: Pinnacle's total move per mph of revision, over {len(react)} in-window runs: within 6 hours "
        f"{slope(s6)} points; to the close {slope(sc)} points. Negative means the market moves with the forecast.",
        "",
        "## Exploratory", "",
        table(explo_rows, ["Event source", "Positions", "Games", "Value at the close"]), "",
        f"Minutes from availability to Pinnacle's next total change (median): {first_line}.", "",
        "## What this can't see", "",
        "Forecasts the market saw before Open-Meteo's archive did; runs other than 00, 06, 12 and 18 UTC; whether a "
        "retail price would have been accepted at size; wind inside the stadium bowl.", "",
    ]
    with open(args.out, "w") as fh:
        fh.write("\n".join(parts))
    if e1 is not None:
        results.record_result("F1", e1.value, e1.low, e1.high, positions=len(pos),
                              games=int(pos["event_id"].nunique()), weeks=int(pos["week"].nunique()),
                              dataset=provenance.lake_dataset([fixture_of[e] for e in in_lake["event_id"]])["dataset_id"],
                              report=args.out)
    provenance.write_run_record(args.out, provenance.run_record(
        "MS-056 weather timing", [provenance.lake_dataset([fixture_of[e] for e in in_lake["event_id"]]), {"kind": "open-meteo single runs", "models": sorted(runs), "rows": {m: len(r) for m, r in runs.items()}, "sha256": {m: provenance.frame_sha256(r) for m, r in runs.items()}}],
        [Path(fv.__file__).with_name("fair_value_params.json")], ["MS-058 ghost rule", "engine v3 totals conversion (ADR-066)"], {"phase": getattr(args, "phase", None)}))
    print("\n".join(p for p in parts if p.startswith("**") or p.startswith("Placebo") or p.startswith("Reaction")))


if __name__ == "__main__":
    main()
