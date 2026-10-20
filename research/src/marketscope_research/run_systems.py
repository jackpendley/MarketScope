"""MS-044 Wong-teaser backtest (research/PREREGISTRATION.md Addendum E). Read-only.

    STUDY_DATABASE_URL=... .venv/bin/python -m marketscope_research.run_systems \
        --out reports/systems-wong-teasers.md --web-json ../apps/web/lib/generated/wong-teasers.json

Hypothetical analysis of historical closing lines, not betting advice.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from . import backtest as bt
from . import systems as sy
from .data import _frame, connect
from .run_football_studies import table

HISTORY = range(2016, 2026)
EARLY, LATE = range(2016, 2024), range(2024, 2026)


def load(conn):
    games = _frame(conn, """
        SELECT g.game_id, g.season, g.week, g.kickoff_utc AS kickoff, g.event_id::text AS event_id,
               g.home_team AS home, g.away_team AS away,
               g.nflverse_close_home_spread::float8 AS home_line, g.nflverse_close_total::float8 AS total,
               (g.home_score - g.away_score)::float8 AS margin
        FROM nfl_games g
        WHERE g.home_score IS NOT NULL AND g.nflverse_close_home_spread IS NOT NULL AND g.season >= 2016""")
    games["kickoff"] = pd.to_datetime(games["kickoff"], utc=True)
    # Caesars' own closing lines (2026): its latest available main line before kickoff.
    caesars = _frame(conn, """
        SELECT DISTINCT ON (m.event_id, m.market_type) m.event_id::text, m.market_type, m.point::float8 AS point
        FROM line_moves m JOIN events e ON e.id = m.event_id
        WHERE m.bookmaker_key = 'williamhill_us' AND m.market_type IN ('spreads', 'totals')
          AND m.price1 IS NOT NULL AND m.changed_at < e.commence_time_utc
        ORDER BY m.event_id, m.market_type, m.changed_at DESC""")
    return games, caesars


def pct(x: float) -> str:
    return "–" if x is None or (isinstance(x, float) and np.isnan(x)) else f"{100 * x:.1f}%"


def win_rate(legs: pd.DataFrame) -> bt.Estimate | None:
    """Leg win rate, pushes counted as losses, 95% interval resampling games."""
    if legs.empty:
        return None
    return bt.cluster_mean_ci((legs["result"] == "win").astype(float), legs["game_id"])


def fmt_rate(e: bt.Estimate | None) -> str:
    return "–" if e is None else f"{100 * e.value:.1f}% ({100 * e.low:.1f}–{100 * e.high:.1f}%)"


def clears(e: bt.Estimate | None) -> str:
    """Prices whose break-even the interval's lower bound clears."""
    if e is None:
        return "–"
    ok = [p for p in sy.PRICES if e.low > bt.teaser_break_even(p)]
    return ", ".join(str(p) for p in ok) if ok else "none"


def teaser_summary(legs: pd.DataFrame, price: int, push_rule: bt.PushRule = "loses") -> dict:
    t = bt.pair_chronological(legs)
    if t.empty:
        return {"teasers": 0}
    u = bt.score_teasers(t, price, push_rule)
    roi = bt.cluster_mean_ci(u, t["season"].astype(str) + "-" + t["week"].astype(str))
    return {"teasers": len(t), "units": float(u.sum()), "roi": roi, "drawdown": bt.max_drawdown(u),
            "equity": u.cumsum().round(3).tolist(), "season": t["season"].tolist()}


def all_pairs_roi(legs: pd.DataFrame, price: int) -> float:
    p = bt.pair_all(legs)
    return float(bt.score_teasers(p, price, "loses").mean()) if len(p) else float("nan")


def caesars_games(games: pd.DataFrame, caesars: pd.DataFrame) -> pd.DataFrame:
    c = caesars.pivot(index="event_id", columns="market_type", values="point")
    g = games[(games["season"] == 2026) & games["event_id"].isin(c.index)].copy()
    g["home_line"] = g["event_id"].map(c["spreads"])
    g["total"] = g["event_id"].map(c.get("totals", pd.Series(dtype=float)))
    return g.dropna(subset=["home_line", "total"])


