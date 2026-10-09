import numpy as np
import pytest

from fraud.config import EvaluationConfig
from fraud.data import make_synthetic
from fraud.metrics import choose_threshold, evaluate, pr_auc, recall_at_fpr
from fraud.schema import TARGET

CFG = EvaluationConfig(target_fpr=0.05, cost_false_negative=20.0, cost_false_positive=1.0)

# 4 frauds, 20 legit. Ranked by score: P(0.9) N(0.8) P(0.7) N(0.6) P(0.5) P(0.2), then 18 N(0.1).
Y = np.array([1, 0, 1, 0, 1, 1] + [0] * 18)
S = np.array([0.9, 0.8, 0.7, 0.6, 0.5, 0.2] + [0.1] * 18)


def test_perfect_classifier():
    y, s = [0, 0, 1, 1], [0.1, 0.2, 0.8, 0.9]
    assert pr_auc(y, s) == pytest.approx(1.0)
    assert recall_at_fpr(y, s, 0.05) == pytest.approx(1.0)


def test_inverted_classifier():
    y, s = [0, 0, 1, 1], [0.9, 0.8, 0.2, 0.1]
    assert pr_auc(y, s) == pytest.approx(0.5 * 1 / 3 + 0.5 * 2 / 4)
    assert recall_at_fpr(y, s, 0.05) == 0.0


def test_recall_at_fpr_hand_computed():
    assert recall_at_fpr(Y, S, 0.05) == pytest.approx(0.5)  # 1 false alarm allowed
    assert recall_at_fpr(Y, S, 0.10) == pytest.approx(1.0)  # 2 false alarms allowed


def test_tied_scores_are_not_split():
    # No threshold separates tied scores, so recall is 0 below fpr = 1.
    assert recall_at_fpr([0, 1, 0, 1], [0.5, 0.5, 0.5, 0.5], 0.5) == 0.0


def test_pr_auc_hand_computed():
    assert pr_auc(Y, S) == pytest.approx((1 + 2 / 3 + 3 / 5 + 4 / 6) / 4)


def test_choose_threshold_minimises_cost():
    # Costs (20*FN + 1*FP): inf 80, 0.9 60, 0.8 61, 0.7 41, 0.6 42, 0.5 22, 0.2 2, 0.1 20.
    assert choose_threshold(Y, S, CFG) == 0.2


def test_choose_threshold_ties_go_to_highest_and_can_flag_nothing():
    cfg = EvaluationConfig(target_fpr=0.05, cost_false_negative=1.0, cost_false_positive=1.0)
    # Flag nothing: cost 2. Flag everything (0.1): cost 2. Others cost more.
    assert choose_threshold([0, 0, 1, 1], [0.9, 0.8, 0.2, 0.1], cfg) == np.inf


def test_evaluate_hand_computed():
    m = evaluate(Y, S, threshold=0.2, cfg=CFG)  # flags 4 frauds + 2 legit
    assert m["precision"] == pytest.approx(4 / 6)
    assert m["recall"] == pytest.approx(1.0)
    assert m["fpr"] == pytest.approx(2 / 20)
    assert m["cost_per_1k"] == pytest.approx(1000 * 2 / 24)
    assert m["recall_at_fpr"] == pytest.approx(0.5)
    assert set(m) == {"pr_auc", "recall_at_fpr", "precision", "recall", "fpr", "cost_per_1k"}


def test_evaluate_flagging_nothing():
    m = evaluate(Y, S, threshold=np.inf, cfg=CFG)
    assert (m["precision"], m["recall"], m["fpr"]) == (0.0, 0.0, 0.0)
    assert m["cost_per_1k"] == pytest.approx(1000 * 20 * 4 / 24)


def test_informative_feature_beats_random_on_synthetic():
    df = make_synthetic(n_rows=20000, seed=3)
    y = df[TARGET]
    random_scores = np.random.default_rng(0).random(len(df))
    assert recall_at_fpr(y, df["credit_risk_score"], 0.05) > 0.05 + 0.03
    assert recall_at_fpr(y, random_scores, 0.05) == pytest.approx(0.05, abs=0.03)


@pytest.mark.parametrize(
    ("y", "s", "error"),
    [
        ([0, 1], [0.1], "same length"),
        ([[0, 1]], [[0.1, 0.2]], "1-D"),
        ([], [], "empty"),
        ([0, 0, 0], [0.1, 0.2, 0.3], "both classes"),
        ([0, 2], [0.1, 0.2], "only 0 and 1"),
        ([0, 1], [0.1, np.nan], "finite"),
    ],
)
def test_bad_inputs_fail(y, s, error):
    for fn in (lambda: pr_auc(y, s), lambda: choose_threshold(y, s, CFG)):
        with pytest.raises(ValueError, match=error):
            fn()


@pytest.mark.parametrize("target", [0.0, 1.0, -0.1])
def test_bad_target_fpr_fails(target):
    with pytest.raises(ValueError, match="target_fpr"):
        recall_at_fpr([0, 1], [0.1, 0.9], target)
