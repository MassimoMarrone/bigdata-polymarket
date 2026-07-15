"""Unit tests for the Task 3 feature engineering (fast, synthetic data)."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))

from predict import social_features  # noqa: E402


def _posts(mid: str, outcome: str, n: int) -> pd.DataFrame:
    ts = pd.date_range("2025-01-01", periods=n, freq="D", tz="UTC")
    return pd.DataFrame({
        "market_id": mid, "published_at": ts,
        "text": ["some text"] * n,
        "engagement": range(n), "views": 0, "followers": 10,
        "sentiment": ["positive"] * (n // 2) + ["negative"] * (n - n // 2),
        "sentiment_score": [0.5] * (n // 2) + [-0.5] * (n - n // 2),
        "resolution_outcome": outcome,
        "resolution_date": pd.Timestamp("2025-03-01", tz="UTC"),
        "category": "politics",
    })


def test_social_features_one_row_per_contract():
    df = pd.concat([_posts("a", "Yes", 10), _posts("b", "No", 4)])
    out = social_features(df)
    assert len(out) == 2
    assert set(out["y"]) == {0, 1}


def test_social_features_values():
    out = social_features(_posts("a", "Yes", 10)).iloc[0]
    assert out["n_posts"] == 10
    assert out["frac_pos"] == 0.5
    assert abs(out["sent_mean"]) < 1e-9  # half +0.5, half -0.5
    assert out["y"] == 1
