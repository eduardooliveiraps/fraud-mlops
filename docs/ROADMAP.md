# Roadmap

Status: todo | design | in progress | review | done. One part in progress at a time.

| # | Part | Status | Depends on |
|---|------|--------|------------|
| 0 | Data loading, schema, synthetic data | done | - |
| 1 | Foundations: config, pinned deps, logging, basic CI | done | 0 |
| 2 | Cluster + MLflow spike (RAM check) | done | 1 |
| 3 | Evaluation core: time split, metrics, threshold | todo | 1 |
| 4 | Training + gate (local, against cluster MLflow) | todo | 2, 3 |
| 5 | Training Job / CronJob on Kubernetes | todo | 4 |
| 6 | Scoring API (local) | todo | 3, 4 |
| 7 | Serving on Kubernetes: probes, HPA, rollback, load test | todo | 5, 6 |
| 8 | Monitoring: Prometheus, Grafana, PSI alert | todo | 7 |
| 9 | CI/CD: image to GHCR, kind smoke test | todo | 7 |
| 10 | Terraform (kind + helm) and final README | todo | all |
| 10c | Optional: GCP Terraform module, validate only | decide after 10b | 10 |

## Contracts
- **Config** (`fraud.config`): `load_config(path) -> Config`. Only source of paths, months,
  costs, thresholds, URLs. Unknown or missing keys fail at load time.
- **Data** (`fraud.data`): `csv_to_parquet(csv, parquet) -> Path`, `load_base(path) -> DataFrame`
  matching `fraud.schema`. `make_synthetic(n_rows, seed)` has the same schema and no real values.
  `make data` builds the Parquet from `configs/config.yaml`.
- **Evaluation** (`fraud.split`, `fraud.metrics`): `time_split(df, cfg) -> train, valid, test`.
  `evaluate(y, scores, cfg) -> {pr_auc, recall_at_fpr, ...}`.
  `choose_threshold(y, scores, costs) -> float` (chosen on valid, reported on test).
- **Features** (`fraud.features`): one preprocessing function, used by both training and serving.
- **Cluster** (`make tools cluster-up`): kind cluster `fraud`, kubectl context `kind-fraud`,
  namespace `fraud`. `make cluster-down` deletes it; MLflow data in `.state/mlflow/` survives.
- **MLflow** (`make mlflow-up`): `http://mlflow.fraud.svc.cluster.local:5000` in the cluster,
  `http://localhost:5000` from WSL/Windows. Server and client are both mlflow 3.16.1.
- **Training**: in = Parquet path + config + `MLFLOW_TRACKING_URI`.
  Out = registered version of `fraud-lgbm` with metrics, threshold and a reference score histogram.
- **Gate**: compares the new version and `@champion` on the same test months. Moves `champion`
  only if it wins by the config margin. Decision is stored as a version tag.
- **Serving**: in = `MODEL_URI` (pinned version, e.g. `models:/fraud-lgbm/7`) + `MLFLOW_TRACKING_URI`.
  Out = `/score`, `/health`, `/metrics`.
- **Metrics** (serving -> monitoring): `fraud_requests_total{status}`,
  `fraud_request_latency_seconds`, `fraud_score`, `fraud_score_psi`.
- **Deploy**: `make deploy` resolves `@champion` to a version and sets it on the Deployment.

## RAM budget (measured in part 2)
WSL memory cap: 10 GB (`.wslconfig`). Estimated peak: ~5-6.5 GB. Do not run the training Job
during load tests.

| Component | Request / limit | Measured |
|-----------|-----------------|----------|
| kind node, whole cluster idle (incl. MLflow) | - | 1.2 GiB |
| MLflow server (1 worker, job runner off) | 250m, 384Mi / 1 CPU, 1Gi | ~350 MiB idle, 355 MiB peak during a run |

Measured with `docker stats fraud-control-plane` and the pod's cgroup `memory.current`/`memory.peak`.
Rebuilding the cluster from scratch (`cluster-down`, `cluster-up`, `mlflow-up`) takes ~2 min.

