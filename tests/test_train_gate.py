"""End-to-end on synthetic data with a throwaway MLflow (SQLite in a temp dir, no server)."""

import mlflow
import numpy as np
import pytest
from mlflow import MlflowClient

from fraud.config import GateConfig, load_config
from fraud.data import make_synthetic
from fraud.features import FEATURES
from fraud.gate import compare
from fraud.schema import TARGET, TIME_COL
from fraud.train import build_model, main, train_and_register

GATE = GateConfig(min_recall_gain=0.005, max_pr_auc_drop=0.005)


@pytest.fixture
def cfg(config_dict, write_config, tmp_path, monkeypatch):
    config_dict["train"].update(n_jobs=2, early_stopping_rounds=20)
    config_dict["train"]["params"].update(n_estimators=200, learning_rate=0.1, min_child_samples=20)
    config_dict["data"]["parquet"] = str(tmp_path / "base.parquet")
    path = write_config(config_dict)
    monkeypatch.chdir(tmp_path)  # MLflow writes artifacts to ./mlruns: keep them in tmp
    monkeypatch.setenv("MLFLOW_TRACKING_URI", f"sqlite:///{tmp_path}/mlflow.db")
    return load_config(path), path


def shuffled_train_labels(df, cfg):
    """Same data, but the model cannot learn anything: a deliberately worse candidate."""
    df = df.copy()
    train = df[TIME_COL].isin(cfg.split.train_months)
    df.loc[train, TARGET] = np.random.default_rng(0).permutation(df.loc[train, TARGET].to_numpy())
    return df


def test_promotion_sequence(cfg):
    cfg, _ = cfg
    df = make_synthetic(n_rows=20_000, seed=1)
    client = MlflowClient()
    name, alias = cfg.mlflow.model_name, cfg.mlflow.champion_alias

    def run(data):
        from fraud.gate import run_gate

        version, test = train_and_register(cfg, data, tags={"data_sha256": "abc"})
        return version, run_gate(cfg, version, test)

    v1, r1 = run(shuffled_train_labels(df, cfg))
    assert r1.promoted and r1.reason == "no champion yet"

    v2, r2 = run(df)
    assert r2.promoted and r2.champion_version == v1  # real model beats the random one

    v3, r3 = run(shuffled_train_labels(df, cfg))
    assert not r3.promoted

    _, r4 = run(df)  # identical to v2: deterministic, so no gain
    assert not r4.promoted and r4.candidate == r4.champion

    assert str(client.get_registered_model(name).aliases[alias]) == v2
    tags = client.get_model_version(name, v3).tags
    assert tags["gate_decision"] == "rejected" and tags["gate_compared_to"] == v2
    assert tags["data_sha256"] == "abc"

    meta = mlflow.models.get_model_info(f"models:/{name}/{v2}").metadata
    assert meta["features"] == FEATURES
    assert len(meta["reference_fractions"]) == len(meta["reference_edges"]) + 1
    assert sum(meta["reference_fractions"]) == pytest.approx(1.0)
    assert 0 < meta["threshold"] < 1


def test_main_end_to_end_records_lineage(cfg, monkeypatch):
    cfg, path = cfg
    make_synthetic(n_rows=5000).to_parquet(cfg.data.parquet)
    monkeypatch.setenv("IMAGE_TAG", "abc1234-dirty")
    result = main(["--config", str(path)])
    assert result.promoted
    tags = MlflowClient().get_model_version(cfg.mlflow.model_name, "1").tags
    assert tags["image_tag"] == "abc1234-dirty"
    assert len(tags["data_sha256"]) == 64


def test_main_requires_tracking_uri(cfg, monkeypatch):
    _, path = cfg
    monkeypatch.delenv("MLFLOW_TRACKING_URI")
    with pytest.raises(RuntimeError, match="MLFLOW_TRACKING_URI is not set"):
        main(["--config", str(path)])


@pytest.mark.parametrize(
    ("params", "error"),
    [({"n_estimatorz": 5}, "Unknown LightGBM parameters"), ({"random_state": 1}, "must not set")],
)
def test_bad_params_fail(cfg, params, error):
    cfg, _ = cfg
    cfg.train.params.update(params)
    with pytest.raises(ValueError, match=error):
        build_model(cfg.train)


def m(recall: float, pr_auc: float) -> dict[str, float]:
    return {"recall_at_fpr": recall, "pr_auc": pr_auc}


@pytest.mark.parametrize(
    ("candidate", "champion", "promoted", "reason"),
    [
        (m(0.50, 0.20), None, True, "no champion yet"),
        (m(0.51, 0.20), m(0.50, 0.20), True, ""),
        (m(0.51, 0.196), m(0.50, 0.20), True, ""),  # small PR-AUC drop is tolerated
        (m(0.504, 0.30), m(0.50, 0.20), False, "recall gain below"),
        (m(0.60, 0.19), m(0.50, 0.20), False, "pr_auc drop above"),
    ],
)
def test_compare_rule(candidate, champion, promoted, reason):
    decision, why = compare(candidate, champion, GATE)
    assert decision is promoted and reason in why
