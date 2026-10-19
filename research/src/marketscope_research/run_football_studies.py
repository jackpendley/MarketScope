"""Run the MS-035 football studies R1, R3, R4 and R5 (research/PREREGISTRATION.md) and write the report
(aggregates only).

    STUDY_DATABASE_URL=... .venv/bin/python -m marketscope_research.run_football_studies --out reports/football-studies-v1.md
"""

from __future__ import annotations

import argparse
import os
import subprocess
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from . import football_studies as fs
from .close_check import totals_consensus
from .consensus import board_quotes, consensus_series
from .data import _frame, connect, load_home_spreads, load_kickoffs, load_totals

SOURCES = ["the-odds-api", "oddspapi"]


def load(conn):
    games = _frame(conn, """
        SELECT g.game_id, g.season, g.week, g.game_type, g.kickoff_utc, g.event_id::text AS event_id,
               ht.franchise AS home, aw.franchise AS away, g.neutral_site AS neutral,
               g.home_score, g.away_score, g.nflverse_close_home_spread::float8 AS close_spread,
               g.nflverse_close_total::float8 AS close_total
        FROM nfl_games g JOIN nfl_teams ht ON ht.abbr = g.home_team JOIN nfl_teams aw ON aw.abbr = g.away_team
        WHERE g.home_score IS NOT NULL""")
    games["margin"] = (games["home_score"] - games["away_score"]).astype(float)
    games["total"] = (games["home_score"] + games["away_score"]).astype(float)
    games["close_margin"] = -games["close_spread"]
    snaps = _frame(conn, """SELECT season, week, team, adj_em, luck FROM rating_snapshots
                            WHERE model_version = 'ratings-v1'""")
    weather = _frame(conn, """SELECT game_id, lead_days, wind_mph, precip_in FROM nfl_weather_forecasts
                              WHERE lead_days IN (1, 3)""")
    spreads, totals, kickoffs = load_home_spreads(conn, SOURCES), load_totals(conn, SOURCES), load_kickoffs(conn)
    return games, snaps, weather, spreads, totals, kickoffs


def ci(e: fs.Estimate | None, digits: int = 2, signed: bool = True) -> str:
    if e is None:
        return "– (too few games)"
    f = f"{{:{'+' if signed else ''}.{digits}f}}"
    return f"{f.format(e.value)} ({f.format(e.low)} to {f.format(e.high)})"


