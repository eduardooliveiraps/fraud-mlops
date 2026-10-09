import numpy as np
import pytest

from fraud.data import make_synthetic
from fraud.schema import TIME_COL
from fraud.validate import validate


@pytest.fixture
def df():
    return make_synthetic(n_rows=500)


def test_valid_data_passes(df):
    assert validate(df) is df


@pytest.mark.parametrize(
    ("corrupt", "expected"),
    [
        (lambda d: d.drop(columns="income"), "income"),
        (lambda d: d.assign(extra=1), "extra"),
        (lambda d: d.assign(**{TIME_COL: d[TIME_COL].astype(float)}), "month: dtype"),
        (lambda d: d.assign(income=np.where(d.index == 3, np.nan, d["income"])), "not_nullable"),
        (lambda d: d.assign(month=-d[TIME_COL] - 1), "month: greater_than_or_equal_to(0)"),
    ],
)
def test_bad_data_fails(df, corrupt, expected):
    with pytest.raises(ValueError, match="Data validation failed") as err:
        validate(corrupt(df))
    assert expected in str(err.value)


def test_error_reports_counts_but_never_values(df):
    df.loc[:2, "payment_type"] = "SECRET_LEVEL"
    df.loc[:4, "email_is_free"] = 987654
    with pytest.raises(ValueError) as err:
        validate(df)
    message = str(err.value)
    assert "payment_type: isin" in message and "(3 failing)" in message
    assert "email_is_free: isin([0, 1]) (5 failing)" in message
    assert "SECRET_LEVEL" not in message and "987654" not in message
    assert err.value.__cause__ is None  # the original Pandera error (with values) is dropped
