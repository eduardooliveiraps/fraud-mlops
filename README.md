# fraud-mlops

[![ci](https://github.com/eduardooliveiraps/fraud-mlops/actions/workflows/ci.yml/badge.svg)](https://github.com/eduardooliveiraps/fraud-mlops/actions/workflows/ci.yml)

Fraud scoring service with a train → gate → deploy → monitor loop on a local kind cluster.
Plan, status and design decisions: [docs/ROADMAP.md](docs/ROADMAP.md).

## Quickstart

Requires Python 3.11 (Linux/WSL2).

```bash
make install   # create .venv from the pinned requirements-dev.lock
make lint      # ruff
make test      # pytest, synthetic data only
make data      # Base.csv -> Parquet (paths in configs/config.yaml)
```

`make lock` re-resolves the version ranges in `pyproject.toml` and rewrites both lock files:
`requirements-dev.lock` (laptop, CI) and `requirements.lock` (runtime only, used by the image).
It only considers releases at least 14 days old (dependency cool-down).

## Local cluster runbook

Requires Docker (Docker Desktop with WSL integration) and ~10 GB RAM for WSL.

```bash
make tools         # pinned kind, kubectl, helm into ~/.local/bin (checksums verified)
make cluster-up    # one-node kind cluster "fraud" (~1.2 GiB RAM)
make mlflow-up     # MLflow server + registry; UI at http://localhost:5000
make mlflow-check  # health check + list experiments
make train         # validate -> train -> register in MLflow -> gate (moves @champion if better)
make cluster-down  # delete the cluster; MLflow data in .state/mlflow/ is kept
```

Scoring API on the laptop (serves the champion's pinned version from the cluster's MLflow):

```bash
make serve         # http://localhost:8000/docs (OpenAPI), /score, /health, /metrics
```

Training inside the cluster (same code, packaged as an image; data mounted read-only):

```bash
make image         # build fraud-mlops:<git describe --dirty> and load it into kind
make train-deploy  # config as ConfigMap + weekly CronJob "fraud-train" using that image
make train-job     # run the CronJob's template now; waits, prints logs, fails if the Job fails
```

Serving inside the cluster (http://localhost:8000):

```bash
make metrics-server             # CPU metrics for kubectl top and the autoscaler (Helm chart)
make deploy                     # API with the champion's pinned version; waits for the rollout
make deploy MODEL_VERSION=3     # a specific registered version (hotfix / demo)
make rollback                   # kubectl rollout undo: previous model + image
make loadtest                   # Locust, 50 users, 3 min (LOAD_USERS=, LOAD_TIME= to change)
kubectl -n fraud rollout history deployment/fraud-api   # which model each revision served
```

Monitoring (Prometheus http://localhost:9090, Grafana http://localhost:3000, read-only without
login):

```bash
make monitoring        # Prometheus (server only) + Grafana, pinned Helm charts, namespace monitoring
make grafana-password  # admin password (generated into a Kubernetes Secret, not in the repo)
make drift-demo        # 4 min real held-out traffic, then 8 min shifted traffic (alert fires)
```

| Symptom | Check |
|---------|-------|
| `docker: ... EOF` while pulling | Network hiccup: run the command again. |
| MLflow pod restarts | `kubectl -n fraud describe pod -l app=mlflow` (look for `OOMKilled`). |
| `localhost:5000` refuses connections | `kubectl -n fraud get pods` until `1/1 Running`. |
| Start with an empty MLflow | `make cluster-down && rm -rf .state/mlflow && make cluster-up mlflow-up` |
| Training Job failed | `make train-job` prints the pod logs; `kubectl -n fraud get jobs` shows history. |
| Pod stuck in `ErrImageNeverPull`/`ImagePullBackOff` | Image not in the node: `make image` (after every `cluster-up`). |
| `make deploy` fails with `No such image` | Build it first: `make image`. |
| Rollout stuck, new pod `CrashLoopBackOff` | Old pods keep serving; `kubectl -n fraud logs <pod>`, then `make rollback`. |
| `kind load` fails with `content digest ... not found` | `docker save fraud-mlops:<tag> -o img.tar && kind load image-archive img.tar --name fraud` |

## Data facts and evaluation

Aggregates from `notebooks/01_eda.py` (1,000,000 applications, 32 columns, 1.10% fraud).

| Month | Rows | Frauds | Fraud rate | Split |
|------:|-----:|-------:|-----------:|-------|
| 0 | 132,440 | 1,500 | 1.13% | train |
| 1 | 127,620 | 1,198 | 0.94% | train |
| 2 | 136,979 | 1,198 | 0.87% | train |
| 3 | 150,936 | 1,392 | 0.92% | train |
| 4 | 127,691 | 1,452 | 1.14% | train |
| 5 | 119,323 | 1,411 | 1.18% | valid |
| 6 | 108,168 | 1,450 | 1.34% | test |
| 7 | 96,843 | 1,428 | 1.47% | test |

- **Time-based split**: train on months 0-4, choose the threshold on month 5, report on 6-7.
  The fraud rate rises in later months, so metrics are only compared on the same months.
- **Metrics**: recall at 5% false-positive rate (the BAF paper's benchmark) and PR-AUC
  (average precision). The decision threshold minimises an assumed cost of 20 per missed fraud
  and 1 per false alarm (`configs/config.yaml`).

### Results (test months 6-7, 205,011 applications, 1.40% fraud)

| Model | Recall at 5% FPR | PR-AUC |
|-------|-----------------:|-------:|
| Random ranking | 0.050 | 0.014 |
| `credit_risk_score` alone | 0.198 | 0.037 |
| **LightGBM** (`fraud-lgbm` v1, champion) | **0.553** | **0.196** |

At the cost-based threshold (0.0287, chosen on month 5) the model flags 6.1% of legitimate
applications and catches 58.7% of frauds (precision 12.1%). Expected cost: 176 per 1,000
applications, against 280 for flagging nothing. Training takes ~47 s and ~1.3 GB RAM.

## Scoring API

`POST /score` takes one application with the 29 model features (schema generated from
`src/fraud/schema.py`; unknown fields, wrong types and unknown categories get `422`):

```json
{"score": 0.0123, "flagged": false, "threshold": 0.0287, "model_version": "1"}
```

`flagged` is `score >= threshold`; the threshold travels with the model version.
`GET /metrics` (Prometheus): `fraud_requests_total{status}`, `fraud_request_latency_seconds`,
`fraud_score`, `fraud_score_psi` (last 1,000 scores vs the training reference; NaN until full),
`fraud_model_info{version}`. On 1,000 held-out applications the API returns exactly the
offline scores (max difference 0.0); local latency p50 14 ms, p99 23 ms.

In the cluster (pods with 1 CPU each, laptop shared with Locust, MLflow and Docker):

| Load test (50 users) | Pods | Throughput | p50 | Failures |
|----------------------|-----:|-----------:|----:|---------:|
| Before scale-out | 2 | 84 req/s | 325 ms | 0 |
| After HPA scale-out | 4 | 134 req/s | 160 ms | 0 |
| Rollout to v3 + rollback, under load | 4 | 134 req/s | 140 ms | 0 of 31,938 |

## CI/CD

`.github/workflows/ci.yml`, on every push and pull request:

1. **lint-test**: `make install lint test` (unit tests use synthetic data only).
2. **smoke** (after lint-test): the same `make` targets as the runbook, on a fresh kind cluster in
   the CI machine: synthetic data (`python -m fraud.data --synthetic 20000`), MLflow, image,
   training CronJob run once (validate, train, register, gate), deploy, live API checks
   (`make smoke`). On `main` only, the image that passed is pushed to GHCR as
   `ghcr.io/eduardooliveiraps/fraud-mlops:<short commit>` (no `latest`).

Actions are pinned by commit SHA; the token is read-only except `packages: write` in the smoke job.

## Monitoring and drift

Prometheus discovers every API pod through its `prometheus.io/scrape` annotation (pods added by
the autoscaler are scraped automatically) and evaluates one alert rule:
`FraudScoreDrift` = `max(fraud_score_psi) > 0.2` for 5 minutes. The Grafana dashboard
(`k8s/grafana/fraud-dashboard.json`, provisioned from the repo) shows request rate by status,
p50/p99 latency, error share, score distribution, PSI per pod with 0.1/0.2 lines, the alert
state and pods per model version.

Drift demo (`make drift-demo`; PSI = max over the API pods, sampled every 30 s):

| Phase | Traffic | PSI | Alert |
|-------|---------|----:|-------|
| 0-4 min | real held-out applications (months 6-7) | 0.007-0.015 | inactive |
| from ~4.5 min | shifted (synthetic) applications | 0.49-0.62 | pending at ~5.5 min, **firing at ~10.5 min** |
| afterwards | 90 s of real traffic again | 0.018 | resolved |

0 failed requests in 102,890. PSI covers each pod's last 1,000 scores, so it changes only with
traffic. The alert is not sent anywhere: in production, Alertmanager would route it to
Slack/PagerDuty, and the response is to check the input data and retrain (`make train-job`).

## Dataset and license

- Uses the **Base** variant of the Bank Account Fraud (BAF) Dataset Suite: Jesus et al.,
  "Turning the Tables: Biased, Imbalanced, Dynamic Tabular Datasets for ML Evaluation",
  NeurIPS 2022 Datasets and Benchmarks Track.
  [Kaggle](https://www.kaggle.com/datasets/sgpjesus/bank-account-fraud-dataset-neurips-2022)
- License: [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/). Used here
  for non-commercial educational/portfolio purposes.
- Changes made: only `Base.csv` is used; it is converted to Parquet and split by `month`.
- The dataset and any derived data are **not** in this repo. Download `Base.csv` from Kaggle
  into `data/raw/`. The MIT license covers this repo's code only, not the dataset.
- CI and tests use synthetic data generated from the schema (column names, dtypes, category
  levels, small discrete value sets) and hand-written value ranges; it is not sampled from or
  fitted to row-level data.
