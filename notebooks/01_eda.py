# %% [markdown]
# # 01 - EDA of BAF Base (aggregates only)
# Run from the repo root (VS Code "Run Cell", or `python notebooks/01_eda.py`).
# License rule: print aggregates only, never rows.

# %%
from pathlib import Path

import pandas as pd

from fraud.config import load_config
from fraud.data import load_base
from fraud.metrics import pr_auc, recall_at_fpr
from fraud.schema import CATEGORICAL_COLS, NUMERIC_COLS, TARGET, TIME_COL
from fraud.split import time_split

cfg = load_config(Path("configs/config.yaml"))
df = load_base(cfg.data.parquet)
print(f"{len(df):,} rows, {df.shape[1]} columns, fraud rate {df[TARGET].mean():.4f}")

# %% [markdown]
# ## Volume and fraud rate per month
# Decides whether the time split (train 0-4, valid 5, test 6-7) has enough frauds everywhere.

# %%
by_month = df.groupby(TIME_COL)[TARGET].agg(rows="size", frauds="sum", fraud_rate="mean")
print(by_month.to_string(formatters={"rows": "{:,}".format, "fraud_rate": "{:.4f}".format}))

# %% [markdown]
# ## Missing values
# The BAF datasheet encodes missing values as -1 (any negative for intended_balcon_amount).
# Negatives elsewhere can be real values (e.g. credit_risk_score), so both shares are shown.

# %%
numeric = df[list(NUMERIC_COLS)]
missing = pd.DataFrame(
    {"share_eq_minus1": (numeric == -1).mean(), "share_negative": (numeric < 0).mean()}
)
print(missing[missing.share_negative > 0].sort_values("share_negative", ascending=False).round(4))

# %% [markdown]
# ## Constant columns (carry no information; candidates to drop in the features step)

# %%
n_unique = df[list(NUMERIC_COLS) + list(CATEGORICAL_COLS)].nunique()
print("constant:", n_unique[n_unique == 1].index.tolist())

# %% [markdown]
# ## Baseline: rank applications by one column
# Any model must beat this. Higher credit_risk_score = riskier.

# %%
split = time_split(df, cfg.split)
y, score = split.test[TARGET], split.test["credit_risk_score"]
baseline = pd.Series(
    {
        "pr_auc": pr_auc(y, score),
        f"recall_at_{cfg.evaluation.target_fpr:.0%}_fpr": recall_at_fpr(
            y, score, cfg.evaluation.target_fpr
        ),
        "test_fraud_rate": y.mean(),
    }
)
print(baseline.round(4).to_string())
