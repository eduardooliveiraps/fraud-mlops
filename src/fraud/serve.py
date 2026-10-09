"""Scoring API. One pinned model version, loaded at startup; scaling = more pods, not workers.

Run: uvicorn --factory fraud.serve:create_app (see `make serve`). Environment:
MODEL_URI (pinned, e.g. models:/fraud-lgbm/3), MLFLOW_TRACKING_URI, FRAUD_CONFIG (optional),
DRAIN_FILE (optional; while this file exists, responses ask clients to reconnect).
Request bodies are never logged (license rule: no row-level data in logs).
"""

import logging
import math
import os
import re
import threading
import time
from collections import deque
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, Literal

import mlflow
import pandas as pd
from fastapi import FastAPI, Request, Response
from lightgbm import LGBMClassifier
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)
from pydantic import BaseModel, ConfigDict, create_model

from fraud.config import load_config
from fraud.drift import bin_fractions, psi
from fraud.features import FEATURES, score
from fraud.registry import require_tracking_uri
from fraud.schema import BINARY_COLS, CATEGORICAL_COLS, NUMERIC_COLS

logger = logging.getLogger(__name__)

# Pinned versions only: `kubectl rollout undo` must bring back the previous model, which an
# alias in the pod spec would not do. `make deploy` resolves the alias to a version.
PINNED_URI = re.compile(r"^models:/(?P<name>[^/@]+)/(?P<version>\d+)$")


def _field_type(col: str) -> object:
    if col in CATEGORICAL_COLS:
        return Literal[tuple(CATEGORICAL_COLS[col])]
    if col in BINARY_COLS:
        return Literal[0, 1]
    return int if NUMERIC_COLS[col] == "int64" else float


# Request schema generated from fraud.schema: one source of truth for column names and types.
# strict: no silent conversions ("5" is not 5); extra="forbid": unknown fields are rejected.
Application = create_model(
    "Application",
    __config__=ConfigDict(extra="forbid", strict=True),
    **{col: (_field_type(col), ...) for col in FEATURES},
)


class ScoreResponse(BaseModel):
    score: float
    flagged: bool
    threshold: float
    model_version: str


class ScoreWindow:
    """Last N scores of this process, for PSI against the training reference."""

    def __init__(self, size: int, edges: list[float], reference: list[float]) -> None:
        self._scores: deque[float] = deque(maxlen=size)
        self._lock = threading.Lock()  # the endpoint runs in a thread pool
        self._edges, self._reference = edges, reference

    def add(self, value: float) -> None:
        with self._lock:
            self._scores.append(value)

    def psi(self) -> float:
        with self._lock:
            scores = list(self._scores)
        if len(scores) < self._scores.maxlen:
            return math.nan  # too few scores for a meaningful value
        return psi(self._reference, bin_fractions(scores, self._edges))


def _load_model(uri: str) -> tuple[LGBMClassifier, dict[str, Any], str]:
    """Return (model, metadata, version) for a pinned model URI."""
    match = PINNED_URI.match(uri)
    if not match:
        raise ValueError(f"MODEL_URI must pin a version like models:/fraud-lgbm/3, got {uri!r}")
    try:
        model = mlflow.lightgbm.load_model(uri)
        metadata = mlflow.models.get_model_info(uri).metadata or {}
    except Exception as err:
        raise RuntimeError(f"Cannot load model {uri}: {err}") from err
    missing = {"threshold", "features", "reference_edges", "reference_fractions"} - metadata.keys()
    if missing:
        raise ValueError(f"Model {uri} metadata is missing {sorted(missing)}")
    if metadata["features"] != FEATURES:
        raise ValueError(f"Model {uri} was trained on other features than this code provides")
    model.set_params(n_jobs=1)  # one row per request: threads cost more than they save
    return model, metadata, match["version"]


def create_app() -> FastAPI:
    """App factory: fails (and the process exits) if anything needed to score is missing."""
    # This is the entrypoint; uvicorn only configures its own loggers.
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    uri = os.environ.get("MODEL_URI", "")
    require_tracking_uri()
    cfg = load_config(Path(os.environ.get("FRAUD_CONFIG", "configs/config.yaml")))
    model, metadata, version = _load_model(uri)
    threshold = float(metadata["threshold"])
    drain_file = Path(os.environ["DRAIN_FILE"]) if os.environ.get("DRAIN_FILE") else None
    window = ScoreWindow(
        cfg.monitoring.psi_window, metadata["reference_edges"], metadata["reference_fractions"]
    )

    # Own registry per app: metrics start at zero and tests do not leak into each other.
    registry = CollectorRegistry()
    requests_total = Counter(
        "fraud_requests_total", "Scoring requests by HTTP status", ["status"], registry=registry
    )
    latency = Histogram(
        "fraud_request_latency_seconds",
        "Time to answer /score, including validation",
        buckets=(0.0025, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5),
        registry=registry,
    )
    scores = Histogram(
        "fraud_score",
        "Fraud probabilities returned by /score",
        buckets=(0.005, 0.01, 0.02, 0.03, 0.05, 0.1, 0.2, 0.3, 0.5, 0.75, 1.0),  # most near 0
        registry=registry,
    )
    Gauge(
        "fraud_score_psi",
        f"PSI of the last {cfg.monitoring.psi_window} scores vs the training reference",
        registry=registry,
    ).set_function(window.psi)  # computed when Prometheus scrapes, not per request
    Gauge(
        "fraud_model_info", "Model version served by this pod (always 1)", ["version"],
        registry=registry,
    ).labels(version=version).set(1)

    app = FastAPI(title="fraud-mlops scoring API", version=version)
    # One prediction at a time per process. Python runs one thread at a time (GIL), so parallel
    # scoring threads only fight over it: measured 33 req/s with 4 threads vs 68 with 1.
    # Waiting threads sleep on the lock; /health does not take it, so probes stay fast.
    score_lock = threading.Lock()

    @app.middleware("http")
    async def measure_and_drain(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        start = time.perf_counter()
        response = await call_next(request)
        if request.url.path == "/score":
            latency.observe(time.perf_counter() - start)
            requests_total.labels(status=str(response.status_code)).inc()
        # Shutting down (preStop created the file): ask each client to close its kept-alive
        # connection after this response, so it reconnects to another pod before uvicorn stops.
        if drain_file is not None and drain_file.exists():
            response.headers["Connection"] = "close"
        return response

    @app.get("/metrics")
    def metrics() -> Response:
        return Response(generate_latest(registry), media_type=CONTENT_TYPE_LATEST)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "model_uri": uri}

    @app.post("/score")
    def score_application(application: Application) -> ScoreResponse:  # type: ignore[valid-type]
        # A sync endpoint: FastAPI runs it in a thread pool, so CPU work does not block the server.
        with score_lock:
            value = float(score(model, pd.DataFrame([application.model_dump()]))[0])
        scores.observe(value)
        window.add(value)
        return ScoreResponse(
            score=value, flagged=value >= threshold, threshold=threshold, model_version=version
        )

    logger.info("Serving %s (threshold %.4f)", uri, threshold)
    return app
