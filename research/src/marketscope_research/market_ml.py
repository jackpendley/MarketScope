"""MS-046: machine learning on minute-level market state (research/PREREGISTRATION.md Addendum G,
committed before this code). Pure functions; loading and reporting live in run_market_ml.py.

G1 predicts the direction of Pinnacle's move from a decision time d to the close. G2 scores the
price-aware value of taking a retail book's number at d, against Pinnacle's no-vig close converted to
the book's line with an empirical margin distribution. All features use rows with changed_at <= d.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import sharp_market as sm
from .backtest import profit

HORIZONS = (48, 24, 6, 1)
KEY_LINES = {2.5, 3.0, 3.5, 6.5, 7.0, 7.5}
BUCKETS = ((0.0, 2.5), (3.0, 4.0), (4.5, 7.0), (7.5, 99.0))  # |closing spread|, inclusive
SEED = 2026
WALK_WEEKS = (3, 4, 5, 6)


# --- margin distribution and price-aware value (G2 target) ----------------------------------

def bucket_of(spread: float) -> int:
    """Index into BUCKETS for a (half-point) closing spread."""
    a = abs(spread)
    return 0 if a <= 2.5 else 1 if a <= 4 else 2 if a <= 7 else 3


def margin_tables(games: pd.DataFrame) -> list[pd.Series]:
    """Per spread bucket, P(favourite margin = k) from final games (home_line = closing home
    spread, margin = home minus away). Oriented to the favourite so 3 and 7 line up across games;
    a pick'em counts the home team as the favourite."""
    fav_margin = np.where(games["home_line"] <= 0, games["margin"], -games["margin"])
    b = games["home_line"].map(bucket_of)
    return [pd.Series(fav_margin[b == i]).value_counts(normalize=True).sort_index() for i in range(len(BUCKETS))]


def implied(price: int) -> float:
    return -price / (-price + 100) if price < 0 else 100 / (price + 100)


def no_vig_home(price_home: int, price_away: int) -> float:
    h, a = implied(price_home), implied(price_away)
    return h / (h + a)


def side_probabilities(table: pd.Series, close_home: float, p_home_nv: float, side: str,
                       line: float) -> tuple[float, float, float]:
    """(win, push, loss) for `side` ('home'/'away') at `line` (from that side), calibrated so the
    favourite's no-push cover probability at the close equals Pinnacle's no-vig probability."""
    home_fav = close_home <= 0
    k, pk = table.index.to_numpy(float), table.to_numpy(float)

    def fav(lf: float) -> tuple[float, float]:
        return float(pk[k + lf > 0].sum()), float(pk[k + lf == 0].sum())

    close_fav = close_home if home_fav else -close_home
    w_c, pu_c = fav(close_fav)
    p_fav_nv = p_home_nv if home_fav else 1 - p_home_nv
    delta = p_fav_nv - (w_c / (1 - pu_c) if pu_c < 1 else 0.5)
    side_is_fav = (side == "home") == home_fav
    lf = line if side_is_fav else -line
    w, pu = fav(lf)
    w = min(max(w + delta * (1 - pu), 0.0), 1 - pu)
    if side_is_fav:
        return w, pu, 1 - w - pu
    return 1 - w - pu, pu, w


def expected_value(win: float, loss: float, price: int) -> float:
    return win * profit(price) - loss


# --- point-in-time features -----------------------------------------------------------------

def _cents(a: int) -> float:
    return a + 100 if a < 0 else a - 100


def close_quote(pin: sm.Book, kickoff: pd.Timestamp) -> sm.Quote | None:
    """Pinnacle's closing quote (line and prices), under Addendum C's close rule."""
    if sm.close_line(pin, kickoff) is None:
        return None
    for q in reversed(pin.quotes[: pin.index_at(kickoff - pd.Timedelta(microseconds=1)) + 1]):
        if q is not None:
            return q
    return None


