"""MS-046 market ML, G1 and G2 (research/PREREGISTRATION.md Addendum G). Read-only.

    STUDY_DATABASE_URL=... .venv/bin/python -m marketscope_research.run_market_ml --phase discovery \
        --out reports/market-ml-discovery.md

Discovery: walk-forward by week inside weeks 1–6. Confirmation (after 2026-12-16): models chosen and
fitted on weeks 1–6, scored once on weeks 7–14. Analysis of closing-line value, not betting advice.
"""

from __future__ import annotations

import argparse
import os
import subprocess
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from . import market_ml as ml
from . import sharp_market as sm
from .data import _frame, connect
from .run_football_studies import ci, table

NAMES = {"draftkings": "DraftKings", "fanduel": "FanDuel", "williamhill_us": "Caesars", "hardrockbet": "Hard Rock"}


def load(conn):
    games = _frame(conn, """
        SELECT e.id::text AS event_id, e.commence_time_utc AS kickoff, g.week
        FROM events e JOIN nfl_games g ON g.event_id = e.id
        WHERE g.season = 2026 AND g.game_type = 'REG' AND g.home_score IS NOT NULL
          AND e.commence_time_utc < %s""", (sm.CONFIRMATION_END,))
    games["kickoff"] = pd.to_datetime(games["kickoff"], utc=True)
    moves = _frame(conn, """
        SELECT event_id::text, bookmaker_key, changed_at, point::float8 AS point, price1, price2,
               limit1::float8 AS limit1
        FROM line_moves WHERE market_type = 'spreads' AND event_id = ANY(%s::uuid[])""",
                   (list(games["event_id"]),))
    moves["changed_at"] = pd.to_datetime(moves["changed_at"], utc=True)
    history = _frame(conn, """
        SELECT nflverse_close_home_spread::float8 AS home_line, (home_score - away_score)::float8 AS margin
        FROM nfl_games WHERE season BETWEEN 2016 AND 2025 AND game_type = 'REG' AND home_score IS NOT NULL
          AND nflverse_close_home_spread IS NOT NULL""")
    return games, moves, history


def g1_scores(train: pd.DataFrame, test: pd.DataFrame, model_name: str) -> pd.DataFrame:
    res = test[["event_id", "week", "h", "y"]].copy()
    res["baseline"] = ml.unit_log_loss(ml.baseline_probs(train, test), test["y"])
    probs = ml.model_probs(ml.classifiers()[model_name], train, test)
    res["model"] = ml.unit_log_loss(probs, test["y"])
    res["pred"] = [ml.CLASSES[i] for i in probs.argmax(axis=1)]
    return res


def g2_scores(train: pd.DataFrame, test: pd.DataFrame, model_name: str) -> pd.DataFrame:
    feats = ml.G1_FEATURES + ml.G2_EXTRA
    res = test[["event_id", "week", "h", "book", "side", "side_diff", "price", "value"]].copy()
    m = ml.regressors()[model_name]().fit(train[feats].to_numpy(float), train["value"].to_numpy(float))
    res["pred"] = m.predict(test[feats].to_numpy(float))
    return res


def ridge_coefficients(units: pd.DataFrame, feats: list[str], target: str, classifier: bool) -> list[tuple[str, float]]:
    """Standardised ridge coefficients on all discovery units, for interpretation (exploratory)."""
    model = (ml.classifiers() if classifier else ml.regressors())["ridge"]().fit(
        units[feats].to_numpy(float), units[target].to_numpy())
    est = model[-1]
    coef = est.coef_[list(est.classes_).index(-1)] - est.coef_[list(est.classes_).index(1)] if classifier else est.coef_
    return sorted(zip(feats, coef), key=lambda x: -abs(x[1]))[:8]


