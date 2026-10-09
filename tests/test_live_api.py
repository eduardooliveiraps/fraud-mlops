"""Checks against a running API (`make smoke`, CI). Skipped unless SMOKE_URL is set."""

import json
import os
import re

import httpx
import pytest

from fraud.data import make_synthetic
from fraud.features import FEATURES

SMOKE_URL = os.environ.get("SMOKE_URL")
pytestmark = pytest.mark.skipif(not SMOKE_URL, reason="needs a running API: set SMOKE_URL")


@pytest.fixture(scope="module")
def api():
    with httpx.Client(base_url=SMOKE_URL, timeout=10) as client:
        yield client


@pytest.fixture(scope="module")
def application() -> dict:
    return json.loads(make_synthetic(n_rows=1, seed=21)[FEATURES].to_json(orient="records"))[0]


def test_health_serves_a_pinned_version(api):
    body = api.get("/health").json()
    assert body["status"] == "ok"
    assert re.fullmatch(r"models:/[^/@]+/\d+", body["model_uri"])


def test_score(api, application):
    response = api.post("/score", json=application)
    assert response.status_code == 200
    body = response.json()
    assert 0 <= body["score"] <= 1
    assert body["flagged"] == (body["score"] >= body["threshold"])


def test_invalid_application_is_rejected(api, application):
    assert api.post("/score", json={**application, "payment_type": "ZZ"}).status_code == 422


def test_metrics_are_exposed(api):
    text = api.get("/metrics").text
    for name in ("fraud_requests_total", "fraud_request_latency_seconds", "fraud_score",
                 "fraud_score_psi", "fraud_model_info"):
        assert f"# TYPE {name} " in text, name
