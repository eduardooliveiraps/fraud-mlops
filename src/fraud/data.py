"""Load the BAF Base dataset and generate schema-matching synthetic data for tests/CI."""

import argparse
import logging
from pathlib import Path

import numpy as np
import pandas as pd

from fraud.config import load_config
from fraud.schema import CATEGORICAL_COLS, COLUMNS, NUMERIC_COLS, TARGET, TIME_COL

logger = logging.getLogger(__name__)


def csv_to_parquet(csv_path: Path, parquet_path: Path) -> Path:
    """Convert the raw CSV to Parquet (smaller on disk, keeps dtypes, much faster to load)."""
    if not csv_path.is_file():
        raise FileNotFoundError(
            f"Raw CSV not found: {csv_path}. Download Base.csv from Kaggle (see README)."
        )
    df = pd.read_csv(csv_path)
    parquet_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(parquet_path, index=False)
    logger.info("Wrote %s (%d rows, %d columns)", parquet_path, *df.shape)
    return parquet_path


def load_base(path: Path) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(f"Parquet not found: {path}. Run `make data` first.")
    return pd.read_parquet(path)


def make_synthetic(n_rows: int = 5000, seed: int = 0) -> pd.DataFrame:
    """Fake data with the real schema, from hand-written ranges only (never from real data).

    Fraud depends weakly on credit_risk_score (up) and name_email_similarity (down),
    so a model has something to learn in tests.
    """
    rng = np.random.default_rng(seed)
    n = n_rows

    def binary(p: float) -> np.ndarray:
        return (rng.random(n) < p).astype("int64")

    def maybe_missing(values: np.ndarray, p_missing: float) -> np.ndarray:
        # BAF encodes missing numeric values as -1.
        return np.where(rng.random(n) < p_missing, -1, values)

    df = pd.DataFrame(
        {
            "income": rng.integers(1, 10, n) / 10,
            "name_email_similarity": rng.random(n),
            "prev_address_months_count": maybe_missing(rng.integers(0, 300, n), 0.6),
            "current_address_months_count": rng.integers(0, 400, n),
            "customer_age": rng.integers(1, 10, n) * 10,
            "days_since_request": np.clip(rng.exponential(1.0, n), 0, 75),
            "intended_balcon_amount": rng.uniform(-10, 100, n),
            "payment_type": rng.choice(CATEGORICAL_COLS["payment_type"], n),
            "zip_count_4w": rng.integers(1, 6000, n),
            "velocity_6h": rng.uniform(0, 15000, n),
            "velocity_24h": rng.uniform(1000, 9000, n),
            "velocity_4w": rng.uniform(3000, 7000, n),
            "bank_branch_count_8w": rng.integers(0, 2000, n),
            "date_of_birth_distinct_emails_4w": rng.integers(0, 30, n),
            "employment_status": rng.choice(CATEGORICAL_COLS["employment_status"], n),
            "credit_risk_score": rng.integers(-150, 380, n),
            "email_is_free": binary(0.5),
            "housing_status": rng.choice(CATEGORICAL_COLS["housing_status"], n),
            "phone_home_valid": binary(0.4),
            "phone_mobile_valid": binary(0.9),
            "bank_months_count": maybe_missing(rng.integers(1, 32, n), 0.25),
            "has_other_cards": binary(0.2),
            "proposed_credit_limit": rng.choice([200.0, 500.0, 1000.0, 1500.0, 2000.0], n),
            "foreign_request": binary(0.03),
            "source": rng.choice(CATEGORICAL_COLS["source"], n, p=[0.99, 0.01]),
            "session_length_in_minutes": np.clip(rng.exponential(7.0, n), 0, 85),
            "device_os": rng.choice(CATEGORICAL_COLS["device_os"], n),
            "keep_alive_session": binary(0.6),
            "device_distinct_emails_8w": rng.choice([-1, 0, 1, 2], n, p=[0.01, 0.02, 0.9, 0.07]),
            "device_fraud_count": np.zeros(n, dtype="int64"),
            TIME_COL: rng.integers(0, 8, n),
        }
    )

    risk = (df["credit_risk_score"] + 150) / 530  # scaled to [0, 1)
    logit = -3.9 + 2.0 * risk - 1.5 * df["name_email_similarity"]
    p_fraud = 1 / (1 + np.exp(-logit))
    df[TARGET] = (rng.random(n) < p_fraud).astype("int64")

    df = df.astype(NUMERIC_COLS)
    return df[COLUMNS]


def main(argv: list[str] | None = None) -> None:
    """Build the Parquet file from the raw CSV and log aggregate facts only."""
    parser = argparse.ArgumentParser(description="Convert BAF Base.csv to Parquet.")
    parser.add_argument("--config", type=Path, default=Path("configs/config.yaml"))
    args = parser.parse_args(argv)

    cfg = load_config(args.config)
    df = load_base(csv_to_parquet(cfg.data.raw_csv, cfg.data.parquet))
    months = df[TIME_COL]
    logger.info(
        "Fraud rate: %.4f, months %d-%d", df[TARGET].mean(), months.min(), months.max()
    )


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    main()