def game_features(books: dict[str, sm.Book], kickoff: pd.Timestamp, steam: pd.DataFrame) -> list[dict]:
    """One feature row per horizon at which Pinnacle is on the board (G1 units)."""
    pin = books.get("pinnacle")
    if pin is None:
        return []
    changes = pin.changes()
    rows = []
    for h in HORIZONS:
        d = kickoff - pd.Timedelta(hours=h)
        q = pin.at(d)
        if q is None:
            continue
        prev6 = pin.at(d - pd.Timedelta(hours=6))
        lim = np.log(q.limit1) if q.limit1 else np.nan
        lim6 = np.log(prev6.limit1) if prev6 is not None and prev6.limit1 else np.nan
        recent6 = [(a, b) for t, a, b, _ in changes if d - pd.Timedelta(hours=6) < t <= d]
        recent24 = [t for t, *_ in changes if d - pd.Timedelta(hours=24) < t <= d]
        retail = [b.at(d) for k, b in books.items() if k in sm.RETAIL]
        diffs = [r.point - q.point for r in retail if r is not None]
        row = {
            "h": h, "pin_line": q.point, "imbalance": _cents(q.price1) - _cents(q.price2),
            "log_limit": 0.0 if np.isnan(lim) else lim,
            "limit_change_6h": 0.0 if np.isnan(lim) or np.isnan(lim6) else lim - lim6,
            "changes_6h": len(recent6), "changes_24h": len(recent24),
            "net_dir_6h": float(sum(np.sign(b - a) for a, b in recent6)),
            "retail_mean": float(np.mean(diffs)) if diffs else 0.0,
            "retail_max": float(max(diffs)) if diffs else 0.0,
            "retail_min": float(min(diffs)) if diffs else 0.0,
            "retail_n": len(diffs),
            "suspensions_24h": sum(1 for t, qq in zip(pin.stamps, pin.quotes)
                                   if qq is None and d - pd.Timedelta(hours=24) < t <= d),
            "key": float(abs(q.point) in KEY_LINES),
        }
        for ref in ("circa", "bookmaker_eu"):
            rq = books[ref].at(d) if ref in books else None
            row[f"{ref}_diff"] = rq.point - q.point if rq is not None else 0.0
            row[f"{ref}_present"] = float(rq is not None)
        recent_steam = steam[(steam["t"] > d - pd.Timedelta(hours=24)) & (steam["t"] <= d)] if len(steam) else steam
        row["steam_24h"] = float(sum(1 if t == "away" else -1 for t in recent_steam["toward"])) if len(steam) else 0.0
        row["_d"] = d
        rows.append(row)
    return rows


G1_FEATURES = ["h", "pin_line", "imbalance", "log_limit", "limit_change_6h", "changes_6h", "changes_24h",
               "net_dir_6h", "retail_mean", "retail_max", "retail_min", "retail_n", "suspensions_24h", "key",
               "circa_diff", "circa_present", "bookmaker_eu_diff", "bookmaker_eu_present", "steam_24h"]
G2_EXTRA = ["side_diff", "price", "minutes_since_change", "at_pin_previous", "side_home"] + [
    f"book_{k}" for k in sm.RETAIL]


def build_units(tl: dict[str, dict[str, sm.Book]], games: pd.DataFrame, tables: list[pd.Series]
                ) -> tuple[pd.DataFrame, pd.DataFrame]:
    """G1 units (game, horizon) and G2 units (game, horizon, retail book, side) with targets."""
    g1, g2 = [], []
    meta = games.set_index("event_id")
    for event, books in tl.items():
        if event not in meta.index or "pinnacle" not in books:
            continue
        kick, week = meta.at[event, "kickoff"], int(meta.at[event, "week"])
        cq = close_quote(books["pinnacle"], kick)
        if cq is None:
            continue
        p_home = no_vig_home(cq.price1, cq.price2)
        table = tables[bucket_of(cq.point)]
        steam = sm.steam_episodes({event: books}, pd.Series({event: kick}))
        pin = books["pinnacle"]
        for f in game_features(books, kick, steam):
            d = f.pop("_d")
            move = cq.point - f["pin_line"]
            g1.append({"event_id": event, "week": week, **f, "y": int(np.sign(move))})
            pin_changes = [c for c in pin.changes() if c[0] <= d]
            pin_prev = pin_changes[-1][1] if pin_changes else None
            for k in sm.RETAIL:
                if k not in books:
                    continue
                rq = books[k].at(d)
                if rq is None:
                    continue
                k_changes = [t for t, *_ in books[k].changes() if t <= d]
                last = k_changes[-1] if k_changes else books[k].stamps[0]
                for side in ("home", "away"):
                    line = rq.point if side == "home" else -rq.point
                    price = rq.price1 if side == "home" else rq.price2
                    win, _push, loss = side_probabilities(table, cq.point, p_home, side, line)
                    g2.append({"event_id": event, "week": week, "book": k, "side": side, **f,
                               "side_diff": (rq.point - f["pin_line"]) * (1 if side == "home" else -1),
                               "price": price, "minutes_since_change": (d - last) / pd.Timedelta(minutes=1),
                               "at_pin_previous": float(pin_prev is not None and rq.point == pin_prev),
                               "side_home": float(side == "home"),
                               **{f"book_{b}": float(b == k) for b in sm.RETAIL},
                               "value": expected_value(win, loss, price)})
    return pd.DataFrame(g1), pd.DataFrame(g2)