def mean_ci(df: pd.DataFrame, col: str) -> str:
    return ci(sm.ratio_bootstrap(df.assign(_v=df[col].astype(float)), "_v"), 3) if len(df) else "–"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", choices=["discovery", "confirmation"], default="discovery")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    dsn = os.environ.get("STUDY_DATABASE_URL")
    if not dsn:
        raise SystemExit("Set STUDY_DATABASE_URL (read-only use).")
    with connect(dsn) as conn:
        games, moves, history = load(conn)

    with_pin = moves.loc[moves["bookmaker_key"] == "pinnacle", "event_id"].unique()
    tl = sm.timelines(moves[moves["event_id"].isin(with_pin)])
    tables = ml.margin_tables(history)
    g1, g2 = ml.build_units(tl, games, tables)
    disc_weeks = set(games.loc[games["kickoff"] < sm.DISCOVERY_END, "week"])
    d1, d2 = g1[g1["week"].isin(disc_weeks)], g2[g2["week"].isin(disc_weeks)]

    # Model choice: pooled walk-forward loss inside discovery (always, so confirmation reuses it).
    wf1, wf2 = ml.walk_forward_g1(d1), ml.walk_forward_g2(d2)
    choice1 = min(("ridge", "gbm"), key=lambda m: wf1[m].mean())
    mse = {m: float(((wf2[m] - wf2["value"]) ** 2).mean()) for m in ("ridge", "gbm")}
    choice2 = min(mse, key=mse.get)

    if args.phase == "discovery":
        s1 = wf1.assign(model=wf1[choice1], pred=np.nan)
        s2 = wf2.assign(pred=wf2[choice2])
        sample = f"walk-forward inside weeks 1–6 (train on earlier weeks, predict weeks {ml.WALK_WEEKS[0]}–{ml.WALK_WEEKS[-1]})"
    else:
        c1, c2 = g1[~g1["week"].isin(disc_weeks)], g2[~g2["week"].isin(disc_weeks)]
        s1, s2 = g1_scores(d1, c1, choice1), g2_scores(d2, c2, choice2)
        sample = "models chosen and fitted on weeks 1–6, scored once on weeks 7–14"

    delta = s1.assign(d=s1["model"] - s1["baseline"])
    e1 = sm.ratio_bootstrap(delta, "d") if len(delta) else None
    sel = s2[s2["pred"] > 0]
    rule = s2[(s2["side_diff"] > 0) & (s2["price"] >= sm.WORST_PRICE)]
    e2 = sm.ratio_bootstrap(sel.assign(v=sel["value"]), "v") if len(sel) else None

    def verdict(e, claim, below=False):
        if e is None:
            return "inconclusive (no units)"
        hit = e.high < 0 if below else e.low > 0
        opp = e.low > 0 if below else e.high < 0
        tag = " (discovery result; confirmation on weeks 7–14 decides)" if args.phase == "discovery" else ""
        return f"**{claim}**{tag}" if hit else ("**the opposite**" + tag if opp else "not distinguishable: no claim")

    by_h1 = [[h, len(d), f"{d['model'].mean():.3f}", f"{d['baseline'].mean():.3f}",
              f"{(d['model'] - d['baseline']).mean():+.3f}"] for h, d in delta.groupby("h", sort=False)]
    by_h2 = [[h, len(d), int((d["pred"] > 0).sum()), mean_ci(d[d["pred"] > 0], "value"),
              mean_ci(d[(d["side_diff"] > 0) & (d["price"] >= sm.WORST_PRICE)], "value")]
             for h, d in s2.groupby("h", sort=False)]
    by_book = [[NAMES[b], int((d["pred"] > 0).sum()), mean_ci(d[d["pred"] > 0], "value")] for b, d in s2.groupby("book")]
    coef1 = ridge_coefficients(d1, ml.G1_FEATURES, "y", True)
    coef2 = ridge_coefficients(d2, ml.G1_FEATURES + ml.G2_EXTRA, "value", False)

    # Exploratory (added after the first run): S2 stale numbers re-scored with price-aware value.
    phase_games = games[games["kickoff"] < sm.DISCOVERY_END] if args.phase == "discovery" else \
        games[games["kickoff"] >= sm.DISCOVERY_END]
    kicks = games.set_index("event_id")["kickoff"]
    tl_p = {e: b for e, b in tl.items() if e in set(phase_games["event_id"])}
    closes = {e: x for e, b in tl_p.items() if (x := sm.close_line(b.get("pinnacle"), kicks[e])) is not None}
    s2ev = sm.s2_events(tl_p, kicks, closes)
    s2ev["value"] = ml.price_aware_values(s2ev, tl_p, kicks, tables)
    s2_rows = [[label, len(d), f"{d['clv'].mean():+.2f}", mean_ci(d, "value")] for label, d in (
        ("All stale numbers", s2ev), ("At −110 or better", s2ev[s2ev["price"] >= -110]),
        ("At −111 to −125", s2ev[s2ev["price"] < -110]), ("Crossing or landing on 3 or 7", s2ev[s2ev["key"]]))]

    commit = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True).strip()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    parts = [
        f"# Market ML on minute-level state: {args.phase} (MS-046)", "",
        f"_Generated {now} · commit `{commit}` · reproduce with "
        f"`research/src/marketscope_research/run_market_ml.py --phase {args.phase}`._", "",
        "Design pre-registered in `research/PREREGISTRATION.md` (Addendum G, committed before this code). Units at "
        "48, 24, 6 and 1 hours before kickoff; features use only line changes up to that time. Intervals resample "
        "games (5,000 draws, seed 2026). Value is closing-line value against Pinnacle's no-vig close, not results. "
        "**Analysis, not betting advice.**", "",
        f"**Sample:** {sample}. G1 units: {len(s1)}; G2 units: {len(s2)}. Models chosen by discovery walk-forward "
        f"loss: G1 `{choice1}` (log loss ridge {wf1['ridge'].mean():.3f}, gbm {wf1['gbm'].mean():.3f}); G2 `{choice2}` "
        f"(MSE ridge {mse['ridge']:.4f}, gbm {mse['gbm']:.4f}).", "",
        "## G1: can the model predict Pinnacle's direction to the close?", "",
        f"Log loss, model minus class-frequency baseline (negative = better): {ci(e1, 3)}. "
        f"**Primary result:** {verdict(e1, 'the model predicts Pinnacle’s direction better than the baseline', below=True)}.", "",
        table(by_h1, ["Hours before kickoff", "Units", "Model log loss", "Baseline log loss", "Difference"]), "",
        f"Class shares (toward home / no change / toward away): "
        + " / ".join(f"{(s1['y'] == c).mean():.0%}" for c in ml.CLASSES) + ".", "",
        "Exploratory, standardised ridge coefficients on all discovery units (positive = more likely toward "
        "home): " + ", ".join(f"{n} {v:+.2f}" for n, v in coef1) + ".", "",
        "## G2: which retail numbers carry value against Pinnacle's close?", "",
        f"Positions: units the model scores above 0. {len(sel)} of {len(s2)}. Mean realised value per unit staked: "
        f"{ci(e2, 3)}. **Primary result:** {verdict(e2, 'model-selected retail numbers carry positive value')}.", "",
        f"Comparison (no model): book's line better than Pinnacle's for the side at −125 or better: {len(rule)} units, "
        f"mean value {mean_ci(rule, 'value')}. All units: {mean_ci(s2, 'value')} (the bookmakers' margin).", "",
        table(by_h2, ["Hours before kickoff", "Units", "Model positions", "Model positions' value", "Rule's value"]), "",
        table(by_book, ["Retail book", "Model positions", "Value"]), "",
        "Exploratory, standardised ridge coefficients (G2, value per unit): "
        + ", ".join(f"{n} {v:+.3f}" for n, v in coef2) + ".", "",
        "## Stale numbers re-scored with price (exploratory, added after the first run)", "",
        "MS-043's S2 measured stale retail numbers in points, ignoring the price. Re-scored with the same "
        "price-aware value as G2 (expected profit per unit at Pinnacle's no-vig close):", "",
        table(s2_rows, ["S2 cases", "Count", "Points CLV", "Price-aware value per unit"]), "",
        "Retail books keep the old number but charge for it: in points it looks like a head start, at the price it "
        "is not. Registered as Addendum H for the confirmation weeks before any of them were played.", "",
        "## What this can't see", "",
        "Who bet; point-in-time injury news before 2026-10-18; exchange order books; moves more than 14 days out. "
        "Value is closing-line value (expected profit at Pinnacle's no-vig close), not results. The margin model "
        "is an empirical table by spread bucket, oriented to the favourite, calibrated to Pinnacle's close.", "",
    ]
    with open(args.out, "w") as f:
        f.write("\n".join(parts))
    print("\n".join(p for p in parts if "Primary result" in p or p.startswith("**Sample")))


if __name__ == "__main__":
    main()
