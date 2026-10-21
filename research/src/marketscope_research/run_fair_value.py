"""MS-053 fair-value engine v2: model selection and validation (research/PREREGISTRATION.md Addendum M).
Read-only. Writes the frozen engine parameters to fair_value_params.json.

    STUDY_DATABASE_URL=... .venv/bin/python -m marketscope_research.run_fair_value --out reports/fair-value-v2.md
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from . import fair_value as fv
from .data import _frame, connect
from .football_studies import RESAMPLES, SEED, Estimate
from .run_football_studies import table

PARAMS = Path(__file__).with_name("fair_value_params.json")


def load(conn) -> pd.DataFrame:
    g = _frame(conn, """
        SELECT season, nflverse_close_home_spread::float8 AS home_line, nflverse_close_total::float8 AS total,
               (home_score - away_score)::float8 AS margin, (home_score + away_score)::float8 AS points,
               nflverse_close_home_moneyline AS home_ml, nflverse_close_away_moneyline AS away_ml
        FROM nfl_games WHERE season BETWEEN 2016 AND 2025 AND home_score IS NOT NULL
          AND nflverse_close_home_spread IS NOT NULL AND nflverse_close_total IS NOT NULL""")
    return g


def diff_ci(a: np.ndarray, b: np.ndarray, resamples: int = RESAMPLES) -> Estimate:
    """Mean of a - b with a game bootstrap."""
    d = a - b
    rng = np.random.default_rng(SEED)
    boots = d[rng.integers(0, len(d), (resamples, len(d)))].mean(axis=1)
    lo, hi = np.quantile(boots, [0.025, 0.975])
    return Estimate(float(d.mean()), float(lo), float(hi), len(d))


def select(train: pd.DataFrame, test: pd.DataFrame, outcome: str) -> dict:
    h_s, h_t, scores = fv.choose_bandwidths(train, outcome)
    build = fv.margin_model if outcome == "k" else fv.total_model
    kern = fv.log_losses(build(train, h_s, h_t).pmf, test, outcome)
    base = fv.log_losses(fv.bucket_pmf(train, outcome), test, outcome)
    d = diff_ci(kern, base)
    return {"h_s": h_s, "h_t": h_t, "scores": scores, "kernel": float(kern.mean()), "bucket": float(base.mean()),
            "diff": d, "adopt": d.high < 0}


def key_calibration(train: pd.DataFrame, test: pd.DataFrame, sel: dict) -> list[list]:
    """Predicted vs observed share of favourite margins of exactly 3 and 7, by closing total (validation)."""
    kern = fv.margin_model(train, sel["h_s"], sel["h_t"])
    base = fv.bucket_pmf(train, "k")
    rows = []
    for label, lo, hi in (("total ≤ 41.5", 0, 41.5), ("42–46.5", 42, 46.5), ("≥ 47", 47, 99)):
        g = test[(test["t"] >= lo) & (test["t"] <= hi)]
        for key in (3, 7):
            pk = np.mean([kern.pmf(r.s, r.t).get(key, 0.0) for r in g.itertuples()])
            pb = np.mean([base(r.s, r.t).get(key, 0.0) for r in g.itertuples()])
            rows.append([label, key, len(g), f"{(g['k'] == key).mean():.1%}", f"{pk:.1%}", f"{pb:.1%}"])
    return rows


def moneyline_check(train, test_games: pd.DataFrame, test: pd.DataFrame, sel: dict) -> dict:
    """Model P(favourite wins) from the spread vs the devigged nflverse closing moneyline (validation)."""
    ok = test_games["home_ml"].notna() & test_games["away_ml"].notna()
    tg, tf = test_games[ok], test[ok.to_numpy()]
    kern = fv.margin_model(train, sel["h_s"], sel["h_t"])
    base = fv.bucket_pmf(train, "k")
    diffs = {"kernel": [], "bucket": []}
    for g, f in zip(tg.itertuples(), tf.itertuples()):
        p_home = fv.devig(fv.implied(g.home_ml), fv.implied(g.away_ml), "multiplicative")
        p_fav = p_home if g.home_line <= 0 else 1 - p_home
        diffs["kernel"].append(abs(fv.win_probability(kern.pmf(f.s, f.t)) - p_fav))
        diffs["bucket"].append(abs(fv.win_probability(base(f.s, f.t)) - p_fav))
    return {k: float(np.mean(v)) for k, v in diffs.items()} | {"n": len(tg)}


def devig_choice(games: pd.DataFrame) -> dict:
    ok = games["home_ml"].notna() & games["away_ml"].notna() & (games["margin"] != 0)
    g = games[ok]
    y = (g["margin"] > 0).to_numpy()
    out = {}
    for split, mask in (("2016–22", g["season"] <= 2022), ("2023–25", g["season"] >= 2023)):
        gg, yy = g[mask.to_numpy()], y[mask.to_numpy()]
        for m in fv.DEVIG_METHODS:
            p = np.array([fv.devig(fv.implied(a), fv.implied(b), m) for a, b in zip(gg["home_ml"], gg["away_ml"])])
            out[(split, m)] = -np.log(np.where(yy, p, 1 - p))
    best = min(fv.DEVIG_METHODS, key=lambda m: out[("2016–22", m)].mean())
    confirm = diff_ci(out[("2023–25", best)], out[("2023–25", "multiplicative")])
    return {"losses": {k: float(v.mean()) for k, v in out.items()}, "best": best, "confirm": confirm,
            "adopt": best if confirm.low <= 0 else "multiplicative"}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    dsn = os.environ.get("STUDY_DATABASE_URL")
    if not dsn:
        raise SystemExit("Set STUDY_DATABASE_URL (read-only use).")
    with connect(dsn) as conn:
        games = load(conn)
    f = fv.favourite_frame(games)
    train_mask = (games["season"] <= 2022).to_numpy()
    train, test = f[train_mask], f[~train_mask]

    m = select(train, test, "k")
    t = select(train, test, "pts")
    cal = key_calibration(train, test, m)
    mlc = moneyline_check(train, games[~train_mask], test, m)
    dv = devig_choice(games)

    params = {
        "margin": {"model": "kernel" if m["adopt"] else "bucket", "h_s": m["h_s"], "h_t": m["h_t"]},
        "total": {"model": "kernel" if t["adopt"] else "bucket", "h_s": t["h_s"], "h_t": t["h_t"]},
        "devig": dv["adopt"], "mix": fv.MIX, "train_seasons": "2016-2025",
    }
    PARAMS.write_text(json.dumps(params, indent=2) + "\n")

    def ci(e):
        return f"{e.value:+.4f} ({e.low:+.4f} to {e.high:+.4f})"

    commit = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True).strip()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    parts = [
        "# Fair-value engine v2: model selection (MS-053)", "",
        f"_Generated {now} · commit `{commit}` · reproduce with `research/src/marketscope_research/run_fair_value.py`._",
        "",
        "Protocol pre-registered in `research/PREREGISTRATION.md` (Addendum M, committed before this code). Bandwidths "
        "chosen by leave-one-season-out log loss on 2016–22; models fitted on 2016–22 and validated once on 2023–25; "
        "game bootstrap (5,000, seed 2026). The adopted engine is then fitted on 2016–25 for use in 2026.", "",
        f"## Margin model: {'**kernel adopted**' if m['adopt'] else '**spread buckets kept**'}", "",
        f"Bandwidths chosen: spread {m['h_s']}, total {m['h_t']}. Validation log loss of the exact favourite margin: "
        f"kernel {m['kernel']:.4f}, buckets {m['bucket']:.4f}; difference {ci(m['diff'])} ({len(test)} games).", "",
        table(cal, ["Closing total", "Margin", "Games", "Observed", "Kernel", "Buckets"]), "",
        f"Moneyline implied by the spread vs the devigged nflverse closing moneyline ({mlc['n']} games): mean "
        f"absolute difference kernel {mlc['kernel']:.3f}, buckets {mlc['bucket']:.3f}.", "",
        f"## Total-points model: {'**kernel adopted**' if t['adopt'] else '**total buckets kept**'}", "",
        f"Bandwidths chosen: spread {t['h_s']}, total {t['h_t']}. Validation log loss: kernel {t['kernel']:.4f}, "
        f"buckets {t['bucket']:.4f}; difference {ci(t['diff'])}.", "",
        f"## Devig method: **{dv['adopt']}**", "",
        table([[m_, f"{dv['losses'][('2016–22', m_)]:.4f}", f"{dv['losses'][('2023–25', m_)]:.4f}"]
               for m_ in fv.DEVIG_METHODS], ["Method", "Log loss 2016–22", "Log loss 2023–25"]), "",
        f"Chosen on 2016–22: {dv['best']}; on 2023–25 its difference from multiplicative is {ci(dv['confirm'])}.", "",
        "## Frozen parameters", "", "```json", json.dumps(params, indent=2), "```", "",
    ]
    with open(args.out, "w") as fh:
        fh.write("\n".join(parts))
    print("\n".join(parts[6:9]))


if __name__ == "__main__":
    main()
