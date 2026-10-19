"""ratings-v2 (MS-039, design pre-registered in design_v2.py): offensive between-season reversion
keyed on QB continuity instead of play-caller continuity. Fits, evaluates and (only if the
pre-registered rule passes) writes ratings/params_v2.json. v1's params.json is never modified.

    PYTHONPATH=src .venv/bin/python -m marketscope_football.ratings.v2 [--report reports/ratings-v2.md]
"""

from __future__ import annotations

import argparse
import json
import math
import subprocess
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from ..eval.metrics import score_table
from ..eval.run_benchmarks import prepare
from ..eval.walkforward import run_models
from .availability_adj import AvailabilityAdjuster
from .design import BURN_IN_FROM, LIKELIHOOD_SEASONS
from .design_v2 import REFERENCE, VALIDATION_SEASONS, VARIANTS, VERSION
from .engine import PARAMS_PATH, UNIT_CHANNELS, Engine, GameLayer, KalmanRatings, channel_events, load_params
from .fit import fit_channel, load_inputs
from .kalman import UnitParams
from .margin_dist import MarginDistribution
from .qb import QBAdjuster, QBParams
from .qb_fit import availability_inputs, qb_inputs

PARAMS_V2_PATH = Path(__file__).with_name("params_v2.json")
REPORT = Path(__file__).resolve().parents[3] / "reports" / "ratings-v2.md"


# ---- Flags -------------------------------------------------------------------------------------

def qb_offense_changes(games: pd.DataFrame, starters: pd.DataFrame) -> dict[tuple[int, str], bool]:
    """(season, team) -> True when the expected starter for the team's first game of the season (point
    in time) differs from its main QB of the previous regular season (most starts; ties go to the
    later starter). Seasons without a previous season or without an expected starter are absent."""
    reg = set(games.loc[games["game_type"] == "REG", "game_id"])
    st = starters.copy()
    st["reg"] = st["game_id"].isin(reg)
    main: dict[tuple[int, str], str] = {}
    played = st[st["reg"] & st["actual_qb"].notna()]
    for (season, team), g in played.groupby(["season", "team"]):
        counts = g.groupby("actual_qb").agg(n=("week", "size"), last=("kickoff_utc", "max"))
        main[(int(season), team)] = counts.sort_values(["n", "last"], ascending=False).index[0]
    out = {}
    firsts = st.sort_values("kickoff_utc").drop_duplicates(["season", "team"])
    for r in firsts.itertuples(index=False):
        prev = main.get((int(r.season) - 1, r.team))
        if prev is not None and isinstance(r.exp_qb, str):
            out[(int(r.season), r.team)] = r.exp_qb != prev
    return out


def v2_flags(variant: str, caller_flags: dict, qb_changes: dict) -> dict:
    """Season flags (offence changed, defence changed) for a v2 variant. Defence keeps v1's play-caller
    flag; offence follows the QB ("qb") or the QB or the play-caller ("qb_or_caller")."""
    if variant not in VARIANTS:
        raise ValueError(variant)
    keys = set(caller_flags) | set(qb_changes)
    out = {}
    for k in keys:
        off_c, def_c = caller_flags.get(k, (False, False))
        qb_c = qb_changes.get(k, False)
        out[k] = (qb_c or off_c if variant == "qb_or_caller" else qb_c, def_c)
    return out


def inputs(variant: str):
    """Games, observations, teams, season flags for the variant (REFERENCE = v1's play-caller flags)
    and v1's mid-season week flags."""
    games, obs, teams, sf, wf = load_inputs("model")
    if variant == REFERENCE:
        return games, obs, teams, sf, wf
    starters, _ = qb_inputs(games, int(games["season"].max()))
    return games, obs, teams, v2_flags(variant, sf, qb_offense_changes(games, starters)), wf


# ---- Fit ---------------------------------------------------------------------------------------

def _fit_channel(args) -> tuple[str, str, dict, dict]:
    variant, ch = args
    games, obs, teams, sf, wf = inputs(variant)
    events = channel_events(games, obs, sf, wf, ch, max(LIKELIHOOD_SEASONS))
    p, meta = fit_channel(events, ch, teams, None, 300)  # v1: cold start, 300 iterations ...
    if not meta["converged"]:
        p, meta = fit_channel(events, ch, teams, p, 1500)  # ... then a warm refine at 1500
    return variant, ch, p, meta


def fit_variants() -> dict[str, dict]:
    jobs = [(v, ch) for v in (REFERENCE, *VARIANTS) for ch in UNIT_CHANNELS]
    out: dict[str, dict] = {v: {"meta": {}} for v in (REFERENCE, *VARIANTS)}
    with ProcessPoolExecutor(max_workers=len(jobs)) as pool:
        for v, ch, p, m in pool.map(_fit_channel, jobs):
            out[v][ch], out[v]["meta"][ch] = p, m
            print(f"  {v} / {ch}: loglik {m['loglik']:.1f} ({m['seconds']} s, {m['message']})")
    return out


