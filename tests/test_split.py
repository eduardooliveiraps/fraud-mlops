import logging

import pytest

from fraud.config import SplitConfig
from fraud.data import make_synthetic
from fraud.schema import TIME_COL
from fraud.split import time_split

CFG = SplitConfig(train_months=(0, 1, 2, 3, 4), valid_months=(5,), test_months=(6, 7))


@pytest.fixture(scope="module")
def df():
    return make_synthetic(n_rows=4000)


def test_each_split_has_only_its_months(df):
    split = time_split(df, CFG)
    assert set(split.train[TIME_COL]) == set(CFG.train_months)
    assert set(split.valid[TIME_COL]) == set(CFG.valid_months)
    assert set(split.test[TIME_COL]) == set(CFG.test_months)
    assert len(split.train) + len(split.valid) + len(split.test) == len(df)


def test_unused_months_are_dropped_and_logged(df, caplog):
    cfg = SplitConfig(train_months=(1, 2), valid_months=(3,), test_months=(4,))
    with caplog.at_level(logging.INFO, logger="fraud.split"):
        split = time_split(df, cfg)
    assert len(split.train) + len(split.valid) + len(split.test) < len(df)
    assert "Months not used by any split: [0, 5, 6, 7]" in caplog.text
    assert "fraud rate" in caplog.text  # aggregates are logged, never rows


def test_empty_split_fails(df):
    with pytest.raises(ValueError, match="Split 'test' has no rows for months \\[6, 7\\]"):
        time_split(df[df[TIME_COL] <= 5], CFG)


def test_missing_time_column_fails(df):
    with pytest.raises(ValueError, match="Column 'month' is required"):
        time_split(df.drop(columns=TIME_COL), CFG)
