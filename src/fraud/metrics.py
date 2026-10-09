"""Model-quality metrics and the cost-based decision threshold.

Higher score = more likely fraud. An application is flagged when score >= threshold.
"""

import numpy as np
from numpy.typing import ArrayLike
from sklearn.metrics import average_precision_score, roc_curve

from fraud.config import EvaluationConfig


def _check(y_true: ArrayLike, scores: ArrayLike) -> tuple[np.ndarray, np.ndarray]:
    y, s = np.asarray(y_true), np.asarray(scores, dtype=float)
    if y.ndim != 1 or y.shape != s.shape:
        raise ValueError(f"y_true and scores must be 1-D, same length; got {y.shape}, {s.shape}")
    if y.size == 0:
        raise ValueError("y_true is empty")
    if not np.isin(y, [0, 1]).all():
        raise ValueError("y_true must contain only 0 and 1")
    if y.min() == y.max():
        raise ValueError("y_true must contain both classes (metrics are undefined otherwise)")
    if not np.isfinite(s).all():
        raise ValueError("scores must be finite")
    return y.astype(int), s


def pr_auc(y_true: ArrayLike, scores: ArrayLike) -> float:
    """Area under the precision-recall curve, as average precision (no optimistic interpolation)."""
    y, s = _check(y_true, scores)
    return float(average_precision_score(y, s))


def recall_at_fpr(y_true: ArrayLike, scores: ArrayLike, target_fpr: float) -> float:
    """Highest recall reachable by some threshold whose false-positive rate is <= target_fpr."""
    if not 0 < target_fpr < 1:
        raise ValueError(f"target_fpr must be in (0, 1), got {target_fpr}")
    y, s = _check(y_true, scores)
    fpr, tpr, _ = roc_curve(y, s, drop_intermediate=False)
    return float(tpr[fpr <= target_fpr].max())


def choose_threshold(y_true: ArrayLike, scores: ArrayLike, cfg: EvaluationConfig) -> float:
    """Threshold with the lowest total cost: cost_fn * missed frauds + cost_fp * false alarms.

    Returns inf if flagging nothing is cheapest. Ties go to the highest threshold (fewer flags).
    """
    y, s = _check(y_true, scores)
    fpr, tpr, thresholds = roc_curve(y, s, drop_intermediate=False)  # thresholds[0] = inf
    missed_frauds = (1 - tpr) * y.sum()
    false_alarms = fpr * (y.size - y.sum())
    cost = cfg.cost_false_negative * missed_frauds + cfg.cost_false_positive * false_alarms
    return float(thresholds[np.argmin(cost)])


def evaluate(
    y_true: ArrayLike, scores: ArrayLike, threshold: float, cfg: EvaluationConfig
) -> dict[str, float]:
    """Threshold-free quality (pr_auc, recall_at_fpr) plus results at the decision threshold."""
    y, s = _check(y_true, scores)
    flagged = s >= threshold
    tp = int((flagged & (y == 1)).sum())
    fp = int((flagged & (y == 0)).sum())
    fn = int((~flagged & (y == 1)).sum())
    positives, negatives = tp + fn, y.size - (tp + fn)
    cost = cfg.cost_false_negative * fn + cfg.cost_false_positive * fp
    return {
        "pr_auc": pr_auc(y, s),
        "recall_at_fpr": recall_at_fpr(y, s, cfg.target_fpr),
        "precision": tp / (tp + fp) if tp + fp else 0.0,
        "recall": tp / positives,
        "fpr": fp / negatives,
        "cost_per_1k": 1000 * cost / y.size,
    }
