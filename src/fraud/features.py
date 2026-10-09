"""Feature preparation and scoring, shared by training, the gate and serving.

Using one function everywhere prevents training/serving skew (features built differently).
"""

import numpy as np
import pandas as pd
from lightgbm import LGBMClassifier

from fraud.schema import CATEGORICAL_COLS, NUMERIC_COLS

# device_fraud_count is always 0 in BAF Base (notebooks/01_eda.py). `month` is a time marker,
# not a feature: production traffic is always a month the model has never seen.
DROPPED = ("device_fraud_count",)
FEATURES = [c for c in NUMERIC_COLS if c not in DROPPED] + list(CATEGORICAL_COLS)


def prepare_features(df: pd.DataFrame) -> pd.DataFrame:
    missing = [c for c in FEATURES if c not in df.columns]
    if missing:
        raise ValueError(f"Missing feature columns: {missing}")
    X = df[FEATURES].copy()
    for col, levels in CATEGORICAL_COLS.items():
        if not X[col].isin(levels).all():
            raise ValueError(f"Column '{col}' has values outside {levels}")
        # Fixed levels -> the same category codes in training and serving.
        X[col] = pd.Categorical(X[col], categories=levels)
    return X


def score(model: LGBMClassifier, df: pd.DataFrame) -> np.ndarray:
    """Fraud probability per row (higher = more likely fraud)."""
    return model.predict_proba(prepare_features(df))[:, 1]