def table(rows: list[list], head: list[str]) -> str:
    lines = ["| " + " | ".join(head) + " |", "|" + "|".join("---" for _ in head) + "|"]
    lines += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    dsn = os.environ.get("STUDY_DATABASE_URL")
    if not dsn:
        raise SystemExit("Set STUDY_DATABASE_URL (read-only use).")
    with connect(dsn) as conn:
        games, snaps, weather, spreads, totals, kickoffs = load(conn)
    reg = games[games["game_type"] == "REG"]

    # R1 -------------------------------------------------------------------------------------
    g26 = reg[(reg["season"] == 2026) & reg["event_id"].notna()]
    cons = consensus_series(spreads[spreads["event_id"].isin(g26["event_id"])])
    leads = fs.consensus_at_leads(cons, kickoffs)
    r1df = leads.merge(g26[["event_id", "margin", "close_spread"]].rename(columns={"close_spread": "nflverse_close"}),
                       on="event_id")
    r1 = fs.r1_accuracy(r1df)
    full = r1df.dropna(subset=[*fs.R1_LEADS, "close"])
    books = fs.r1_books(board_quotes(spreads), full[["event_id", "close_observed_at", "close"]],
                        full.set_index("event_id")["margin"])
    src = spreads[spreads["event_id"].isin(full["event_id"])].groupby("event_id")["source"].first().value_counts()

    # R3 -------------------------------------------------------------------------------------
    w1 = weather[weather["lead_days"] == 1].drop_duplicates("game_id")
    w3 = weather[weather["lead_days"] == 3].drop_duplicates("game_id")
    r3df = games[games["season"].between(2024, 2026) & games["close_total"].notna()].merge(
        w1[["game_id", "wind_mph", "precip_in"]], on="game_id")
    r3 = fs.r3_pricing(r3df)
    tc = totals_consensus(totals[totals["event_id"].isin(g26["event_id"])]).rename(columns={"total": "consensus"})
    tl = fs.consensus_at_leads(tc, kickoffs)
    mv = g26.merge(tl, on="event_id").merge(w1[["game_id", "wind_mph"]], on="game_id").merge(
        w3[["game_id", "wind_mph"]].rename(columns={"wind_mph": "wind3"}), on="game_id")
    mv = mv.dropna(subset=["3 days", "close"])
    mv["crossed"] = (mv["wind3"] < fs.R3_WINDY) & (mv["wind_mph"] >= fs.R3_WINDY)
    mv["move"] = mv["close"] - mv["3 days"]
    r3m = fs.r3_movement(mv)

    # R4 / R5 --------------------------------------------------------------------------------
    rg = fs.rating_games(reg[reg["season"].isin(fs.RATING_SEASONS)], snaps[snaps["season"].isin(fs.RATING_SEASONS)])
    r4 = fs.r4_priced(rg)
    rg26 = fs.rating_games(g26.assign(close_margin=g26["close_margin"].fillna(0.0)), snaps[snaps["season"] == 2026])
    m4 = rg26.merge(leads, on="event_id")
    m4["gap6"] = m4["rating_margin"] - (-m4["6 days"])
    m4["move"] = (-m4["close"]) - (-m4["6 days"])
    r4m = fs.r4_move(m4)
    r5 = fs.r5_luck(rg)
    last_week = {s: (18 if s >= 2021 else 17) for s in fs.RATING_SEASONS}
    r5p = fs.r5_persistence(snaps[snaps["season"].isin(fs.RATING_SEASONS)], last_week)

    commit = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True).strip()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    verdict = lambda e, claim_dir: "**yes**" if e.excludes_zero() == claim_dir else "no"  # noqa: E731

    parts = [
        "# Football studies v1: R1, R3, R4, R5 (MS-035)",
        "",
        f"_Generated {now} · commit `{commit}` · reproduce with "
        "`research/src/marketscope_research/run_football_studies.py`._",
        "",
        "Design pre-registered in `research/PREREGISTRATION.md` (commit 168538a, before this code). 95% intervals "
        "resample games (5,000 draws). Model estimates and market data; not betting advice.",
        "",
        "## Summary",
        "",
        table([
            ["R1", "Consensus more accurate at the close than 6 days out", ci(r1["diff_vs_close"]["6 days"]) + " pts",
             "inconclusive (gate)" if not r1["gate"] else verdict(r1["diff_vs_close"]["6 days"], "above 0")],
            ["R3", "Wind under- or over-priced in closing totals", ci(r3["slope"], 3) + " pts per mph",
             "inconclusive (gate)" if not r3["gate"] else
             ("**under-priced**" if r3["slope"].high < 0 else "**over-priced**" if r3["slope"].low > 0 else "no")],
            ["R4", "Ratings carry information beyond the close", ci(r4["slope"], 3) + " ATS pts per pt of gap",
             "**yes**" if r4["claim"] else "no"],
            ["R5", "Market overrates lucky teams", ci(r5["market"], 3) + " ATS pts per win of luck",
             verdict(r5["market"], "below 0")],
        ], ["Study", "Primary hypothesis", "Estimate (95% CI)", "Claim?"]),
        "",
        "## R1: market accuracy over time (2026)",
        "",
        f"{r1['games']} final 2026 games with a board consensus at all four leads (gate: {fs.R1_MIN_GAMES}; "
        f"sources: {', '.join(f'{k} {v}' for k, v in src.items())}).",
        "",
        table([[k, f"{v:.2f}", ci(r1["diff_vs_close"].get(k)) if k != "close" else "–"]
               for k, v in r1["mae"].items()], ["Line", "Margin MAE", "Minus our close (paired)"]),
        "",
        "Closing line of each board book vs the consensus in the same snapshot (exploratory; negative = the book "
        "was closer to the result):",
        "",
        table([[r.book, r.games, f"{r.mae:.2f}", ci(r.vs_consensus)] for r in books.itertuples()],
              ["Book", "Games", "MAE", "Minus consensus"]),
        "",
        "## R3: weather and totals (2024–26)",
        "",
        f"{r3['games']} outdoor/open-roof games with a 1-day forecast and a closing total; {r3['windy']} with forecast "
        f"wind ≥ {fs.R3_WINDY:.0f} mph (gate: {fs.R3_MIN_GAMES} and {fs.R3_MIN_WINDY})."
        + ("" if r3["gate"] else " **The gate is not met, so the primary result is inconclusive**; the estimate is "
           "shown for transparency and makes no claim. It will be re-run when more windy games are final."),
        "",
        f"- **Primary:** total residual (actual − close) per mph of forecast wind: {ci(r3['slope'], 3)}.",
        f"- **Market response (exploratory):** the closing total moves {r3['close_per_mph'][0]:+.3f} points per mph "
        f"(HC1 SE {r3['close_per_mph'][1]:.3f}, season fixed effects).",
        f"- **Precipitation (descriptive):** {r3['precip']['wet_games']} games with forecast precipitation; mean "
        f"residual {r3['precip']['wet_mean_residual']:+.2f} vs {r3['precip']['dry_mean_residual']:+.2f} dry.",
        "",
        table([[b["wind"], b["games"], f"{b['mean_close']:.1f}", ci(b["mean_residual"])] for b in r3["buckets"]],
              ["Forecast wind (mph)", "Games", "Mean close", "Mean residual (actual − close)"]),
        "",
        f"- **Movement (exploratory, 2026 odds):** {r3m['crossings']} game{'' if r3m['crossings'] == 1 else 's'} crossed {fs.R3_WINDY:.0f} mph between the "
        f"3-day and 1-day forecasts (gate {fs.R3_MIN_CROSSINGS}): "
        + ("inconclusive." if not r3m["gate"] else
           f"totals consensus moved {ci(r3m['crossed_move'])} vs {ci(r3m['other_move'])} in other games."),
        "",
        "## R4: is performance priced? (2016–24)",
        "",
        f"{r4['games']} games. Mean absolute gap between the rating margin and the close: {r4['mean_abs_gap']:.2f} pts.",
        "",
        f"- **Primary:** ATS residual per point of gap: {ci(r4['slope'], 3)}; positive in {r4['positive_seasons']} of "
        f"{len(r4['per_season'])} seasons. Claim rule (interval above 0 and ≥ 6 positive seasons): "
        f"{'met' if r4['claim'] else 'not met'}.",
        f"- **2023–24 only (out-of-sample for the rating parameters):** {ci(r4['out_of_sample'], 3)}.",
        "- **Per season:** " + ", ".join(f"{s} {v:+.3f}" for s, v in r4["per_season"].items()) + ".",
        f"- **Closing move (exploratory, 2026):** {r4m['games']} games (gate {fs.R4_MIN_MOVE_GAMES}); "
        + (f"consensus move per point of 6-day gap: {ci(r4m['slope'], 3)}." if r4m["gate"] else "inconclusive."),
        "",
        "## R5: luck regression (2016–24)",
        "",
        f"{r5['games']} games from week {fs.R5_FROM_WEEK}; SD of the luck difference {r5['luck_sd']:.2f} wins.",
        "",
        f"- **Primary (market):** ATS residual per win of luck difference: {ci(r5['market'], 3)}.",
        f"- **Ratings (exploratory):** rating residual per win of luck difference: {ci(r5['ratings'], 3)}.",
        f"- **Persistence (exploratory):** luck gained after week {fs.R5_SPLIT_WEEK} per win of luck through week "
        f"{fs.R5_SPLIT_WEEK}: {ci(r5p['slope'], 3)} ({r5p['team_seasons']} team-seasons).",
        "",
        "## Not run yet",
        "",
        "- **R2 (injury news):** live injury snapshots began 2026-10-18; gate 30 events.",
        "- **R6 (model + market blend) and R7 (play-caller impact):** next milestone.",
    ]
    with open(args.out, "w") as fh:
        fh.write("\n".join(parts) + "\n")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
