"""MLflow registry helpers. CLI: python -m fraud.registry -> pinned URI of the champion."""

import argparse
import os
from pathlib import Path

from mlflow import MlflowClient

from fraud.config import MlflowConfig, load_config


def require_tracking_uri() -> str:
    # Without it MLflow silently uses a local ./mlruns folder.
    uri = os.environ.get("MLFLOW_TRACKING_URI")
    if not uri:
        raise RuntimeError("MLFLOW_TRACKING_URI is not set (e.g. http://localhost:5000)")
    return uri


def champion_version(cfg: MlflowConfig) -> str | None:
    aliases = MlflowClient().get_registered_model(cfg.model_name).aliases
    # str(): the SQLite store returns an int, the REST API a string.
    return str(aliases[cfg.champion_alias]) if cfg.champion_alias in aliases else None


def pinned_uri(cfg: MlflowConfig, version: str) -> str:
    return f"models:/{cfg.model_name}/{version}"


def main(argv: list[str] | None = None) -> str:
    parser = argparse.ArgumentParser(description="Print the pinned model URI of the champion.")
    parser.add_argument("--config", type=Path, default=Path("configs/config.yaml"))
    args = parser.parse_args(argv)
    require_tracking_uri()
    cfg = load_config(args.config).mlflow
    version = champion_version(cfg)
    if version is None:
        raise LookupError(f"Model '{cfg.model_name}' has no '{cfg.champion_alias}' alias yet")
    uri = pinned_uri(cfg, version)
    print(uri)  # CLI output, read by the Makefile
    return uri


if __name__ == "__main__":
    main()
