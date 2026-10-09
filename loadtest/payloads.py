"""Request bodies for the load test. LOAD_DATA=synthetic (default, safe for CI) or real.

`real` replays held-out test months from the local Parquet (laptop only): rows stay in memory,
are sent to the local API and are never saved or logged (dataset license).
"""

import json
import os
from pathlib import Path

from fraud.config import load_config
from fraud.data import load_base, make_synthetic
from fraud.features import FEATURES
from fraud.split import time_split

REAL_SAMPLE_ROWS = 20_000


def load_applications() -> list[dict]:
    source = os.environ.get("LOAD_DATA", "synthetic")
    if source == "synthetic":
        df = make_synthetic(n_rows=2000, seed=7)
    elif source == "real":
        cfg = load_config(Path(os.environ.get("FRAUD_CONFIG", "configs/config.yaml")))
        test = time_split(load_base(cfg.data.parquet), cfg.split).test
        df = test.sample(min(REAL_SAMPLE_ROWS, len(test)), random_state=0)
    else:
        raise ValueError(f"LOAD_DATA must be 'synthetic' or 'real', got {source!r}")
    # to_json -> plain Python types (JSON has no numpy int64)
    return json.loads(df[FEATURES].to_json(orient="records"))
