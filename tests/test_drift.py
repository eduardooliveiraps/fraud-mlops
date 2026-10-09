import numpy as np
import pytest

from fraud.drift import bin_fractions, psi, quantile_edges


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


def test_psi_is_zero_for_identical_shares():
    assert psi([0.2] * 5, [0.2] * 5) == pytest.approx(0.0)


def test_psi_hand_computed():
    # (0.9 - 0.5) ln(0.9 / 0.5) + (0.1 - 0.5) ln(0.1 / 0.5)
    expected = 0.4 * np.log(1.8) + 0.4 * np.log(5)
    assert psi([0.5, 0.5], [0.9, 0.1]) == pytest.approx(expected)


def test_psi_stays_finite_with_empty_bins():
    assert np.isfinite(psi([0.5, 0.5], [1.0, 0.0]))


def test_psi_detects_a_shift_but_not_noise():
    rng = np.random.default_rng(0)
    reference = rng.beta(0.5, 30, 50_000)
    edges = quantile_edges(reference, 10)
    expected = bin_fractions(reference, edges)
    same = bin_fractions(rng.beta(0.5, 30, 2000), edges)
    shifted = bin_fractions(rng.beta(0.5, 10, 2000), edges)  # 3x higher scores
    assert psi(expected, same) < 0.05
    assert psi(expected, shifted) > 0.2


@pytest.mark.parametrize(
    ("e", "a"), [([0.5, 0.5], [1.0]), ([1.0], [1.0]), ([[0.5, 0.5]], [[0.5, 0.5]])]
)
def test_psi_bad_shapes_fail(e, a):
    with pytest.raises(ValueError, match="bin shares"):
        psi(e, a)
