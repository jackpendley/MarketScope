"""Write the nflverse-close vs last-pregame-consensus report (aggregates only).

    STUDY_DATABASE_URL=... .venv/bin/python -m marketscope_research.run_close_check --out reports/close-vs-consensus.md
"""

from __future__ import annotations

import argparse
import os
import subprocess
from datetime import datetime, timezone

from .close_check import compare, summary
from .data import _frame, connect, load_home_spreads, load_kickoffs, load_totals
from .run_market_gate import md_table, pct

PCT_COLS = ["spread_exact", "spread_within_0.5", "spread_within_1", "same_favorite", "total_within_1"]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    dsn = os.environ.get("STUDY_DATABASE_URL")
    if not dsn:
        raise SystemExit("Set STUDY_DATABASE_URL (read-only use).")
    sources = ["the-odds-api", "oddspapi"]
    with connect(dsn) as conn:
        games = _frame(conn, """SELECT event_id::text, game_id, nflverse_close_home_spread::float8,
                                       nflverse_close_total::float8
                                FROM nfl_games WHERE event_id IS NOT NULL AND nflverse_close_home_spread IS NOT NULL
                                  AND home_score IS NOT NULL""")
        spreads, totals, kickoffs = load_home_spreads(conn, sources), load_totals(conn, sources), load_kickoffs(conn)
    df = compare(games, spreads, totals, kickoffs)
    s = summary(df)
    s.index.name = "source"
    commit = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True).strip()
    worst = df.reindex(df["spread_diff"].abs().sort_values(ascending=False).index).head(5)
    sign_ok = s.loc["all", "same_favorite"] >= 0.9 and s.loc["all", "spread_correlation"] > 0.9
    report = f"""# Data quality: nflverse closing lines vs MarketScope consensus (MS-026)

_Generated {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")} · commit `{commit}` ·
reproduce with `research/src/marketscope_research/run_close_check.py`._

nflverse publishes one closing spread and total per game (`spread_line`, positive = home favored). On ingest
MarketScope stores it as `nfl_games.nflverse_close_home_spread` = −`spread_line`, in our home orientation. This
report compares it with our **last observed pregame** board consensus (median of ≥ 3 board books) for every linked
**completed** game (a future game's nflverse line is not yet a close). The two are not the same quantity: imported games' last snapshot is 5 minutes before kickoff, live games'
can be hours earlier, and nflverse's source and timing differ from our books.

## Verdict

{"**Sign convention confirmed.**" if sign_ok else "**Sign convention NOT confirmed: investigate before using the benchmark.**"}
Correlation {s.loc["all", "spread_correlation"]:.3f}; the same team is favored in {pct(s.loc["all", "same_favorite"])} of
{int(s.loc["all", "games"])} games; spreads agree within 1 point in {pct(s.loc["all", "spread_within_1"])}.

## Agreement by source

{md_table(s, {c: "pct" for c in PCT_COLS})}

## Largest spread differences (game ids only; no prices)

{md_table(worst[["game_id", "source"]].assign(hours_before_kickoff=(worst["minutes_before_kickoff"] / 60).round(1)).assign(abs_diff=worst["spread_diff"].abs()), index=False)}
"""
    with open(args.out, "w") as fh:
        fh.write(report)
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