def unit_loglik(meta: dict) -> float:
    return float(sum(meta[ch]["loglik"] for ch in UNIT_CHANNELS))


def frozen_v1_loglik(v1: dict) -> float:
    """Frozen ratings-v1 parameters replayed (not refitted) on the current data and flags."""
    from .fit import replay
    from .kalman import UnitFilter

    games, obs, teams, sf, wf = inputs(REFERENCE)
    total = 0.0
    for ch in UNIT_CHANNELS:
        events = channel_events(games, obs, sf, wf, ch, max(LIKELIHOOD_SEASONS))
        total += replay(events, UnitFilter(UnitParams(**v1[ch]), teams))[0]
    return float(total)


def fit_game_layer_v2(variant: str, fitted: dict, v1: dict) -> tuple[GameLayer, float]:
    """OLS on 2016–22 of the margin on v1's final feature set (unit features, QB term, availability),
    computed from the v2 filters. v1's QB parameters and availability inputs are reused."""
    games, obs, teams, sf, wf = inputs(variant)
    _, st, layer1 = load_params("model")
    units = {ch: UnitParams(**fitted[ch]) for ch in UNIT_CHANNELS}
    units1, _, _ = load_params("model")
    if "pace" in units1:
        units["pace"] = units1["pace"]
    eng = Engine(teams, units, st, obs, sf, wf)
    last = int(games["season"].max())
    starters, qbg = qb_inputs(games, last)
    qb = QBAdjuster(QBParams(**v1["qb"]), starters, qbg, layer1.n_pass)
    av = AvailabilityAdjuster(availability_inputs(games, last))
    done = games[games["margin"].notna() & games["season"].between(BURN_IN_FROM, max(LIKELIHOOD_SEASONS))]
    cols = list(layer1.w)
    rows = []
    for (season, week), slot in done.groupby(["season", "week"], sort=True):
        eng.begin(season, week)
        if season in LIKELIHOOD_SEASONS:
            for g in slot.itertuples(index=False):
                f = {**eng.features(g.home, g.away, bool(g.neutral), layer1), "qb": qb.feature(g), **av.features(g)}
                rows.append({**{c: f[c] for c in cols}, "home": 0.0 if g.neutral else 1.0, "margin": g.margin})
        for g in slot.itertuples(index=False):
            eng.observe(g)
        qb.update(slot)
    X = pd.DataFrame(rows)
    A = X[cols + ["home"]].to_numpy(float)
    beta, *_ = np.linalg.lstsq(A, X["margin"].to_numpy(float), rcond=None)
    mae = float(np.mean(np.abs(X["margin"].to_numpy(float) - A @ beta)))
    layer = GameLayer(layer1.n_pass, layer1.n_rush, layer1.n_drives, {c: float(b) for c, b in zip(cols, beta[:-1])},
                      float(beta[-1]), layer1.total_a, layer1.total_b)
    return layer, mae


# ---- Models for the walk-forward harness -------------------------------------------------------

def build_v2_model(games: pd.DataFrame, sigma: float, params: dict, variant: str, name: str = VERSION) -> KalmanRatings:
    """A KalmanRatings with v2 filters, flags and game layer (v1's QB, availability, margin distribution)."""
    _, obs, teams, sf, wf = inputs(variant)
    units1, st, _ = load_params("model")
    units = {ch: UnitParams(**params[ch]) for ch in UNIT_CHANNELS}
    if "pace" in units1:
        units["pace"] = units1["pace"]
    layer = GameLayer(**params["game"])
    last = int(games["season"].max())
    starters, qbg = qb_inputs(games, last)
    md = params["margin_dist"]
    dist = MarginDistribution(md["scale"], md["weights"]) if md["adopted"] else None
    return KalmanRatings(name, teams, (units, st, layer), obs, sf, wf, sigma,
                         qb=QBAdjuster(QBParams(**params["qb"]), starters, qbg, layer.n_pass),
                         avail=AvailabilityAdjuster(availability_inputs(games, last)), dist=dist)


def adoption(v1_ll: float, v2_ll: float, paired: pd.Series) -> tuple[bool, list[str]]:
    """The pre-registered rule: likelihood at least v1's AND 2023–24 Δ margin MAE <= 0 AND Δ log loss <= 0."""
    checks = [("2016–22 unit log likelihood ≥ v1", v2_ll >= v1_ll),
              ("2023–24 Δ margin MAE ≤ 0", paired["d_margin_mae"] <= 0),
              ("2023–24 Δ log loss ≤ 0", paired["d_log_loss"] <= 0)]
    return all(ok for _, ok in checks), [f"{'✓' if ok else '✗'} {label}" for label, ok in checks]


