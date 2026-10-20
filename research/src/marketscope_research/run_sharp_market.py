"""MS-043 sharp-market study S1–S5 (research/PREREGISTRATION.md, Addendum C). Read-only.

    STUDY_DATABASE_URL=... .venv/bin/python -m marketscope_research.run_sharp_market \
        --phase discovery --out reports/sharp-market-discovery.md

--phase confirmation re-runs the same code on weeks 7–14 once those games are imported.
"""

from __future__ import annotations

import argparse
import os
import subprocess
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from . import sharp_market as sm
from .data import _frame, connect
from .run_football_studies import ci, table

PHASES = {
    "discovery": (pd.Timestamp("2026-09-01", tz="UTC"), sm.DISCOVERY_END),
    "confirmation": (sm.DISCOVERY_END, sm.CONFIRMATION_END),
}
NAMES = {"pinnacle": "Pinnacle", "circa": "Circa", "bookmaker_eu": "Bookmaker.eu",
         "draftkings": "DraftKings", "fanduel": "FanDuel", "williamhill_us": "Caesars",
         "hardrockbet": "Hard Rock"}


def load(conn, start: pd.Timestamp, end: pd.Timestamp):
    games = _frame(conn, """
        SELECT e.id::text AS event_id, e.commence_time_utc AS kickoff,
               (g.home_score - g.away_score)::float8 AS margin
        FROM events e JOIN nfl_games g ON g.event_id = e.id
        WHERE g.season = 2026 AND g.game_type = 'REG' AND g.home_score IS NOT NULL
          AND e.commence_time_utc >= %s AND e.commence_time_utc < %s""", (start, end))
    games["kickoff"] = pd.to_datetime(games["kickoff"], utc=True)
    moves = _frame(conn, """
        SELECT event_id::text, bookmaker_key, market_type, changed_at, point::float8 AS point,
               price1, price2, limit1::float8 AS limit1
        FROM line_moves WHERE event_id = ANY(%s::uuid[])""", (list(games["event_id"]),))
    moves["changed_at"] = pd.to_datetime(moves["changed_at"], utc=True)
    return games, moves


def pct(x: float) -> str:
    return "–" if x is None or np.isnan(x) else f"{100 * x:.1f}%"


