"""Train -> evaluate -> register -> gate. Entry point: python -m fraud.train --config <yaml>."""

import argparse
import hashlib
import logging
import os
from pathlib import Path

import mlflow
import pandas as pd
from lightgbm import LGBMClassifier, early_stopping
from mlflow import MlflowClient

from fraud.config import Config, TrainConfig, load_config
from fraud.data import load_base
from fraud.drift import bin_fractions, quantile_edges
from fraud.features import FEATURES, prepare_features, score
from fraud.gate import GateResult, run_gate
from fraud.metrics import choose_threshold, evaluate
from fraud.registry import require_tracking_uri
from fraud.schema import TARGET
from fraud.split import time_split
from fraud.validate import validate

logger = logging.getLogger(__name__)

# Set by the code, not the config: they make runs reproducible and comparable.
RESERVED_PARAMS = {"random_state", "n_jobs", "deterministic", "force_col_wise", "metric", "verbose"}


def build_model(cfg: TrainConfig) -> LGBMClassifier:
    reserved = sorted(RESERVED_PARAMS & cfg.params.keys())
    if reserved:
        raise ValueError(f"train.params must not set {reserved}; they are fixed in code")
    unknown = sorted(cfg.params.keys() - LGBMClassifier().get_params().keys())
    if unknown:
        raise ValueError(f"Unknown LightGBM parameters in train.params: {unknown}")
    return LGBMClassifier(
        **cfg.params,
        random_state=cfg.seed,
        n_jobs=cfg.n_jobs,
        deterministic=True,  # same data + seed + threads -> same model
        force_col_wise=True,  # recommended together with deterministic
        metric="average_precision",  # early stopping on valid PR-AUC
        verbose=-1,
    )


def file_sha256(path: Path) -> str:
    """Fingerprint of the training data file (lineage without storing any data)."""
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def train_and_register(
    cfg: Config, df: pd.DataFrame, tags: dict[str, str]
) -> tuple[str, pd.DataFrame]:
    """Train, register a new model version with lineage `tags`. Returns (version, test split)."""
    model = build_model(cfg.train)  # fails on bad params before any heavy work
    split = time_split(validate(df), cfg.split)
    model.fit(
        prepare_features(split.train),
        split.train[TARGET],
        eval_X=prepare_features(split.valid),
        eval_y=split.valid[TARGET],
        callbacks=[early_stopping(cfg.train.early_stopping_rounds, verbose=False)],
    )
    s_valid, s_test = score(model, split.valid), score(model, split.test)
    threshold = choose_threshold(split.valid[TARGET], s_valid, cfg.evaluation)
    valid_metrics = evaluate(split.valid[TARGET], s_valid, threshold, cfg.evaluation)
    test_metrics = evaluate(split.test[TARGET], s_test, threshold, cfg.evaluation)
    edges = quantile_edges(s_test, cfg.monitoring.psi_bins)

    mlflow.set_experiment(cfg.mlflow.experiment)
    with mlflow.start_run():
        mlflow.log_params(
            {
                **cfg.train.params,
                "seed": cfg.train.seed,
                "n_jobs": cfg.train.n_jobs,
                "best_iteration": model.best_iteration_,
                "train_months": list(cfg.split.train_months),
                "valid_months": list(cfg.split.valid_months),
                "test_months": list(cfg.split.test_months),
                "train_rows": len(split.train),
                "target_fpr": cfg.evaluation.target_fpr,
                "cost_false_negative": cfg.evaluation.cost_false_negative,
                "cost_false_positive": cfg.evaluation.cost_false_positive,
            }
        )
        mlflow.log_metrics(
            {
                "threshold": threshold,
                **{f"valid_{k}": v for k, v in valid_metrics.items()},
                **{f"test_{k}": v for k, v in test_metrics.items()},
            }
        )
        mlflow.set_tags(tags)
        # Everything serving needs travels with the model: one URI is enough.
        info = mlflow.lightgbm.log_model(
            model,
            name="model",
            registered_model_name=cfg.mlflow.model_name,
            metadata={
                "threshold": threshold,
                "features": FEATURES,
                "reference_edges": edges,
                "reference_fractions": bin_fractions(s_test, edges),
            },
        )
    version = str(info.registered_model_version)
    for key, value in tags.items():
        MlflowClient().set_model_version_tag(cfg.mlflow.model_name, version, key, value)
    logger.info(
        "Registered %s version %s: test recall_at_fpr %.4f, pr_auc %.4f, threshold %.4f",
        cfg.mlflow.model_name, version,
        test_metrics["recall_at_fpr"], test_metrics["pr_auc"], threshold,
    )
    return version, split.test


def main(argv: list[str] | None = None) -> GateResult:
    parser = argparse.ArgumentParser(description="Train, register and gate a fraud model.")
    parser.add_argument("--config", type=Path, default=Path("configs/config.yaml"))
    args = parser.parse_args(argv)

    require_tracking_uri()
    cfg = load_config(args.config)
    build_model(cfg.train)  # fail fast on bad params before loading 1M rows
    # Lineage: which data and (in a container, where there is no .git) which image built it.
    tags = {"data_sha256": file_sha256(cfg.data.parquet)}
    if image_tag := os.environ.get("IMAGE_TAG"):
        tags["image_tag"] = image_tag
    version, test = train_and_register(cfg, load_base(cfg.data.parquet), tags)
    return run_gate(cfg, version, test)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    main()
