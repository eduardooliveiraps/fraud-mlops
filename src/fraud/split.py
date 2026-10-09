"""Time-based train/valid/test split by month: the model never sees the future it is tested on."""

import logging
from typing import NamedTuple

import pandas as pd

from fraud.config import SplitConfig
from fraud.schema import TARGET, TIME_COL

logger = logging.getLogger(__name__)


class Split(NamedTuple):
    train: pd.DataFrame
    valid: pd.DataFrame
    test: pd.DataFrame


def time_split(df: pd.DataFrame, cfg: SplitConfig) -> Split:
    if TIME_COL not in df.columns:
        raise ValueError(f"Column '{TIME_COL}' is required for the time split")
    months = {"train": cfg.train_months, "valid": cfg.valid_months, "test": cfg.test_months}
    parts = {}
    for name, selected in months.items():
        part = df[df[TIME_COL].isin(selected)]
        if part.empty:
            raise ValueError(f"Split '{name}' has no rows for months {list(selected)}")
        logger.info(
            "%s: months %s, %d rows, fraud rate %.4f",
            name, list(selected), len(part), part[TARGET].mean(),
        )
        parts[name] = part
    unused = sorted(set(df[TIME_COL].unique().tolist()) - {m for s in months.values() for m in s})
    if unused:
        logger.info("Months not used by any split: %s", unused)
    return Split(**parts)