def verdict(e, gate: bool, claim: str, threshold: float = 0.0) -> str:
    if not gate or e is None:
        return "inconclusive (gate not met)"
    if e.low > threshold:
        return f"**{claim}** (discovery result; needs confirmation on weeks 7–14)"
    if e.high < threshold:
        return "**the opposite direction** (discovery result; needs confirmation)"
    return "not distinguishable: no claim"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", choices=PHASES, default="discovery")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    dsn = os.environ.get("STUDY_DATABASE_URL")
    if not dsn:
        raise SystemExit("Set STUDY_DATABASE_URL (read-only use).")
    with connect(dsn) as conn:
        games, moves = load(conn, *PHASES[args.phase])

    kicks = games.set_index("event_id")["kickoff"]
    margins = games.set_index("event_id")["margin"]
    spreads = moves[moves["market_type"] == "spreads"]
    with_pin = spreads.loc[spreads["bookmaker_key"] == "pinnacle", "event_id"].unique()
    spreads = spreads[spreads["event_id"].isin(with_pin)]
    tl = sm.timelines(spreads)
    closes = {e: c for e, b in tl.items() if (c := sm.close_line(b.get("pinnacle"), kicks[e])) is not None}

    totals = moves[moves["market_type"] == "totals"]
    tl_t = sm.timelines(totals[totals["event_id"].isin(totals.loc[totals["bookmaker_key"] == "pinnacle", "event_id"])])
    closes_t = {e: c for e, b in tl_t.items() if (c := sm.close_line(b.get("pinnacle"), kicks[e])) is not None}

    # S1
    pairs = sm.s1_pairs(tl, kicks)
    r1 = sm.s1(pairs)
    follow = sm.follow_times(tl, kicks)
    # S2
    ev = sm.s2_events(tl, kicks, closes)
    r2 = sm.s2(ev)
    ev5 = sm.s2_events(tl, kicks, closes, delay=pd.Timedelta(minutes=5))
    ev_t = sm.s2_events(tl_t, kicks, closes_t, market="totals")
    cover = sm.hypothetical_cover(ev, margins)
    # S3
    episodes = sm.steam_episodes(tl, kicks)
    out3 = sm.s3_outcomes(episodes, tl, closes)
    r3 = sm.s3(out3)
    out3_t = sm.s3_outcomes(sm.steam_episodes(tl_t, kicks), tl_t, closes_t, market="totals")
    # S4/S5
    pc = sm.pinnacle_changes(tl, closes)

    commit = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True).strip()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    start, end = PHASES[args.phase]
    pin = r1["pinnacle"]

    def mean_ci(df, col):
        return ci(sm.ratio_bootstrap(df, col)) if len(df) else "–"

    s1_rows = [[NAMES[r], r1[r]["pairs"], r1[r]["ties"], ci(r1[r]["share"], 3, signed=False)
                if r1[r]["share"] else "–"] for r in sm.REFERENCE]
    follow_rows = []
    for k in sm.RETAIL:
        f = follow[follow["retail"] == k]["minutes"]
        if len(f) == 0:
            continue
        followed = f.dropna()
        follow_rows.append([NAMES[k], len(f), pct((f <= 5).mean()), pct((f <= 15).mean()), pct((f <= 60).mean()),
                            pct(f.isna().mean()),
                            f"{followed.median():.0f} min" if len(followed) else "–"])
    s2_book = [[NAMES[k], len(d), f"{d['clv'].mean():+.2f}", f"{d['stale_min'].median():.0f} min"]
               for k, d in ev.groupby("retail")] if len(ev) else []

    parts = [
        f"# Sharp-market study S1–S5: {args.phase} (MS-043)", "",
        f"_Generated {now} · commit `{commit}` · reproduce with "
        f"`research/src/marketscope_research/run_sharp_market.py --phase {args.phase}`._", "",
        "Design pre-registered in `research/PREREGISTRATION.md` (Addendum C, committed before this code as "
        "`59bce90`). Data: `line_moves` (minute-level main lines, ADR-052). CLV is in points against "
        "Pinnacle's line at kickoff. 95% intervals resample games (5,000 draws, seed 2026). "
        "Timing describes which book changed its number first, not who bet. Hypothetical results are analysis, "
        "not betting advice.", "",
        f"**Sample:** regular-season games kicking off {start:%Y-%m-%d} to {end - pd.Timedelta(days=1):%Y-%m-%d}: "
        f"{len(games)} final games, {len(tl)} with a Pinnacle spread history, {len(closes)} with a usable close.", "",
        "## S1: who moves first? (primary: Pinnacle vs retail)", "",
        f"Matched identical spread changes (same a → b within 60 minutes). Gate: {sm.S1_MIN_PAIRS} Pinnacle–retail "
        f"pairs ({'met' if r1['gate'] else 'not met'}).", "",
        table(s1_rows, ["Reference book", "Pairs with retail", "Same-second ties", "Share where the reference moved first"]),
        "",
        f"**Primary result:** {verdict(pin['share'], r1['gate'], 'Pinnacle leads retail', 0.5)}.", "",
        "Exploratory, Pinnacle's share by time to kickoff: "
        + ", ".join(f"{k} {pct(v)}" for k, v in r1["by_hours"].items())
        + "; by size: " + ", ".join(f"{k} pt {pct(v)}" for k, v in r1["by_size"].items()) + ".", "",
        "Exploratory, how retail books follow a Pinnacle change (books that were at Pinnacle's old number):", "",
        table(follow_rows, ["Retail book", "Pinnacle changes", "≤ 5 min", "≤ 15 min", "≤ 60 min",
                            "Never before kickoff", "Median when followed"]), "",
        "## S2: stale retail lines (primary: CLV of taking the old number)", "",
        f"Events: a retail book still posting Pinnacle's old number 60 seconds after Pinnacle moved, on the side "
        f"Pinnacle moved toward, at −125 or better. {r2['events']} events in {r2['games']} games. Gate: "
        f"{sm.S2_MIN_EVENTS} events in {sm.S2_MIN_GAMES} games ({'met' if r2['gate'] else 'not met'}).", "",
        f"Mean CLV: {ci(r2['clv'])} points. **Primary result:** "
        f"{verdict(r2['clv'], r2['gate'], 'stale retail lines carry positive CLV')}.", "",
        "Exploratory:", "",
        f"- Decision 5 minutes after Pinnacle's move: {len(ev5)} events, mean CLV {mean_ci(ev5, 'clv')}.",
        f"- Moves crossing or landing on 3 or 7: {int(ev['key'].sum()) if len(ev) else 0} events, mean CLV "
        f"{mean_ci(ev[ev['key']], 'clv') if len(ev) else '–'}; others {mean_ci(ev[~ev['key']], 'clv') if len(ev) else '–'}.",
        f"- Totals, same rule: {len(ev_t)} events, mean CLV {mean_ci(ev_t, 'clv')}.",
        f"- **Hypothetical** cover rate of the S2 bets against actual results: {pct(cover['cover_rate'])} of "
        f"{cover['bets']} decided bets (pushes excluded), versus a break-even of {pct(cover['break_even'])} at the "
        "posted prices. One season's results are noisy; CLV is the yardstick.", "",
        table(s2_book, ["Retail book", "Events", "Mean CLV (points)", "Median time the old number stayed up"]), "",
        "## S3: steam (primary: does Pinnacle keep moving to the close?)", "",
        f"Steam: 3 of the 7 books move the spread the same way within 10 minutes. {len(episodes)} episodes; "
        f"{r3['episodes']} with Pinnacle on the board at the decision time and a usable close. Gate: "
        f"{sm.S3_MIN_EPISODES} ({'met' if r3['gate'] else 'not met'}).", "",
        f"Continuation from 60 s after the third move to the close: {ci(r3['continuation'])} points in the steam "
        f"direction. **Primary result:** {verdict(r3['continuation'], r3['gate'], 'steam continues to the close')}.", "",
        "Exploratory:", "",
        f"- CLV at the best line among retail books that had not moved (−125 or better): "
        f"{mean_ci(out3.dropna(subset=['retail_clv']), 'retail_clv')} points "
        f"({int(out3['retail_clv'].notna().sum())} episodes).",
        f"- A reference book among the first three movers in {pct(out3['reference_in_first_three'].mean()) if len(out3) else '–'} "
        "of episodes.",
        f"- Totals: {len(out3_t)} episodes, continuation {mean_ci(out3_t, 'continuation')}.", "",
        "## S4 and S5: limits and key numbers (exploratory, descriptive)", "",
        f"Pinnacle spread changes: {len(pc)}. Reversed by the close (the closing line back at or beyond the old number):",
        "",
        table([
            ["Limit above the game's median", int((pc["high_limit"] == True).sum()), pct(pc.loc[pc["high_limit"] == True, "reversed"].mean())],  # noqa: E712
            ["Limit at or below the median", int((pc["high_limit"] == False).sum()), pct(pc.loc[pc["high_limit"] == False, "reversed"].mean())],  # noqa: E712
            ["Crossing or landing on 3 or 7", int(pc["key"].sum()), pct(pc.loc[pc["key"], "reversed"].mean())],
            ["Other changes", int((~pc["key"]).sum()), pct(pc.loc[~pc["key"], "reversed"].mean())],
        ], ["Pinnacle changes", "Count", "Reversed by the close"]) if len(pc) else "No Pinnacle changes.", "",
        "Retail follow-through on key-number moves (S5): within 60 minutes "
        f"{pct((follow.loc[follow['key'], 'minutes'] <= 60).mean()) if len(follow) else '–'} versus "
        f"{pct((follow.loc[~follow['key'], 'minutes'] <= 60).mean()) if len(follow) else '–'} for other moves.", "",
        "## What this can't see", "",
        "Who bet or why; Circa's limits (not reported); exchange order books; moves more than 14 days before "
        "kickoff. Points-based CLV ignores price beyond the −125 bound. One season of history.", "",
    ]
    with open(args.out, "w") as f:
        f.write("\n".join(parts))
    print("\n".join(p for p in parts if "Primary result" in p or p.startswith("**Sample")))


if __name__ == "__main__":
    main()
