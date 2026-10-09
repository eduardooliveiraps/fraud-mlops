# fraud-mlops

Fraud scoring service with a train → gate → deploy → monitor loop on a local kind cluster.
Plan, status and design decisions: [docs/ROADMAP.md](docs/ROADMAP.md).

## Quickstart

Requires Python 3.11 (Linux/WSL2).

```bash
make install   # create .venv from the pinned requirements.lock
make lint      # ruff
make test      # pytest, synthetic data only
make data      # Base.csv -> Parquet (paths in configs/config.yaml)
```

`make lock` re-resolves the version ranges in `pyproject.toml` and rewrites `requirements.lock`.

## Local cluster runbook

Requires Docker (Docker Desktop with WSL integration) and ~10 GB RAM for WSL.

```bash
make tools         # pinned kind + kubectl into ~/.local/bin (checksums verified)
make cluster-up    # one-node kind cluster "fraud" (~1.2 GiB RAM)
make mlflow-up     # MLflow server + registry; UI at http://localhost:5000
make mlflow-check  # health check + list experiments
make cluster-down  # delete the cluster; MLflow data in .state/mlflow/ is kept
```

| Symptom | Check |
|---------|-------|
| `docker: ... EOF` while pulling | Network hiccup: run the command again. |
| MLflow pod restarts | `kubectl -n fraud describe pod -l app=mlflow` (look for `OOMKilled`). |
| `localhost:5000` refuses connections | `kubectl -n fraud get pods` until `1/1 Running`. |
| Start with an empty MLflow | `make cluster-down && rm -rf .state/mlflow && make cluster-up mlflow-up` |

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
- **Baseline** (rank by `credit_risk_score` alone, test months): recall at 5% FPR **0.198**,
  PR-AUC **0.037** (a random ranking gives 0.05 and 0.014).


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