## Design decisions
Format: date - decision - why - alternatives considered.
- 2026-10-08 - Time-based split by `month` (train 0-4, valid 5, test 6-7) - Fraud patterns drift
  over time; a random split leaks the future and gives optimistic metrics. Alt: random split.
- 2026-10-08 - Synthetic data for tests and CI - The dataset license and size keep real data out
  of the repo and CI; synthetic data has the real schema but hand-written values.
  Alt: a committed sample (not allowed by the rules above).
- 2026-10-09 - Primary metric: recall at 5% FPR; also PR-AUC - It is the BAF paper's benchmark
  metric, so results are comparable with published numbers; PR-AUC suits a 1% positive rate
  better than ROC-AUC. Alt: ROC-AUC, F1.
- 2026-10-09 - Gate: promote if recall@5%FPR >= champion + 0.005 and PR-AUC drops <= 0.005, both
  on the same test months - Comparing on identical data is the only fair comparison; the margin
  stops promotions caused by noise. Alt: always promote the latest model.
- 2026-10-09 - Decision threshold from an assumed cost ratio of 20:1 (missed fraud : false alarm),
  chosen on valid - The business threshold is a separate decision from model quality; costs are
  config values, not code. Alt: a fixed 0.5 threshold.
- 2026-10-09 - Serving pins a model version, not the alias - `kubectl rollout undo` restores the
  previous pod spec; with `@champion` in the spec it would reload the current model, so the
  rollback would not roll back the model. Alt: alias in the spec + restart.
- 2026-10-09 - No Ingress: NodePort + kind port mapping - The community ingress-nginx controller
  was retired in March 2026; on GKE we would use Gateway API. Alt: Traefik as Ingress controller.
- 2026-10-09 - MLflow via our own plain manifests, applied by `make` - There is no official chart
  and Bitnami withdrew its free images; small manifests are easier to read and teach more.
  Terraform installs only third-party charts (Prometheus, Grafana). Alt: community MLflow chart.
- 2026-10-09 - Load test with Locust - Python, so it can reuse config and `make_synthetic`.
  Alt: k6.
- 2026-10-09 - Config as frozen dataclasses loaded from YAML, strict keys - No new dependency;
  typos in keys fail at load time instead of silently using a default. Alt: pydantic-settings.
- 2026-10-09 - Dependencies: version ranges in `pyproject.toml`, exact pins in `requirements.lock`
  (built by `make lock` in a fresh venv) - Ranges say what we support, the lock makes every
  install identical (laptop, CI, later the image). Alt: pip-tools or uv (extra tools).
- 2026-10-09 - Pin mlflow 3.16.1 for server image and client - 3.17.0 was 2 days old; a release
  with a few weeks of patches is safer, and identical versions rule out client/server mismatch.
  Bump both together on purpose. Alt: latest 3.17.0.
- 2026-10-09 - MLflow data in a static PersistentVolume over a kind host mount (`.state/mlflow/`)
  - kind's default storage lives inside the node container and is deleted with the cluster.
  Alt: default StorageClass (data lost on `cluster-down`).
- 2026-10-09 - MLflow reached via NodePort 30500 -> `127.0.0.1:5000` (kind port mapping) - Always
  on, no `kubectl port-forward` terminal to keep alive; bound to localhost only because MLflow has
  no auth. Alt: port-forward.
- 2026-10-09 - MLflow background job runner disabled (`MLFLOW_SERVER_ENABLE_JOB_EXECUTION=false`)
  - It starts several worker processes for GenAI/async jobs we don't use and got the pod
  OOMKilled at a 1 GiB limit. Alt: raise the limit to ~2 GiB.
- 2026-10-09 - CLI tools (kind v0.33.0, kubectl v1.37.1) pinned with sha256 in the Makefile,
  installed to `~/.local/bin` by `make tools` - Same versions everywhere, and a tampered or
  corrupted download fails instead of installing. Kubernetes v1.37.0 = kind's default node image.
  Alt: apt/snap packages (unpinned, versions vary by machine).
