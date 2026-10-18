"""The pre-registered data gate: is there enough labelled data to fit and test a model?"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .design import MIN_FORWARD_GAMES, MIN_GAMES, MIN_POSITIVES, MIN_TEST_GAMES, MIN_TEST_POSITIVES
from .features import FEATURES


@dataclass
class GateResult:
    games: int
    positives: int
    test_games: int
    test_positives: int
    forward_games: int
    checks: dict[str, bool]

    @property
    def passed(self) -> bool:
        return all(self.checks.values())

    @property
    def forward_ready(self) -> bool:
        return self.forward_games >= MIN_FORWARD_GAMES


def labelled(df: pd.DataFrame) -> pd.DataFrame:
    return df[df["moved"].notna() & df["split"].isin(["train", "validation", "test", "forward"])]


def evaluate_gate(df: pd.DataFrame) -> GateResult:
    lab = labelled(df)
    core = lab[lab["split"].isin(["train", "validation", "test"])]
    test = core[core["split"] == "test"]
    forward = lab[lab["split"] == "forward"]
    games, positives = core["event_id"].nunique(), int(core["moved"].sum())
    test_games, test_pos = test["event_id"].nunique(), int(test["moved"].sum())
    return GateResult(
        games=games,
        positives=positives,
        test_games=test_games,
        test_positives=test_pos,
        forward_games=forward["event_id"].nunique(),
        checks={
            f"games >= {MIN_GAMES}": games >= MIN_GAMES,
            f"positives >= {MIN_POSITIVES}": positives >= MIN_POSITIVES,
            f"test games >= {MIN_TEST_GAMES}": test_games >= MIN_TEST_GAMES,
            f"test positives >= {MIN_TEST_POSITIVES}": test_pos >= MIN_TEST_POSITIVES,
        },
    )


def split_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Rows, games, label coverage and class balance per split."""
    rows = []
    for split in ["train", "validation", "test", "forward"]:
        s = df[df["split"] == split]
        lab = s[s["moved"].notna()]
        rows.append(
            {
                "split": split,
                "weeks": ", ".join(str(w) for w in sorted(s["week"].unique())),
                "games": s["event_id"].nunique(),
                "snapshots": len(s),
                "labelled": len(lab),
                "positives": int(lab["moved"].sum()),
                "positive_rate": float(lab["moved"].mean()) if len(lab) else float("nan"),
                "toward_home": int((lab["direction"] == "home").sum()),
                "toward_away": int((lab["direction"] == "away").sum()),
            }
        )
    return pd.DataFrame(rows)


def rate_by(df: pd.DataFrame, column: str) -> pd.DataFrame:
    lab = labelled(df)
    g = lab.groupby(column)
    return pd.DataFrame({"games": g["event_id"].nunique(), "labelled": g.size(), "positive_rate": g["moved"].mean()})


def missingness(df: pd.DataFrame) -> pd.DataFrame:
    lab = labelled(df)
    return pd.DataFrame(
        {
            "missing_overall": lab[FEATURES].isna().mean(),
            "missing_imported": lab[lab["source_live"] == 0][FEATURES].isna().mean(),
            "missing_live": lab[lab["source_live"] == 1][FEATURES].isna().mean(),
        }
    )


def label_coverage(df: pd.DataFrame) -> float:
    """Share of eligible snapshots that received a label (the rest had no horizon snapshot)."""
    return float(df["moved"].notna().mean()) if len(df) else float("nan")
