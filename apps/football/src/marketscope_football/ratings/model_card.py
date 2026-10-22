"""Generated model card for ratings-v1 (Phase 14, ADR-074).

One structured result feeds both the JSON and the Markdown, so the card cannot drift from the numbers:

- what the model is: the feature schema (feature_schema.py) and the frozen parameters' fit summary;
- the one-time 2025 test (reports/model_runs/*.json, committed when it ran);
- the live 2026 forward test: each game's last estimate before kickoff against the result and the
  nflverse close, with the same definitions as the site's /model scorecard (apps/web/lib/model-view.ts).

    DATABASE_URL=... PYTHONPATH=src .venv/bin/python -m marketscope_football.ratings.model_card   # read-only
    PYTHONPATH=src .venv/bin/python -m marketscope_football.ratings.model_card \\
        --scored tests/fixtures/synthetic_forward_test.csv --json /tmp/card.json --markdown /tmp/card.md

Model output is a model estimate, not advice; the forward test is the only prospective evidence.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import numpy as np
import pandas as pd

from .engine import PARAMS_PATH
from .feature_schema import feature_schema, schema_sha256
from .version import MODEL_VERSION

ROOT = Path(__file__).resolve().parents[3]
RECORDS = ROOT / "reports" / "model_runs"
CARD_JSON = ROOT / "reports" / "model-card-ratings-v1.json"
MODEL_CARD_MD = ROOT.parents[1] / "docs" / "MODEL_CARD.md"
BEGIN, END = "<!-- generated:ratings-v1:begin -->", "<!-- generated:ratings-v1:end -->"
MIN_CI_GAMES, MIN_CALIBRATION_GAMES = 30, 50  # as on the /model page
RESAMPLES, SEED = 5000, 2026

FORWARD_SQL = """
WITH last AS (
  SELECT DISTINCT ON (game_id) * FROM model_predictions
  WHERE model_version = %s AND predicted_at < kickoff_utc
  ORDER BY game_id, predicted_at DESC
)
SELECT g.game_id, g.season, g.week, g.kickoff_utc, g.home_score AS home_final, g.away_score AS away_final,
       p.predicted_at, p.expected_margin, p.expected_total, p.p_home,
       g.nflverse_close_home_spread::float8 AS close_home_spread, g.nflverse_close_total::float8 AS close_total,
       g.nflverse_close_home_moneyline AS close_home_ml, g.nflverse_close_away_moneyline AS close_away_ml{prov}
