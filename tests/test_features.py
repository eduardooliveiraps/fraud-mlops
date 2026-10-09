import pytest

from fraud.data import make_synthetic
from fraud.features import FEATURES, prepare_features
from fraud.schema import CATEGORICAL_COLS, TARGET, TIME_COL


def test_feature_columns():
    assert TARGET not in FEATURES and TIME_COL not in FEATURES
    assert "device_fraud_count" not in FEATURES
    assert len(FEATURES) == len(set(FEATURES)) == 29


def test_categories_are_fixed_even_if_some_levels_are_absent():
    df = make_synthetic(n_rows=50).assign(payment_type="AA")
    X = prepare_features(df)
    assert list(X.columns) == FEATURES
    for col, levels in CATEGORICAL_COLS.items():
        assert list(X[col].cat.categories) == levels


def test_unknown_category_fails():
    df = make_synthetic(n_rows=50).assign(device_os="beos")
    with pytest.raises(ValueError, match="'device_os' has values outside"):
        prepare_features(df)


def test_missing_feature_fails():
    with pytest.raises(ValueError, match="Missing feature columns: \\['income'\\]"):
        prepare_features(make_synthetic(n_rows=50).drop(columns="income"))
