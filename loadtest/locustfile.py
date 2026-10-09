"""Load test for POST /score with synthetic applications (no real data). Run: make loadtest."""

import json
import random

from locust import HttpUser, between, task

from fraud.data import make_synthetic
from fraud.features import FEATURES

# Plain Python types for JSON. Fixed seeds: the same payloads in every run.
APPLICATIONS = json.loads(make_synthetic(n_rows=2000, seed=7)[FEATURES].to_json(orient="records"))
RNG = random.Random(0)
# A Kubernetes Service balances connections, not requests: a kept-alive connection stays on the
# pod it first reached, so pods added by the HPA would only get new connections. Like a client
# pool with a maximum connection lifetime, each user reconnects every N requests.
REQUESTS_PER_CONNECTION = 100


class Scorer(HttpUser):
    wait_time = between(0.05, 0.2)  # think time between a user's requests

    def on_start(self) -> None:
        self.sent = 0

    @task
    def score(self) -> None:
        self.client.post("/score", json=RNG.choice(APPLICATIONS))  # non-2xx counts as failure
        self.sent += 1
        if self.sent % REQUESTS_PER_CONNECTION == 0:
            self.client.close()  # next request opens a new connection
