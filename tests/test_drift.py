import numpy as np
import pytest

from fraud.drift import bin_fractions, quantile_edges


def test_quantile_bins_hold_equal_shares():
    scores = np.arange(1000) / 1000
    edges = quantile_edges(scores, 10)
    assert len(edges) == 9
    assert bin_fractions(scores, edges) == pytest.approx([0.1] * 10)


def test_skewed_scores_still_get_balanced_bins():
    scores = np.random.default_rng(0).beta(0.5, 30, 10_000)  # piled up near 0, like fraud scores
    assert bin_fractions(scores, quantile_edges(scores, 5)) == pytest.approx([0.2] * 5, abs=0.01)


def test_tied_scores_merge_bins():
    edges = quantile_edges([0.3] * 100, 10)
    assert edges == [0.3]
    assert bin_fractions([0.3] * 100, edges) == [1.0, 0.0]


def test_value_on_an_edge_goes_to_the_lower_bin():
    assert bin_fractions([0.0, 0.5, 1.0], [0.5]) == pytest.approx([2 / 3, 1 / 3])


def test_empty_scores_fail():
    with pytest.raises(ValueError, match="empty"):
        quantile_edges([], 10)
    with pytest.raises(ValueError, match="empty"):
        bin_fractions([], [0.5])