def record(legs: pd.DataFrame) -> str:
    r = legs["result"].value_counts()
    return f"{r.get('win', 0)}–{r.get('loss', 0)}–{r.get('push', 0)}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--web-json")
    args = ap.parse_args()
    dsn = os.environ.get("STUDY_DATABASE_URL")
    if not dsn:
        raise SystemExit("Set STUDY_DATABASE_URL (read-only use).")
    with connect(dsn) as conn:
        games, caesars = load(conn)

    hist = games[games["season"].isin(HISTORY)]
    legs = {v: sy.wong_legs(hist, v) for v in sy.VARIANTS}
    primary = win_rate(legs["V0"])
    be = bt.teaser_break_even(sy.PRIMARY_PRICE)
    if primary.low > be:
        verdict = f"**Wong legs beat the {sy.PRIMARY_PRICE} break-even** ({pct(be)})"
    elif primary.high < be:
        verdict = f"**Wong legs fall short of the {sy.PRIMARY_PRICE} break-even** ({pct(be)})"
    else:
        verdict = f"not distinguishable from the {sy.PRIMARY_PRICE} break-even ({pct(be)}): no claim"

    variant_rows = []
    for v, d in legs.items():
        e = win_rate(d)
        variant_rows.append([f"{v}: {sy.VARIANTS[v]}", len(d), fmt_rate(e), pct((d["result"] == "push").mean()),
                             clears(e)])
    stability = []
    for v, d in legs.items():
        stability.append([v, fmt_rate(win_rate(d[d["season"].isin(EARLY)])),
                          fmt_rate(win_rate(d[d["season"].isin(LATE)]))])
    roles = [[v, fmt_rate(win_rate(d[d["role"] == "favourite"])), fmt_rate(win_rate(d[d["role"] == "underdog"]))]
             for v, d in legs.items()]

    roi_rows = []
    summaries = {}
    for v, d in legs.items():
        row = [v]
        for p in sy.PRICES:
            s = teaser_summary(d, p)
            summaries[(v, p)] = s
            row.append(f"{100 * s['roi'].value:+.1f}% ({100 * s['roi'].low:+.1f} to {100 * s['roi'].high:+.1f})")
        roi_rows.append(row)
    other_rows = []
    for v, d in legs.items():
        s = summaries[(v, sy.PRIMARY_PRICE)]
        voids = teaser_summary(d, sy.PRIMARY_PRICE, "voids")
        other_rows.append([v, s["teasers"], f"{s['units']:+.1f}", f"{s['drawdown']:.1f}",
                           f"{100 * voids['roi'].value:+.1f}%", f"{100 * all_pairs_roi(d, sy.PRIMARY_PRICE):+.1f}%"])

    season_rows = []
    for season in HISTORY:
        row = [season]
        for v in ("V0", "V1"):
            d = legs[v][legs[v]["season"] == season]
            s = teaser_summary(d, sy.PRIMARY_PRICE)
            row += [len(d), pct((d["result"] == "win").mean()) if len(d) else "–",
                    f"{s.get('units', 0):+.1f}"]
        season_rows.append(row)

    # 2026 to date (hypothetical)
    g26 = games[games["season"] == 2026]
    cz = caesars_games(games, caesars)
    rows26, json26 = [], {}
    for label, src in (("nflverse close", g26), ("Caesars' closing line", cz)):
        for v in sy.VARIANTS:
            d = sy.wong_legs(src, v)
            s = teaser_summary(d, sy.PRIMARY_PRICE)
            rows26.append([label, v, len(d), record(d), pct((d["result"] == "win").mean()) if len(d) else "–",
                           s["teasers"], f"{s.get('units', 0):+.2f}",
                           f"{100 * s['roi'].value:+.1f}%" if s["teasers"] else "–"])
            json26[f"{label}|{v}"] = {"legs": len(d), "record": record(d), "teasers": s["teasers"],
                                      "units": round(s.get("units", 0.0), 2)}

    commit = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True).strip()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    be_list = ", ".join(f"{p} → {pct(bt.teaser_break_even(p))}" for p in sy.PRICES)
    parts = [
        "# Wong teasers: system backtest (MS-044)", "",
        f"_Generated {now} · commit `{commit}` · reproduce with `research/src/marketscope_research/run_systems.py`._", "",
        "Design pre-registered in `research/PREREGISTRATION.md` (Addendum E, committed before this code). "
        "Legs: a team at the nflverse closing spread of −7.5 to −8.5 or +1.5 to +2.5, teased six points through 3 "
        "and 7. A push counts as a loss for the leg win rate. 95% intervals resample games (legs) or season-weeks "
        "(teasers), 5,000 draws, seed 2026. **Hypothetical results on closing lines; not betting advice.**", "",
        f"Break-even leg win rate for a two-team teaser: {be_list}.", "",
        "## Primary: V0 leg win rate, 2016–25", "",
        f"{len(legs['V0'])} legs: {fmt_rate(primary)}. Result: {verdict}.", "",
        "## Variants", "",
        table(variant_rows, ["Variant", "Legs", "Leg win rate (95% CI)", "Pushes", "Prices whose break-even the interval clears"]),
        "", "Stability check (no parameters are fitted; this only asks whether the rate held up recently):", "",
        table(stability, ["Variant", "2016–23", "2024–25"]), "",
        "Favourites versus underdogs:", "",
        table(roles, ["Variant", "Favourites (−7.5 to −8.5)", "Underdogs (+1.5 to +2.5)"]), "",
        "## Teaser return per unit (hypothetical), chronological pairing, push loses", "",
        table(roi_rows, ["Variant"] + [str(p) for p in sy.PRICES]), "",
        f"At {sy.PRIMARY_PRICE}:", "",
        table(other_rows, ["Variant", "Teasers", "Units", "Max drawdown (units)", "ROI if a push voids",
                           "ROI, all pairs in a week"]), "",
        f"## By season at {sy.PRIMARY_PRICE} (chronological teasers, units)", "",
        table(season_rows, ["Season", "V0 legs", "V0 win", "V0 units", "V1 legs", "V1 win", "V1 units"]), "",
        "## 2026 so far (hypothetical; too few legs for any conclusion)", "",
        f"Teasers at {sy.PRIMARY_PRICE}, chronological pairing, push loses. Caesars' line is its latest main line "
        "before kickoff in `line_moves` (games imported so far).", "",
        table(rows26, ["Line", "Variant", "Legs", "W–L–P", "Leg win rate", "Teasers", "Units", "ROI"]), "",
        "## What this can't see", "",
        "Prices before the close (a line can be in range on Wednesday and out of it by Sunday); each book's actual "
        "teaser rules; limits or account restrictions. Legs are treated as independent; pairing within a week "
        "keeps the real constraint that both games must be available together.", "",
    ]
    with open(args.out, "w") as f:
        f.write("\n".join(parts))

    if args.web_json:
        os.makedirs(os.path.dirname(args.web_json), exist_ok=True)
        payload = {
            "generated": now, "commit": commit, "primaryPrice": sy.PRIMARY_PRICE,
            "breakEven": {str(p): round(bt.teaser_break_even(p), 4) for p in sy.PRICES},
            "primary": {"legs": len(legs["V0"]), "rate": round(primary.value, 4), "low": round(primary.low, 4),
                        "high": round(primary.high, 4)},
            "variants": {v: {"label": sy.VARIANTS[v], "legs": len(d),
                             **({k: round(getattr(win_rate(d), k), 4) for k in ("value", "low", "high")}
                                if len(d) else {}),
                             "roi": {str(p): round(summaries[(v, p)]["roi"].value, 4) for p in sy.PRICES},
                             "equity": summaries[(v, sy.PRIMARY_PRICE)]["equity"],
                             "equitySeason": summaries[(v, sy.PRIMARY_PRICE)]["season"]}
                         for v, d in legs.items()},
            "y2026": json26,
        }
        with open(args.web_json, "w") as f:
            json.dump(payload, f, indent=1)
    print("\n".join(parts[8:11]))


if __name__ == "__main__":
    main()
