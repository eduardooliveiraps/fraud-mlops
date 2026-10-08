# fraud-mlops

Fraud scoring service with a train → gate → deploy → monitor loop on a local kind cluster.

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
