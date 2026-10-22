"""MS-059 engine v3 line conversion (research/PREREGISTRATION.md Addendum T). Reads the research lake and
the database read-only; `--write-params` records the adopted conversion in fair_value_params.json.

    STUDY_DATABASE_URL=... .venv/bin/python -m marketscope_research.run_ladder_fit --phase fit \
        --out reports/fair-value-v3.md --write-params
    ... --phase stability --out reports/fair-value-v3-stability.md   (weeks 7–14, once in the lake)

Uses no game outcomes: the target is the sharp books' own alternate prices and moneylines.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from . import provenance
from . import fair_value as fv
from . import ladder_fit as lf
from . import sharp_market as sm
from .data import _frame, connect
from .lake import store
from .run_cross_market import NAMES
from .run_football_studies import table

SELECTION_END = pd.Timestamp("2026-10-01", tz="UTC")  # weeks 1–3 before, weeks 4–6 from
LABELS = {"v2": "V2 additive shift", "logit": "L logit shift", "location": "M location shift",
          "scale": "S logit scale"}
TARGET_NAMES = {"spreads": "Spread alternates", "totals": "Total alternates",
                "moneyline": "Moneylines from the spread"}


def load_observations(manifest: pd.DataFrame) -> pd.DataFrame:
    con = store.connect()
    parts = []
    for f in manifest.itertuples():
        lad = con.execute("SELECT * FROM ladder WHERE fixture_id = ?", [f.fixture_id]).df()
        lad["created_at"] = pd.to_datetime(lad["created_at"], utc=True)
        parts.append(lf.fixture_observations(lad, f.kickoff).assign(event_id=f.fixture_id))
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=lf.COLUMNS + ["event_id"])


def boot(d: pd.DataFrame, col: str):
    return sm.ratio_bootstrap(d.assign(v=d[col]), "v") if len(d) else None


def fmt(e, scale=1.0, digits=4):
    return "–" if e is None else f"{scale * e.value:.{digits}f} ({scale * e.low:.{digits}f} to {scale * e.high:.{digits}f})"


def breakdown(v2: pd.DataFrame, chosen: pd.DataFrame) -> list[list]:
    """Mean KL (×1000) for V2 and the chosen candidate by distance, key numbers, book and time."""
    groups = [("All", slice(None))]
    groups += [("0.5–1 point from the main line", v2["distance"] <= 1),
               ("1.5–3 points", (v2["distance"] > 1) & (v2["distance"] <= 3)),
               ("More than 3 points", v2["distance"] > 3)]
    if v2["key"].any():
        groups += [("Spanning 3 or 7", v2["key"]), ("Not spanning 3 or 7", ~v2["key"])]
    groups += [(NAMES.get(b, b), v2["book"] == b) for b in lf.BOOKS if (v2["book"] == b).any()]
    groups += [(f"{h} h before kickoff" if h else "Close", v2["h"] == h) for h in lf.HORIZONS]
    out = []
    for label, mask in groups:
        a, b = v2[mask], chosen[mask]
        if not len(a):
            continue
        out.append([label, len(a), f"{1000 * a['kl'].mean():.2f}", f"{1000 * b['kl'].mean():.2f}",
                    f"{100 * a['abs_err'].mean():.2f}", f"{100 * b['abs_err'].mean():.2f}"])
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", choices=["fit", "stability"], default="fit")
    ap.add_argument("--out", required=True)
    ap.add_argument("--write-params", action="store_true")
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
    params_path = Path(fv.__file__).with_name("fair_value_params.json")
    params = json.loads(params_path.read_text())

    manifest = store.connect().execute("SELECT fixture_id, kickoff FROM manifest").df()
    manifest["kickoff"] = pd.to_datetime(manifest["kickoff"], utc=True)
    start = pd.Timestamp("2026-09-01", tz="UTC")
    if args.phase == "fit":
        sel_m = manifest[(manifest["kickoff"] >= start) & (manifest["kickoff"] < SELECTION_END)]
        val_m = manifest[(manifest["kickoff"] >= SELECTION_END) & (manifest["kickoff"] < sm.DISCOVERY_END)]
    else:
        sel_m = manifest.iloc[0:0]
        val_m = manifest[(manifest["kickoff"] >= sm.DISCOVERY_END) & (manifest["kickoff"] < sm.CONFIRMATION_END)]
    sel, val = load_observations(sel_m), load_observations(val_m)

    sections, conversion = [], {}
    for target in lf.TARGETS:
        s_obs, v_obs = sel[sel["market"] == target], val[val["market"] == target]
        if args.phase == "fit":
            beta_source = sel[sel["market"] == ("totals" if target == "totals" else "spreads")]
            beta, beta_losses = lf.choose_beta(beta_source, engine)
            chosen, losses = lf.select(s_obs, engine, beta)
        else:
            frozen = params.get("conversion", {}).get(target, {"method": "v2", "beta": 1.0})
            chosen, beta, losses, beta_losses = frozen["method"], frozen["beta"], {}, {}
        v2 = lf.score(v_obs, engine, "v2")
        ch = lf.score(v_obs, engine, chosen, beta)
        diff = ch.assign(d=ch["kl"] - v2["kl"])
        e_diff = boot(diff, "d")
        adopted = (args.phase == "fit" and chosen != "v2" and e_diff is not None and e_diff.value < 0
                   and e_diff.high < 0)
        conversion[target] = ({"method": chosen if adopted else "v2",
                               "beta": beta if adopted and chosen == "scale" else 1.0}
                              if args.phase == "fit" else {"method": chosen, "beta": beta})
        if args.phase == "fit":
            verdict = ("**V2 chosen on the selection games: nothing changes.**" if chosen == "v2" else
                       f"**{LABELS[chosen]} adopted as engine v3** (validation KL lower, interval below 0)."
                       if adopted else f"**V2 stays**: {LABELS[chosen]} did not beat it on validation with the "
                                       "interval below 0.")
        else:
            worse = chosen != "v2" and e_diff is not None and e_diff.low > 0
            verdict = ("**Flag:** v3 is worse than V2 on weeks 7–14 (interval above 0). The adoption stands "
                       "(Addendum T)." if worse else "No flag: v3 is not worse than V2 on weeks 7–14.")
        rows_sel = [[LABELS[m] + (f" (β = {beta:.2f})" if m == "scale" else ""), f"{1000 * v:.3f}"]
                    for m, v in losses.items()]
        sec = [f"## {TARGET_NAMES[target]}", "",
               f"Selection: {len(s_obs)} observations over {s_obs['event_id'].nunique() if len(s_obs) else 0} games. "
               f"Validation: {len(v_obs)} over {v_obs['event_id'].nunique() if len(v_obs) else 0} games.", ""]
        if rows_sel:
            sec += ["Mean KL on the selection games (×1000, lower is better):", "",
                    table(rows_sel, ["Candidate", "Mean KL ×1000"]), ""]
        if beta_losses and target != "moneyline":
            best3 = sorted(beta_losses.items(), key=lambda kv: kv[1])[:3]
            sec += ["S's β grid, best three: " + ", ".join(f"{b:.2f} ({1000 * v:.3f})" for b, v in best3) + ".", ""]
        sec += [f"Validation, {LABELS[chosen]} minus V2, mean KL ×1000: {fmt(e_diff, 1000, 3)}. "
                f"V2 {1000 * v2['kl'].mean():.3f}, {LABELS[chosen]} {1000 * ch['kl'].mean():.3f}; mean absolute "
                f"error {100 * v2['abs_err'].mean():.2f} against {100 * ch['abs_err'].mean():.2f} points."
                if len(v_obs) else "No validation observations.", "",
                verdict, ""]
        if len(v_obs):
            sec += [table(breakdown(v2, ch), ["Observations", "Count", "V2 KL ×1000", "Chosen KL ×1000",
                                              "V2 abs. error (pts)", "Chosen abs. error (pts)"]), ""]
        sections += sec

    if args.phase == "fit" and args.write_params:
        params["conversion"] = conversion
        params_path.write_text(json.dumps(params, indent=2) + "\n")

    commit = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True).strip()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    split = ("selection weeks 1–3, validation weeks 4–6" if args.phase == "fit"
             else "weeks 7–14 re-scored with the frozen choice")
    parts = [
        f"# Fair-value engine v3: line conversion ({args.phase}, MS-059)", "",
        f"_Generated {now} · commit `{commit}` · reproduce with "
        f"`research/src/marketscope_research/run_ladder_fit.py --phase {args.phase}`._", "",
        "Design pre-registered in `research/PREREGISTRATION.md` (Addendum T, committed before this code). Each sharp "
        "book's (Pinnacle, Circa, Bookmaker.eu) Shin-devigged prices at its own half-point alternates, and its own "
        "moneyline, predicted from the same book's main line by four conversions of the frozen engine v2 "
        f"distributions; loss is the binary KL divergence, game bootstrap (5,000, seed 2026); {split}. **Uses no "
        "game outcomes; this is model building, not a claim about value.**", "",
        f"**Adopted conversion:** " + ", ".join(f"{t} {conversion[t]['method']}"
                                                 + (f" (β = {conversion[t]['beta']:.2f})"
                                                    if conversion[t]["method"] == "scale" else "")
                                                 for t in lf.TARGETS) + ".", "",
        *sections,
        "## What this can't see", "",
        "Sharp alternates carry more margin than main lines, so the Shin fair price at an alternate is itself "
        "approximate. The books may share a pricing model, so agreement with them is agreement with the market's "
        "ladder, not with outcomes.", "",
    ]
    with open(args.out, "w") as fh:
        fh.write("\n".join(parts))
    provenance.write_run_record(args.out, provenance.run_record(
        "MS-059 ladder fit", [provenance.lake_dataset(pd.concat([sel_m, val_m])["fixture_id"])],
        [Path(fv.__file__).with_name("fair_value_params.json")], ["MS-058 ghost rule for main lines", "coherence rule for alternates"], {"phase": getattr(args, "phase", None)}))
    print("\n".join(p for p in parts if p.startswith("**") or p.startswith("Validation")))


if __name__ == "__main__":
    main()