# --- models and walk-forward ------------------------------------------------------------------

def classifiers():
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    return {"ridge": lambda: make_pipeline(StandardScaler(), LogisticRegression(C=1.0, max_iter=2000)),
            "gbm": lambda: HistGradientBoostingClassifier(max_depth=3, learning_rate=0.05, max_iter=200,
                                                          random_state=SEED)}


def regressors():
    from sklearn.ensemble import HistGradientBoostingRegressor
    from sklearn.linear_model import Ridge
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    return {"ridge": lambda: make_pipeline(StandardScaler(), Ridge(alpha=1.0)),
            "gbm": lambda: HistGradientBoostingRegressor(max_depth=3, learning_rate=0.05, max_iter=200,
                                                         random_state=SEED)}


CLASSES = (-1, 0, 1)


def baseline_probs(train: pd.DataFrame, test: pd.DataFrame) -> np.ndarray:
    """Class frequencies by horizon in the training weeks (one pseudo-count per class)."""
    out = np.zeros((len(test), len(CLASSES)))
    for i, h in enumerate(test["h"]):
        y = train.loc[train["h"] == h, "y"]
        counts = np.array([(y == c).sum() + 1 for c in CLASSES], float)
        out[i] = counts / counts.sum()
    return out


def model_probs(model, train: pd.DataFrame, test: pd.DataFrame) -> np.ndarray:
    m = model().fit(train[G1_FEATURES].to_numpy(float), train["y"].to_numpy())
    p = m.predict_proba(test[G1_FEATURES].to_numpy(float))
    out = np.full((len(test), len(CLASSES)), 1e-9)
    for j, c in enumerate(m.classes_):
        out[:, CLASSES.index(int(c))] = p[:, j]
    return out / out.sum(axis=1, keepdims=True)


def unit_log_loss(probs: np.ndarray, y: pd.Series) -> np.ndarray:
    idx = np.array([CLASSES.index(int(v)) for v in y])
    return -np.log(np.clip(probs[np.arange(len(idx)), idx], 1e-12, 1))


def walk_forward_g1(units: pd.DataFrame, weeks=WALK_WEEKS) -> pd.DataFrame:
    """Per test unit: log loss of each model and the baseline, trained only on earlier weeks."""
    rows = []
    for w in weeks:
        train, test = units[units["week"] < w], units[units["week"] == w]
        if train.empty or test.empty or train["y"].nunique() < 2:
            continue
        res = test[["event_id", "week", "h", "y"]].copy()
        res["baseline"] = unit_log_loss(baseline_probs(train, test), test["y"])
        for name, model in classifiers().items():
            res[name] = unit_log_loss(model_probs(model, train, test), test["y"])
        rows.append(res)
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def walk_forward_g2(units: pd.DataFrame, weeks=WALK_WEEKS) -> pd.DataFrame:
    """Per test unit: each model's predicted value, trained only on earlier weeks."""
    feats = G1_FEATURES + G2_EXTRA
    rows = []
    for w in weeks:
        train, test = units[units["week"] < w], units[units["week"] == w]
        if train.empty or test.empty:
            continue
        res = test[["event_id", "week", "h", "book", "side", "side_diff", "price", "value"]].copy()
        for name, model in regressors().items():
            m = model().fit(train[feats].to_numpy(float), train["value"].to_numpy(float))
            res[name] = m.predict(test[feats].to_numpy(float))
        rows.append(res)
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def price_aware_values(events: pd.DataFrame, tl: dict[str, dict[str, sm.Book]], kickoffs: pd.Series,
                       tables: list[pd.Series]) -> pd.Series:
    """Price-aware value (expected profit per unit at Pinnacle's no-vig close) of S2 events."""
    out = []
    for r in events.itertuples():
        cq = close_quote(tl[r.event_id]["pinnacle"], kickoffs[r.event_id])
        if cq is None:
            out.append(np.nan)
            continue
        line = r.line if r.side == "home" else -r.line
        w, _pu, lo = side_probabilities(tables[bucket_of(cq.point)], cq.point, no_vig_home(cq.price1, cq.price2),
                                        r.side, line)
        out.append(expected_value(w, lo, r.price))
    return pd.Series(out, index=events.index, dtype=float)
