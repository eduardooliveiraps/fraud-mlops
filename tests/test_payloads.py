"""Load-test payloads. CI never touches real data: `real` is tested on a synthetic Parquet."""

import pytest
from payloads import load_applications

from fraud.data import make_synthetic
from fraud.features import FEATURES
from fraud.schema import TIME_COL


def test_synthetic_is_the_default(monkeypatch):
    monkeypatch.delenv("LOAD_DATA", raising=False)
    apps = load_applications()
    assert len(apps) == 2000 and list(apps[0]) == FEATURES


def test_real_replays_only_test_months(monkeypatch, tmp_path, config_dict, write_config):
    df = make_synthetic(n_rows=3000, seed=4)  # stands in for the real Parquet
    parquet = tmp_path / "base.parquet"
    df.to_parquet(parquet)
    config_dict["data"]["parquet"] = str(parquet)
    monkeypatch.setenv("FRAUD_CONFIG", str(write_config(config_dict)))
    monkeypatch.setenv("LOAD_DATA", "real")
    apps = load_applications()
    assert len(apps) == df[TIME_COL].isin(config_dict["split"]["test_months"]).sum()
    assert list(apps[0]) == FEATURES  # no label, no month


def test_unknown_source_fails(monkeypatch):
    monkeypatch.setenv("LOAD_DATA", "prod")
    with pytest.raises(ValueError, match="LOAD_DATA must be"):
        load_applications()