def fmt(r: pd.Series, k: str, dg: int) -> str:
    return f"{r['d_' + k]:+.{dg}f} ({r['d_' + k + '_lo']:+.{dg}f} to {r['d_' + k + '_hi']:+.{dg}f})"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", default=str(REPORT))
    args = ap.parse_args()
    v1 = json.loads(PARAMS_PATH.read_text())["model"]
    fitted = fit_variants()
    v1_ll = unit_loglik(fitted[REFERENCE]["meta"])  # v1's structure, refitted on the same data
    frozen_ll = frozen_v1_loglik(v1)
    lls = {v: unit_loglik(fitted[v]["meta"]) for v in VARIANTS}
    chosen = max(VARIANTS, key=lambda v: lls[v])
    layer, mae = fit_game_layer_v2(chosen, fitted[chosen], v1)
    params = {**{ch: fitted[chosen][ch] for ch in UNIT_CHANNELS}, "game": asdict(layer), "qb": v1["qb"],
              "margin_dist": v1["margin_dist"], "continuity": chosen,
              "meta": {**fitted[chosen]["meta"], "game_in_sample_mae": mae, "variant_logliks": lls,
                       "reference_loglik": v1_ll, "frozen_v1_loglik": frozen_ll}}

    games, sigma, _ = prepare()
    from .live import build_model  # v1, unchanged
    scored = list(VALIDATION_SEASONS)
    preds = run_models(games, {"ratings-v1": lambda: build_model(games, sigma)[0],
                               VERSION: lambda: build_v2_model(games, sigma, params, chosen)}, scored)
    paired = score_table(preds, "ratings-v1").set_index("model").loc[VERSION]
    adopted, checks = adoption(v1_ll, lls[chosen], paired)
    seen = run_models(games, {"ratings-v1": lambda: build_model(games, sigma)[0],
                              VERSION: lambda: build_v2_model(games, sigma, params, chosen)}, [2025], allow_test=True)
    paired25 = score_table(seen, "ratings-v1").set_index("model").loc[VERSION]

    if adopted:
        PARAMS_V2_PATH.write_text(json.dumps({"model": params, "luck": json.loads(PARAMS_PATH.read_text())["luck"]},
                                             indent=2))
    code = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    ran = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    rho = {ch: (fitted[chosen][ch]["rho_off_same"], fitted[chosen][ch]["rho_off_changed"]) for ch in UNIT_CHANNELS}
    rho1 = {ch: (v1[ch]["rho_off_same"], v1[ch]["rho_off_changed"]) for ch in UNIT_CHANNELS}
    flags = qb_offense_changes(games, qb_inputs(games, int(games["season"].max()))[0])
    fl = pd.Series({k: v for k, v in flags.items() if k[0] in LIKELIHOOD_SEASONS})
    L = [f"# ratings-v2: QB-keyed offensive reversion (MS-039)", "",
         f"_Generated {ran} · code `{code}`. Design pre-registered in `ratings/design_v2.py` (committed before any fit)._", "",
         "## Result", "",
         f"**{'Adopted' if adopted else 'Not adopted: ratings-v1 stays the only version'}.** Rule (all must hold):", "",
         *[f"- {c}" for c in checks], "",
         "## Variant selection (2016–22 log likelihood, four unit channels)", "",
         "| Model | Offensive reversion keyed on | Log likelihood |", "|---|---|---|",
         f"| ratings-v1 frozen (replayed, not refitted) | play-caller | {frozen_ll:.1f} |",
         f"| ratings-v1 structure refitted (the reference) | play-caller | {v1_ll:.1f} |",
         *[f"| {v}{' (chosen)' if v == chosen else ''} | {'QB' if v == 'qb' else 'QB or play-caller'} | {lls[v]:.1f} |" for v in VARIANTS], "",
         f"QB changed at {int(fl.sum())} of {len(fl)} team-season boundaries in 2016–22 ({fl.mean():.0%}).", "",
         "Fitted offensive carryover (ρ same / changed):", "",
         "| Channel | v1 (play-caller) | v2 ({}) |".format(chosen), "|---|---|---|",
         *[f"| {ch} | {rho1[ch][0]:.2f} / {rho1[ch][1]:.2f} | {rho[ch][0]:.2f} / {rho[ch][1]:.2f} |" for ch in UNIT_CHANNELS], "",
         "## Validation, 2023–24 (walk-forward, paired by game; v2 minus v1, negative = better)", "",
         f"Games: {int(paired['games'])}. Δ margin MAE {fmt(paired, 'margin_mae', 3)}; Δ Brier {fmt(paired, 'brier', 4)}; "
         f"Δ log loss {fmt(paired, 'log_loss', 4)}.", "",
         "## 2025 (seen: ratings-v1's one-time test season, so not an untouched test for v2)", "",
         f"Games: {int(paired25['games'])}. Δ margin MAE {fmt(paired25, 'margin_mae', 3)}; Δ Brier {fmt(paired25, 'brier', 4)}; "
         f"Δ log loss {fmt(paired25, 'log_loss', 4)}.", "",
         f"Game layer refitted on the v2 filters (in-sample 2016–22 MAE {mae:.3f}); QB parameters, availability, margin "
         "distribution and luck reused from v1.", ""]
    Path(args.report).write_text("\n".join(L))
    print("\n".join(L[4:12]))


if __name__ == "__main__":
    main()
