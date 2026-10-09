import pandas as pd
import pytest

from fraud.data import csv_to_parquet, load_base, main, make_synthetic
from fraud.schema import CATEGORICAL_COLS, COLUMNS, NUMERIC_COLS, TARGET, TIME_COL


@pytest.fixture(scope="module")
def df():
    return make_synthetic()


def test_columns_match_schema(df):
    assert list(df.columns) == COLUMNS
    assert set(COLUMNS) == {TARGET, TIME_COL, *NUMERIC_COLS, *CATEGORICAL_COLS}
    for col, dtype in NUMERIC_COLS.items():
        assert df[col].dtype == dtype, col
    for col, levels in CATEGORICAL_COLS.items():
        assert pd.api.types.is_string_dtype(df[col]), col
        assert set(df[col].unique()) <= set(levels), col


def test_month_range(df):
    assert df[TIME_COL].between(0, 7).all()


def test_deterministic_for_fixed_seed():
    pd.testing.assert_frame_equal(make_synthetic(seed=1), make_synthetic(seed=1))


def test_fraud_rate(df):
    assert 0 < df[TARGET].mean() < 0.1


def test_parquet_round_trip(df, tmp_path):
    csv_path = tmp_path / "raw" / "Base.csv"
    csv_path.parent.mkdir()
    df.to_csv(csv_path, index=False)

    out = load_base(csv_to_parquet(csv_path, tmp_path / "processed" / "base.parquet"))

    assert list(out.columns) == list(df.columns)
    pd.testing.assert_series_equal(out.dtypes, df.dtypes)


def test_missing_csv(tmp_path):
    with pytest.raises(FileNotFoundError, match="Raw CSV not found"):
        csv_to_parquet(tmp_path / "Base.csv", tmp_path / "base.parquet")


def test_missing_parquet(tmp_path):
    with pytest.raises(FileNotFoundError, match="make data"):
        load_base(tmp_path / "base.parquet")


def test_main_builds_parquet_from_config(df, tmp_path, config_dict, write_config):
    csv_path, parquet_path = tmp_path / "Base.csv", tmp_path / "out" / "base.parquet"
    df.to_csv(csv_path, index=False)
    config_dict["data"] = {"raw_csv": str(csv_path), "parquet": str(parquet_path)}

    main(["--config", str(write_config(config_dict))])

    assert load_base(parquet_path).shape == df.shape


def test_main_synthetic_writes_once_and_never_overwrites(tmp_path, config_dict, write_config):
    parquet = tmp_path / "processed" / "base.parquet"
    config_dict["data"]["parquet"] = str(parquet)
    config = str(write_config(config_dict))

    main(["--config", config, "--synthetic", "300"])
    assert load_base(parquet).shape == (300, len(COLUMNS))

    with pytest.raises(FileExistsError, match="refusing to replace"):
        main(["--config", config, "--synthetic", "300"])  # e.g. the real Parquet on a laptop