FROM last p JOIN nfl_games g ON g.game_id = p.game_id
WHERE g.home_score IS NOT NULL
ORDER BY g.kickoff_utc, g.game_id
"""


def no_vig_home(home_ml, away_ml) -> float | None:
    if home_ml is None or away_ml is None or pd.isna(home_ml) or pd.isna(away_ml) or 0 in (home_ml, away_ml):
        return None
    implied = lambda ml: -ml / (-ml + 100) if ml < 0 else 100 / (ml + 100)  # noqa: E731
    h, a = implied(home_ml), implied(away_ml)
    return h / (h + a)


def _ci(diffs: np.ndarray) -> list[float] | None:
    if len(diffs) < MIN_CI_GAMES:
        return None
    rng = np.random.default_rng(SEED)
    means = diffs[rng.integers(0, len(diffs), (RESAMPLES, len(diffs)))].mean(axis=1)
    lo, hi = np.quantile(means, [0.025, 0.975])
    return [float(lo), float(hi)]


def _paired(model: list[float], close: list[float]) -> dict | None:
    if not model:
        return None
    m, c = np.array(model), np.array(close)
    return {"games": len(m), "model": float(m.mean()), "close": float(c.mean()), "diff": float((m - c).mean()),
            "ci": _ci(m - c)}


def forward_metrics(scored: pd.DataFrame) -> dict:
    """The /model scorecard, computed from the same rows (one per final game: the last pre-kickoff estimate)."""
    if not len(scored):
        return {"games": 0}
    margin = scored["home_final"] - scored["away_final"]
    home_win = np.where(margin > 0, 1.0, np.where(margin < 0, 0.0, 0.5))
    wc = scored["close_home_spread"].notna()
    probs = [no_vig_home(h, a) for h, a in zip(scored["close_home_ml"], scored["close_away_ml"])]
    wp = np.array([p is not None for p in probs])
    wt = scored["expected_total"].notna() & scored["close_total"].notna()
    total = scored["home_final"] + scored["away_final"]
    decided = (margin != 0) & (scored["expected_margin"] != 0)
    out = {
        "games": int(len(scored)),
        "weeks": int(scored[["season", "week"]].drop_duplicates().shape[0]),
        "first_game": str(scored["kickoff_utc"].min()), "last_game": str(scored["kickoff_utc"].max()),
        "margin_mae": float((scored["expected_margin"] - margin).abs().mean()),
        "margin_vs_close": _paired(list((scored["expected_margin"] - margin)[wc].abs()),
                                   list((-scored["close_home_spread"] - margin)[wc].abs())),
        "brier_vs_close": _paired(list(((scored["p_home"] - home_win) ** 2)[wp]),
                                  [(p - w) ** 2 for p, w in zip(probs, home_win) if p is not None]),
        "total_vs_close": _paired(list((scored["expected_total"] - total)[wt].abs()),
                                  list((scored["close_total"] - total)[wt].abs())),
        "favourite_won": {"won": int((np.sign(scored["expected_margin"]) == np.sign(margin))[decided].sum()),
                          "decided": int(decided.sum())},
        "calibration": None,
    }
    if len(scored) >= MIN_CALIBRATION_GAMES:
        b = np.minimum(4, np.floor(scored["p_home"] * 5)).astype(int)
        out["calibration"] = [{"bin": f"{k * 20}–{k * 20 + 20}%", "games": int((b == k).sum()),
                               "mean_p": float(scored["p_home"][b == k].mean()),
                               "home_win_rate": float(home_win[b == k].mean())}
                              for k in range(5) if (b == k).any()]
    if "params_sha256" in scored:
        out["rows_with_provenance"] = int(scored["params_sha256"].notna().sum())
    return out


def build_card(scored: pd.DataFrame, source: str) -> dict:
    params = json.loads(PARAMS_PATH.read_text())["model"]
    records = [json.loads(p.read_text()) for p in sorted(RECORDS.glob(f"{MODEL_VERSION}-*.json"))]
    test = next((r for r in records if r["run_kind"] == "test"), None)
    schema = feature_schema()
    return {
        "model_version": MODEL_VERSION,
        "params_sha256": schema["params_sha256"],
        "feature_schema_sha256": schema_sha256(schema),
        "features": [{k: f[k] for k in ("name", "weight", "unit", "available")} for f in schema["features"]],
        "home_field": schema["home_field"]["weight"],
        "fit": {"seasons": "2016–22 (likelihood); game layer by OLS on the tuning seasons",
                "games": params["meta"]["game"]["games"], "in_sample_margin_mae": params["meta"]["game"]["mae"]},
        "evaluation_history": [
            "2023–24: validation seasons; they shaped factor selection and the margin distribution, so they "
            "are not an unbiased test.",
            "2025: evaluated exactly once with the frozen parameters (the test record below); not reusable as "
            "a test for any later model.",
            "2026: the live forward test, append-only estimates written before kickoff; the only prospective "
            "evidence.",
        ],
        "test_2025": None if test is None else {
            "games": test["games"], "ran_at": test["ran_at"], "code_sha": test["code_sha"],
            "models": {name: {k: m[k] for k in ("margin_mae", "margin_mae_lo", "margin_mae_hi", "brier", "log_loss")
                              if k in m}
                       for name, m in test["metrics"].items() if isinstance(m, dict) and "margin_mae" in m},
        },
        "forward_2026": {"source": source, **forward_metrics(scored)},
    }


def _f(x, d=2):
    return "–" if x is None else f"{x:.{d}f}"


def render(card: dict) -> str:
    fw = card["forward_2026"]
    lines = [BEGIN, "", "## 2. MarketScope Ratings: ratings-v1 (generated)", "",
             f"_Generated by `marketscope_football.ratings.model_card` from `{CARD_JSON.relative_to(ROOT.parents[1])}`; "
             "do not edit by hand. Model output is a model estimate, not advice._", "",
             f"- **Version:** `{card['model_version']}`, parameters `{card['params_sha256'][:12]}` (frozen, ADR-039), "
             f"feature schema `{card['feature_schema_sha256'][:12]}`.",
             f"- **Model:** a Kalman-filtered team-unit model; expected home margin = Σ weight × feature + "
             f"{card['home_field']:.2f} home field. Fitted on {card['fit']['seasons']} ({card['fit']['games']} games, "
             f"in-sample margin MAE {card['fit']['in_sample_margin_mae']:.2f}).", "",
             "| Feature | Weight | Unit | Available |", "|---|---|---|---|"]
    lines += [f"| {f['name']} | {f['weight']:+.3f} | {f['unit']} | {f['available']} |" for f in card["features"]]
    lines += ["", "**Evaluation history (what each period may and may not claim):**", ""]
    lines += [f"- {e}" for e in card["evaluation_history"]]
    t = card["test_2025"]
    if t:
        lines += ["", f"### One-time 2025 test ({t['games']} games, run {t['ran_at'][:10]})", "",
                  "| Model | Margin MAE (95% CI) | Brier | Log loss |", "|---|---|---|---|"]
        for name, m in t["models"].items():
            lines.append(f"| {name} | {_f(m.get('margin_mae'))} ({_f(m.get('margin_mae_lo'))}–{_f(m.get('margin_mae_hi'))})"
                         f" | {_f(m.get('brier'), 3)} | {_f(m.get('log_loss'), 3)} |")
    weeks = fw.get("weeks")
    span = f", {weeks} week{'s' if weeks != 1 else ''}, first game {fw['first_game'][:10]}" if weeks else ""
    lines += ["", f"### Live 2026 forward test ({fw['games']} final games{span})", ""]
    if fw["games"]:
        def pm(name, d=2):
            m = fw[name]
            if m is None:
                return "–"
            ci = f" (95% CI {m['ci'][0]:+.{d}f} to {m['ci'][1]:+.{d}f})" if m["ci"] else " (CI after 30 games)"
            return f"model {m['model']:.{d}f}, close {m['close']:.{d}f}, difference {m['diff']:+.{d}f}{ci}"
        lines += [f"- Margin MAE: {pm('margin_vs_close')}. Negative favours the model.",
                  f"- Brier: {pm('brier_vs_close', 3)}.", f"- Total MAE: {pm('total_vs_close')}.",
                  f"- The model's favourite won {fw['favourite_won']['won']} of {fw['favourite_won']['decided']} decided games."]
        if fw["calibration"]:
            lines += ["", "| P(home win) bin | Games | Mean estimate | Home win rate |", "|---|---|---|---|"]
            lines += [f"| {b['bin']} | {b['games']} | {b['mean_p']:.2f} | {b['home_win_rate']:.2f} |"
                      for b in fw["calibration"]]
        else:
            lines.append(f"- Calibration table after {MIN_CALIBRATION_GAMES} games.")
    lines += ["", "**Limitations.** The closing line is a strong benchmark the model is not expected to beat (R4); "
              "a margin error close to the market's is the realistic goal. Small samples: intervals are wide until "
              "late in the season. Injuries and quarterback changes enter only through published reports.", "", END]
    return "\n".join(lines)


def write_markdown(card: dict, path: Path = MODEL_CARD_MD) -> None:
    text = path.read_text()
    block = render(card)
    if BEGIN in text:
        start, end = text.index(BEGIN), text.index(END) + len(END)
        text = text[:start] + block + text[end:]
    else:
        raise ValueError(f"markers {BEGIN} … {END} not found in {path}")
    path.write_text(text)


def load_scored(args) -> tuple[pd.DataFrame, str]:
    if args.scored:
        return pd.read_csv(args.scored), f"file:{Path(args.scored).name}"
    import psycopg

    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        raise SystemExit("Set DATABASE_URL (read-only use) or pass --scored.")
    with psycopg.connect(dsn) as conn:
        conn.read_only = True
        # The provenance columns exist from migration 0021 (ADR-074); older databases lack them.
        has_prov = conn.execute("""SELECT count(*) FROM information_schema.columns
                                   WHERE table_name = 'model_predictions' AND column_name = 'params_sha256'""").fetchone()[0]
        sql = FORWARD_SQL.format(prov=", p.params_sha256, p.feature_schema_sha256" if has_prov else "")
        with conn.cursor() as cur:
            cur.execute(sql, (MODEL_VERSION,))
            df = pd.DataFrame(cur.fetchall(), columns=[c.name for c in cur.description])
    return df, "database"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scored", help="CSV of scored estimates instead of the database (e.g. the synthetic demo)")
    ap.add_argument("--json", default=str(CARD_JSON))
    ap.add_argument("--markdown", default=str(MODEL_CARD_MD))
    args = ap.parse_args()
    scored, source = load_scored(args)
    card = build_card(scored, source)
    Path(args.json).write_text(json.dumps(card, indent=2, default=str) + "\n")
    md = Path(args.markdown)
    if not md.exists():
        md.write_text(f"{BEGIN}\n{END}\n")
    write_markdown(card, md)
    print(f"model card: {card['forward_2026']['games']} forward-test games -> {args.json}, {args.markdown}")


if __name__ == "__main__":
    main()
