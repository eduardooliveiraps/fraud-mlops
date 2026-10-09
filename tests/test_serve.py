"""Scoring API against a small model registered in a throwaway MLflow (no server)."""

import json
import math
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from fraud import serve
from fraud.config import load_config
from fraud.data import make_synthetic
from fraud.features import FEATURES, score
from fraud.registry import main as registry_main
from fraud.train import train_and_register


@pytest.fixture(scope="module")
def registered(tmp_path_factory):
    """Train and register one small model; yields (config path, pinned URI)."""
    tmp = tmp_path_factory.mktemp("serve")
    cfg_dict = yaml.safe_load(Path("configs/config.yaml").read_text())
    cfg_dict["train"].update(n_jobs=2, early_stopping_rounds=20)
    cfg_dict["train"]["params"].update(n_estimators=100, learning_rate=0.1, min_child_samples=20)
    cfg_dict["monitoring"]["psi_window"] = 20  # small, so tests can fill it
    cfg_path = tmp / "config.yaml"
    cfg_path.write_text(yaml.safe_dump(cfg_dict))
    with pytest.MonkeyPatch.context() as mp:
        mp.chdir(tmp)  # MLflow artifacts go to ./mlruns
        mp.setenv("MLFLOW_TRACKING_URI", f"sqlite:///{tmp}/mlflow.db")
        cfg = load_config(cfg_path)
        version, _ = train_and_register(cfg, make_synthetic(n_rows=5000), tags={})
        from fraud.gate import run_gate

        run_gate(cfg, version, make_synthetic(n_rows=2000, seed=9))  # makes it champion
        yield cfg_path, f"models:/{cfg.mlflow.model_name}/{version}"


@pytest.fixture
def env(registered, monkeypatch):
    cfg_path, uri = registered
    monkeypatch.chdir(cfg_path.parent)
    monkeypatch.setenv("MLFLOW_TRACKING_URI", f"sqlite:///{cfg_path.parent}/mlflow.db")
    monkeypatch.setenv("FRAUD_CONFIG", str(cfg_path))
    monkeypatch.setenv("MODEL_URI", uri)
    return uri


@pytest.fixture
def client(env):
    return TestClient(serve.create_app())


def applications(n: int, seed: int = 5) -> list[dict]:
    # to_json -> plain Python types (JSON has no numpy int64)
    return json.loads(make_synthetic(n_rows=n, seed=seed)[FEATURES].to_json(orient="records"))


def metric(client: TestClient, line_start: str) -> float:
    for line in client.get("/metrics").text.splitlines():
        if line.startswith(line_start):
            return float(line.rsplit(" ", 1)[1])
    raise AssertionError(f"metric {line_start!r} not found")


def test_health(client, env):
    assert client.get("/health").json() == {"status": "ok", "model_uri": env}


def test_score_matches_offline_scoring(client, env):
    import mlflow

    apps = applications(30)
    model = mlflow.lightgbm.load_model(env)
    offline = score(model, make_synthetic(n_rows=30, seed=5))
    for app, expected in zip(apps, offline, strict=True):
        body = client.post("/score", json=app).json()
        assert body["score"] == pytest.approx(expected, abs=1e-12)
        assert body["flagged"] == (body["score"] >= body["threshold"])
        assert body["model_version"] == env.rsplit("/", 1)[1]


@pytest.mark.parametrize(
    "corrupt",
    [
        lambda a: a.pop("income"),  # missing field
        lambda a: a.update(extra=1),  # unknown field
        lambda a: a.update(payment_type="ZZ"),  # unknown category
        lambda a: a.update(email_is_free=2),  # binary flag out of {0, 1}
        lambda a: a.update(zip_count_4w="12"),  # string instead of int (strict)
        lambda a: a.update(month=3),  # not a feature
    ],
)
def test_invalid_application_is_422_and_counted(client, corrupt):
    app = applications(1)[0]
    corrupt(app)
    assert client.post("/score", json=app).status_code == 422
    assert metric(client, 'fraud_requests_total{status="422"}') == 1


def test_metrics_and_psi_window(client, env):
    names = ["fraud_requests_total", "fraud_request_latency_seconds", "fraud_score",
             "fraud_score_psi", "fraud_model_info"]
    response = client.get("/metrics", follow_redirects=False)  # Prometheus target: no redirect
    assert response.status_code == 200
    text = response.text
    assert all(f"# TYPE {n} " in text for n in names)
    assert f'fraud_model_info{{version="{env.rsplit("/", 1)[1]}"}} 1.0' in text
    assert math.isnan(metric(client, "fraud_score_psi"))  # window (20) not full yet
    for app in applications(20, seed=11):
        client.post("/score", json=app)
    assert metric(client, 'fraud_requests_total{status="200"}') == 20
    assert metric(client, "fraud_score_count") == 20
    assert math.isfinite(metric(client, "fraud_score_psi"))


@pytest.mark.parametrize(
    ("uri", "error", "exc"),
    [
        ("", "must pin a version", ValueError),
        ("models:/fraud-lgbm@champion", "must pin a version", ValueError),
        ("models:/fraud-lgbm/99", "Cannot load model", RuntimeError),
    ],
)
def test_startup_fails_on_bad_model_uri(env, monkeypatch, uri, error, exc):
    monkeypatch.setenv("MODEL_URI", uri)
    with pytest.raises(exc, match=error):
        serve.create_app()


def test_startup_fails_without_tracking_uri(env, monkeypatch):
    monkeypatch.delenv("MLFLOW_TRACKING_URI")
    with pytest.raises(RuntimeError, match="MLFLOW_TRACKING_URI is not set"):
        serve.create_app()


def test_startup_fails_if_code_features_differ_from_model(env, monkeypatch):
    monkeypatch.setattr(serve, "FEATURES", FEATURES[:-1])
    with pytest.raises(ValueError, match="trained on other features"):
        serve.create_app()


def test_registry_cli_prints_pinned_champion_uri(env, capsys):
    assert registry_main(["--config", "config.yaml"]) == env
    assert capsys.readouterr().out.strip() == env
