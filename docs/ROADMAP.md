# Roadmap

Status: todo | design | in progress | review | done. One part in progress at a time.

| # | Part | Status | Depends on |
|---|------|--------|------------|
| 0 | Data loading, schema, synthetic data | done | - |
| 1 | Foundations: config, pinned deps, logging, basic CI | done | 0 |
| 2 | Cluster + MLflow spike (RAM check) | done | 1 |
| 3 | Evaluation core: time split, metrics, threshold | done | 1 |
| 4 | Training + gate (local, against cluster MLflow) | done | 2, 3 |
| 5 | Training Job / CronJob on Kubernetes | done | 4 |
| 6 | Scoring API (local) | done | 3, 4 |
| 7 | Serving on Kubernetes: probes, HPA, rollback, load test | done | 5, 6 |
| 8 | Monitoring: Prometheus, Grafana, PSI alert | done | 7 |
| 9 | CI/CD: image to GHCR, kind smoke test | done (PR path checked in part 10's PR) | 7 |
| 10 | Terraform (kind + helm) and final README | todo | all |
| 10c | Optional: GCP Terraform module, validate only | decide after 10b | 10 |

## Contracts
- **Config** (`fraud.config`): `load_config(path) -> Config`. Only source of paths, months,
  costs, thresholds, URLs. Unknown or missing keys fail at load time.
- **Data** (`fraud.data`): `csv_to_parquet(csv, parquet) -> Path`, `load_base(path) -> DataFrame`
  matching `fraud.schema`. `make_synthetic(n_rows, seed)` has the same schema and no real values.
  `make data` builds the Parquet from `configs/config.yaml`.
- **Split** (`fraud.split`): `time_split(df, cfg.split) -> Split(train, valid, test)`. Month order
  train < valid < test is enforced by `SplitConfig`; an empty split fails.
- **Metrics** (`fraud.metrics`): `choose_threshold(y_valid, s_valid, cfg.evaluation) -> float`
  (may be `inf` = flag nothing). `evaluate(y_test, s_test, threshold, cfg.evaluation) ->`
  `{pr_auc, recall_at_fpr, precision, recall, fpr, cost_per_1k}`; flagged = score >= threshold.
  The gate compares `recall_at_fpr` and `pr_auc`. Baseline to beat: 0.198 / 0.037 (test months).
- **Cluster** (`make tools cluster-up`): kind cluster `fraud`, kubectl context `kind-fraud`,
  namespace `fraud`. `make cluster-down` deletes it; MLflow data in `.state/mlflow/` survives.
- **MLflow** (`make mlflow-up`): `http://mlflow.fraud.svc.cluster.local:5000` in the cluster,
  `http://localhost:5000` from WSL/Windows. Server and client are both mlflow 3.16.1.
- **Validation** (`fraud.validate`): `validate(df)` (Pandera, strict). Errors list column, check
  and failure count only, never values.
- **Features** (`fraud.features`): `prepare_features(df) -> X` (29 features, fixed category
  levels) and `score(model, df) -> fraud probabilities`. Used by training, gate and serving.
- **Drift reference** (`fraud.drift`): `quantile_edges`, `bin_fractions`. Serving adds PSI here.
- **Training** (`python -m fraud.train --config <yaml>`, `make train`): in = Parquet + config +
  `MLFLOW_TRACKING_URI` (required). Out = new version of `fraud-lgbm`; run has params, `valid_*`
  and `test_*` metrics, `threshold`. Model metadata: `threshold`, `features`, `reference_edges`,
  `reference_fractions` (PSI reference = test-month scores). Version tag `data_sha256`.
- **Image** (`make image`): `fraud-mlops:<git describe --always --dirty>`, one image for training
  and serving, runtime deps from `requirements.lock`, uid 10001, no config or data inside
  (`.dockerignore` is an allow-list). Loaded into kind with `kind load` (no registry until part 9).
- **Training in the cluster** (`make train-deploy`, `make train-job`): CronJob `fraud-train`
  (Mondays 03:00 UTC) is the only Job template. Config from ConfigMap `fraud-config` at
  `/app/configs`, data from read-only PVC `fraud-data` at `/app/data/processed`,
  `MLFLOW_TRACKING_URI` = in-cluster MLflow, `IMAGE_TAG` logged as a version tag.
  Job outcome: Complete (gate promoted or rejected) or Failed (error, nothing registered).
- **Gate** (`fraud.gate.run_gate`): re-scores candidate and `@champion` on the same test months;
  promotes if recall gain >= `gate.min_recall_gain` and PR-AUC drop <= `gate.max_pr_auc_drop`.
  Version tags `gate_decision`, `gate_reason`, `gate_compared_to`. Rejection is not an error.
- **Registry** (`fraud.registry`): `python -m fraud.registry --config <yaml>` prints the champion's
  pinned URI (`models:/fraud-lgbm/<n>`); used by `make serve` and (part 7) `make deploy`.
- **Serving** (`uvicorn --factory fraud.serve:create_app`, `make serve`): env `MODEL_URI` (pinned
  version only; aliases rejected), `MLFLOW_TRACKING_URI`, optional `FRAUD_CONFIG`. Refuses to start
  if the model can't load or its `features` metadata differs from the code's `FEATURES`.
  `POST /score` (29 features, strict, extra fields forbidden) -> `{score, flagged, threshold,
  model_version}`; `GET /health` -> 200 once loaded; `GET /metrics` (no redirect).
  One worker per process; LightGBM uses 1 thread per prediction.
- **Metrics** (serving -> monitoring): `fraud_requests_total{status}`,
  `fraud_request_latency_seconds` (histogram, /score only), `fraud_score` (histogram),
  `fraud_score_psi` (gauge, last `monitoring.psi_window` scores, NaN until full),
  `fraud_model_info{version}` (gauge = 1).
- **Deploy** (`make deploy [MODEL_VERSION=n]`, `make rollback`): resolves `@champion` (or checks
  that version n exists) and that the image exists locally, then applies Deployment `fraud-api`
  with `MODEL_URI` pinned, image tag, image content id and a change-cause. Service `fraud-api`
  (`fraud-api.fraud.svc.cluster.local:8000`, NodePort 30800 -> `localhost:8000`); HPA 2-4 pods
  at 70% CPU of a 250m request. `make rollback` = `kubectl rollout undo` (model and image).
- **Third-party components**: pinned Helm charts with values in `k8s/<name>/values.yaml`
  (metrics-server 3.14.0, prometheus-community/prometheus 29.33.1, grafana-community/grafana
  13.2.5; Terraform installs them in part 10). Charts follow the same 14-day cool-down.
- **Monitoring** (`make monitoring`, namespace `monitoring`): Prometheus scrapes pods annotated
  `prometheus.io/scrape: "true"` (+ `port`, `path`) every 15 s and holds rule `FraudScoreDrift`
  (`max(fraud_score_psi) > 0.2` for 5m). `prometheus-server.monitoring.svc.cluster.local:9090`,
  `localhost:9090`. Grafana `localhost:3000`, data source uid `prometheus`, dashboard uid
  `fraud-api`. A test checks that every metric the dashboard and rule query is exposed by the API.
- **CI** (`.github/workflows/ci.yml`, first green run 2026-10-09: lint-test 1.6 min, smoke 3.6 min,
  image public at `ghcr.io/eduardooliveiraps/fraud-mlops:2d60948`): `lint-test` then `smoke` (fresh kind cluster, synthetic
  data via `python -m fraud.data --synthetic N`, which refuses to overwrite an existing file;
  ends with `make smoke` = `tests/test_live_api.py` against `localhost:8000`). On push to `main`:
  `make push REGISTRY=ghcr.io/<owner>` -> `ghcr.io/<owner>/fraud-mlops:<git describe>`.
- **Load-test payloads** (`loadtest/payloads.py`): `LOAD_DATA=synthetic` (default, CI) or `real`
  (held-out months from the local Parquet, in memory only).

## RAM budget (measured in part 2)
WSL memory cap: 10 GB (`.wslconfig`). Estimated peak: ~5-6.5 GB. Do not run the training Job
during load tests.

| Component | Request / limit | Measured |
|-----------|-----------------|----------|
| kind node, whole cluster idle (incl. MLflow) | - | 1.2 GiB |
| MLflow server (1 worker, job runner off) | 250m, 384Mi / 1 CPU, 1Gi | ~350 MiB idle, 355 MiB peak during a run |
| Training, 1M rows, 4 threads (local, part 4) | - | 1.3 GB peak RSS, 47 s |
| Training Job (pod, part 5) | 2 CPU, 1536Mi / 4 CPU, 2560Mi | ~1.15 GiB working set, ~60 s |
| API pod, x2-4 (part 7) | 250m, 384Mi / 1 CPU, 768Mi | ~200 MiB; ~1 CPU (at limit) under load |
| metrics-server (part 7) | chart defaults (100m, 200Mi) | - |
| Prometheus (part 8) | 100m, 256Mi / 500m, 768Mi | ~55 MiB (2 scrape jobs, 2 days) |
| Grafana (part 8) | 50m, 128Mi / 500m, 512Mi | ~210 MiB |

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
- 2026-10-09 - PR-AUC as average precision - The trapezoid area under the PR curve
  interpolates linearly and overstates the score when positives are rare. Alt: `auc(pr_curve)`.
- 2026-10-09 - Recall at FPR counts only reachable thresholds (tied scores are never split) -
  It reports what a real threshold can achieve, so it is slightly conservative. Alt: interpolate.
- 2026-10-09 - One-feature baseline (`credit_risk_score`) - A model's number means little without
  a trivial reference; this one is 0.198 recall at 5% FPR. Alt: no baseline.
- 2026-10-09 - Monthly aggregates (rows, frauds, rate) in the README - Summary statistics, not
  row-level data; they justify the split. Alt: keep EDA output local only.
- 2026-10-09 - Fraud rate rises from ~0.9% (months 2-3) to 1.47% (month 7) - PR-AUC depends on
  the fraud rate, so it is never compared across different months; the gate uses fixed test months.
- 2026-10-09 - Threshold, feature list and PSI reference stored in the model's MLflow metadata -
  Serving needs one URI, and the threshold can never be paired with the wrong model.
  Alt: separate run artifacts.
- 2026-10-09 - The gate re-scores the champion on today's test data - Stored metrics may come from
  different data or config; re-scoring both is the only fair comparison. It also checks that
  the registered model loads and scores. Alt: compare stored metrics.
- 2026-10-09 - `MLFLOW_TRACKING_URI` from the environment only, required - Without it MLflow
  silently writes to `./mlruns`; the address is environment-specific (laptop vs cluster).
- 2026-10-09 - Fixed LightGBM params + early stopping on valid PR-AUC; no tuning, no class
  weights - The project is about the platform; costs are handled by the threshold.
  Determinism: fixed seed, threads, `deterministic=True`. Alt: Optuna search.
- 2026-10-09 - Features: drop `month` (time marker) and `device_fraud_count` (constant); keep `-1`
  missing markers (trees split on them); fixed category levels. Alt: -1 -> NaN.
- 2026-10-09 - Pandera 0.33.1 (0.34 was days old); validation errors summarised without values -
  Pandera's own report contains the failing values, which would be row-level data in logs.
- 2026-10-09 - Ruff E501 enabled - The declared 100-char limit is now checked by `make lint`.
- 2026-10-09 - One image for training and serving - Both run byte-identical `prepare_features`,
  the strongest guard against training/serving skew; one Dockerfile, one CI build. Alt: two images.
- 2026-10-09 - Two locks: `requirements-dev.lock` and runtime `requirements.lock` (resolved inside
  the dev lock) - The image gets only what it runs (59 vs 120 packages). Alt: one lock.
- 2026-10-09 - `mlflow-skinny` at runtime, full `mlflow` in dev only - Client-only package, ~190 MB
  and 36 packages fewer; tests need the full package for a SQLite tracking store.
  Lesson: skinny lacks `skops` (MLflow's safe model format), found only by running in the image;
  now an explicit dependency. The part 9 smoke test runs the image, so CI catches such gaps.
- 2026-10-09 - CronJob as the only Job template; manual runs use `create job --from=cronjob` -
  Scheduled and manual runs cannot drift apart. Alt: separate Job manifest.
- 2026-10-09 - `kind load` instead of a registry until part 9 - Works with Docker's containerd
  store for locally built images (not for pulled multi-platform images); fallback documented.
- 2026-10-09 - Job: `backoffLimit: 1`, deadline 30 min, TTL 1 day, `Forbid` concurrency, read-only
  root filesystem (+ `/tmp` emptyDir) - One retry covers network errors; deterministic errors
  (bad config) simply fail twice, ~30 s wasted. Alt: no retry.
- 2026-10-09 - Dependency cool-down: `make lock` only accepts releases >= 14 days old
  (`PIP_UPLOADED_PRIOR_TO=P14D`) - Broken or malicious releases are usually caught in their first
  days; one rule instead of case-by-case judgement. It moved ~25 pins back one patch (e.g.
  pydantic 2.14.0 -> 2.13.5). The mlflow pin stays because it must match the server image.
- 2026-10-09 - One application per request - Online scoring is per application; batch scoring
  is what training already does. Alt: `/score/batch`.
- 2026-10-09 - PSI computed at scrape time over the last 1,000 scores per pod, NaN until full -
  No per-request cost; a quiet pod never raises a false drift alarm. Alt: recompute per request.
- 2026-10-09 - Serving guards: pinned `MODEL_URI` only, and model `features` must equal the code's
  `FEATURES` - Keeps `rollout undo` meaningful and stops a model built by other feature code from
  serving wrong scores. Alt: accept aliases, no check.
- 2026-10-09 - One uvicorn worker per pod, sync endpoint (thread pool), LightGBM `n_jobs=1` -
  Scale with pods (HPA); one process per pod keeps Prometheus metrics simple.
  Alt: several workers + Prometheus multiprocess mode.
- 2026-10-09 - `/metrics` is a plain route, not a mounted sub-app - A mount answers
  `307 -> /metrics/`; the test client followed it silently, so a test now forbids redirects.
- 2026-10-09 - Keep `httpx` for FastAPI's TestClient despite a Starlette warning suggesting
  `httpx2` - Unknown package to us; httpx works. Revisit when Starlette drops httpx support.
- 2026-10-09 - metrics-server from its official Helm chart (pinned) - One rule: third-party
  components are pinned charts, ours are plain manifests. Alt: raw manifest + `kubectl patch`.
- 2026-10-09 - Manifests filled by `sed` in `make deploy`, plus the image content id as a pod
  annotation - A rebuilt `-dirty` image keeps its tag, so without the id the Deployment did not
  change and the old code kept running (found during this part). Alt: Kustomize.
- 2026-10-09 - Deployment has no `replicas` field - The HPA owns the pod count; a fixed value
  would reset it on every deploy.
- 2026-10-09 - Deploy guards before Kubernetes: version must exist, image must exist - Bad
  deploys fail in seconds on the laptop. If one still reaches the cluster, `maxUnavailable: 0`
  keeps the old pods serving (tested: 40/40 health checks OK while new pods crash-looped).
- 2026-10-09 - `OMP_NUM_THREADS=1` in the API pod - LightGBM's OpenMP pool otherwise starts one
  thread per visible CPU (8) in a 1-CPU pod. Measured: 25 -> 4 threads, ~320 -> ~200 MiB.
- 2026-10-09 - One prediction at a time per pod (lock around scoring) - Python threads share one
  interpreter lock (GIL); parallel scoring threads only fought over it. Measured on one process:
  33 req/s with 4 scoring threads vs 68 with 1. Scale with pods. Alt: `async def` endpoint
  (probes would queue behind scoring).
- 2026-10-09 - Kubernetes Services balance connections, not requests - With kept-alive
  connections, pods added by the HPA got almost no traffic (2 of 4 pods idle). The load test now
  reconnects every 100 requests (like a client pool's max connection lifetime). In production:
  an L7 load balancer (GKE Gateway) or mesh balances per request.
- 2026-10-09 - Drain before shutdown: `preStop` creates `$DRAIN_FILE`, then sleeps 5 s; while the
  file exists every response carries `Connection: close` - At SIGTERM uvicorn closes idle
  kept-alive connections, and a client sending at that instant got a closed socket (3 of 31,650
  requests failed during a rollout + rollback). With draining: 0 of 31,938. No HTTP endpoint, so
  nobody outside the pod can trigger it. Alt: rely on client retries.
- 2026-10-09 - No Alertmanager: the alert fires and is visible in Prometheus and Grafana, not
  sent - No free notification channel; one pod and routing config less. In production:
  Alertmanager -> Slack/PagerDuty. Alt: Alertmanager with a dummy receiver.
- 2026-10-09 - No persistent volumes for Prometheus and Grafana - Local demo; Grafana holds no
  state because data source and dashboard are provisioned from the repo (dashboards as code).
- 2026-10-09 - `grafana-community/grafana` chart - `grafana/grafana` is deprecated (last release
  January 2026). The 14-day cool-down applies to charts too.
- 2026-10-09 - Prometheus scrapes only itself and annotated pods; all other default jobs off -
  We use no node/cluster metrics (`kubectl top` comes from metrics-server); ~55 MiB of RAM.
- 2026-10-09 - Anonymous read-only Grafana; admin password generated into a Secret - The
  dashboard opens without login (localhost only); edits need the password (`make grafana-password`).
- 2026-10-09 - Drift demo: real held-out months = normal, synthetic = shifted - Both measured
  (PSI ~0.01 vs ~0.5), no invented noise. `real` mode works only where the data is (laptop).
- 2026-10-09 - PSI covers each pod's last 1,000 scores, not a time window - Without traffic it
  keeps its last value (and the alert keeps firing) until new traffic replaces the window.
  Acceptable here; a time window would need storing timestamps per score.
- 2026-10-09 - One CI job builds, smoke-tests in kind, then pushes - The pushed image is the one
  that passed; no 1 GB image moves between jobs. Push only on `main`, never from PRs.
- 2026-10-09 - CI runs the runbook's own `make` targets on a fresh machine - If CI is green, the
  README commands work. Monitoring is not in CI (time, RAM); the dashboard/rule contract test
  covers it. Alt: `helm/kind-action`.
- 2026-10-09 - GitHub Actions pinned by commit SHA, 14-day cool-down like packages - Tags are
  mutable, SHAs are not. Cost: manual SHA updates on upgrade.
- 2026-10-09 - Image tag = `git describe --always --dirty` everywhere (`make image`, `make push`,
  manifests), no `latest` - One way to name an image, traceable to a commit.
- 2026-10-09 - CI makes `.state/mlflow` world-writable - The MLflow pod runs as uid 1000 (the
  owner's laptop user); GitHub's runner user is uid 1001.
- 2026-10-09 - Repository made public (portfolio) - GitHub Free: Actions minutes and package
  storage are free and unlimited for public repos (private: 2,000 min/month, 500 MB, which the
  237 MB image would fill in ~2 versions). History checked: no data was ever committed.
