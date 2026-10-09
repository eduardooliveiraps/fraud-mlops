"""Champion/challenger gate: move the champion alias only if the candidate wins on the same data."""

import logging
from dataclasses import dataclass

import mlflow
import pandas as pd
from mlflow import MlflowClient

from fraud.config import Config, GateConfig
from fraud.features import score
from fraud.metrics import pr_auc, recall_at_fpr
from fraud.registry import champion_version as get_champion_version
from fraud.registry import pinned_uri
from fraud.schema import TARGET

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GateResult:
    promoted: bool
    reason: str
    candidate: dict[str, float]
    champion: dict[str, float] | None
    champion_version: str | None


def compare(
    candidate: dict[str, float], champion: dict[str, float] | None, cfg: GateConfig
) -> tuple[bool, str]:
    """Decision rule. Both metric dicts must come from the same test data."""
    if champion is None:
        return True, "no champion yet"
    recall_gain = candidate["recall_at_fpr"] - champion["recall_at_fpr"]
    pr_auc_gain = candidate["pr_auc"] - champion["pr_auc"]
    summary = f"recall_at_fpr {recall_gain:+.4f}, pr_auc {pr_auc_gain:+.4f}"
    if recall_gain < cfg.min_recall_gain:
        return False, f"{summary}: recall gain below {cfg.min_recall_gain}"
    if -pr_auc_gain > cfg.max_pr_auc_drop:
        return False, f"{summary}: pr_auc drop above {cfg.max_pr_auc_drop}"
    return True, summary


def _quality(model_uri: str, test: pd.DataFrame, target_fpr: float) -> dict[str, float]:
    # Load from the registry (not from memory): we judge exactly what was registered.
    scores = score(mlflow.lightgbm.load_model(model_uri), test)
    return {
        "recall_at_fpr": recall_at_fpr(test[TARGET], scores, target_fpr),
        "pr_auc": pr_auc(test[TARGET], scores),
    }


def run_gate(cfg: Config, version: str, test: pd.DataFrame) -> GateResult:
    """Score candidate and current champion on `test`, decide, tag the version, maybe move alias."""
    client = MlflowClient()
    name, alias = cfg.mlflow.model_name, cfg.mlflow.champion_alias
    target_fpr = cfg.evaluation.target_fpr
    candidate = _quality(pinned_uri(cfg.mlflow, version), test, target_fpr)

    champion_version = get_champion_version(cfg.mlflow)
    champion = (
        _quality(pinned_uri(cfg.mlflow, champion_version), test, target_fpr)
        if champion_version
        else None
    )
    promoted, reason = compare(candidate, champion, cfg.gate)
    decision = "promoted" if promoted else "rejected"

    client.set_model_version_tag(name, version, "gate_decision", decision)
    client.set_model_version_tag(name, version, "gate_reason", reason)
    if champion_version:
        client.set_model_version_tag(name, version, "gate_compared_to", champion_version)
    if promoted:
        client.set_registered_model_alias(name, alias, version)
    logger.info(
        "Gate: version %s %s (%s). Champion is now version %s",
        version, decision, reason,
        version if promoted else champion_version,
    )
    return GateResult(promoted, reason, candidate, champion, champion_version)
