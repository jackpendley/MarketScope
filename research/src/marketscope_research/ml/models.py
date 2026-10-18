"""Baselines and logistic regression for the market-movement targets. Every model exposes
fit(train_df) -> self and predict(df) -> P(positive)."""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from .design import SMOOTHING_ROWS


def add_derived(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["abs_outlier_dev"] = out["outlier_dev"].abs()
    out["abs_pinnacle_dev"] = out["pinnacle_dev"].abs()
    return out


class Constant:
    """The training base rate for every row (the 'climatology' forecast)."""

    name = "constant (train rate)"

    def __init__(self, target: str):
        self.target = target

    def fit(self, df: pd.DataFrame) -> "Constant":
        self.rate = float(df[self.target].mean())
        return self

    def predict(self, df: pd.DataFrame) -> np.ndarray:
        return np.full(len(df), self.rate)


class RecentWeekRate(Constant):
    """The base rate of the most recent completed week in the fitting data (tracks drift)."""

    name = "recent-week rate"

    def fit(self, df: pd.DataFrame) -> "RecentWeekRate":
        last = df["week"].max()
        self.rate = float(df[df["week"] == last][self.target].mean())
        return self


class BucketRate:
    """Smoothed empirical rate per bucket of one variable (unseen buckets get the overall rate)."""

    def __init__(self, target: str, bucket_fn, name: str):
        self.target, self.bucket_fn, self.name = target, bucket_fn, name

    def fit(self, df: pd.DataFrame) -> "BucketRate":
        self.overall = float(df[self.target].mean())
        b = self.bucket_fn(df)
        g = df.groupby(b, observed=True)[self.target].agg(["sum", "count"])
        self.rates = ((g["sum"] + self.overall * SMOOTHING_ROWS) / (g["count"] + SMOOTHING_ROWS)).to_dict()
        return self

    def predict(self, df: pd.DataFrame) -> np.ndarray:
        return self.bucket_fn(df).map(self.rates).astype(float).fillna(self.overall).to_numpy()


def lead_bucket(df: pd.DataFrame) -> pd.Series:
    return pd.cut(df["hours_to_kickoff"], bins=[0, 48, 72, 120, 1e9], labels=["24-48", "48-72", "72-120", "120+"]).astype(str)


def volatility_bucket(df: pd.DataFrame) -> pd.Series:
    """Recent activity: consensus changes in the last 48 h (0, 1, 2+) x a 0.5+ move in 24 h."""
    changes = df["changes_48h"].clip(upper=2).astype(int).astype(str)
    big = (df["abs_move_24h"].fillna(0) >= 0.5).map({True: "moved", False: "flat"})
    return changes + "/" + big


def sign_bucket(column: str):
    return lambda df: np.sign(df[column].fillna(0)).astype(int).astype(str)


class Logistic:
    """Standardized logistic regression: median imputation with missing-value indicators,
    one-hot categoricals, L2 penalty C."""

    def __init__(self, target: str, numeric: list[str], categorical: list[str], C: float, name: str = "logistic regression"):
        self.target, self.numeric, self.categorical, self.C, self.name = target, numeric, categorical, C, name

    def _pipeline(self) -> Pipeline:
        steps = [("num", Pipeline([("impute", SimpleImputer(strategy="median", add_indicator=True)),
                                   ("scale", StandardScaler())]), self.numeric)]
        if self.categorical:
            steps.append(("cat", OneHotEncoder(handle_unknown="ignore"), self.categorical))
        return Pipeline([("prep", ColumnTransformer(steps)),
                         ("lr", LogisticRegression(C=self.C, max_iter=5000))])

    def fit(self, df: pd.DataFrame) -> "Logistic":
        self.pipe = self._pipeline().fit(df[self.numeric + self.categorical], df[self.target].astype(int))
        return self

    def predict(self, df: pd.DataFrame) -> np.ndarray:
        return self.pipe.predict_proba(df[self.numeric + self.categorical])[:, 1]

    def coefficients(self) -> pd.Series:
        names = self.pipe.named_steps["prep"].get_feature_names_out()
        coefs = self.pipe.named_steps["lr"].coef_[0]
        return pd.Series(coefs, index=[n.split("__", 1)[1] for n in names]).sort_values(key=np.abs, ascending=False)
