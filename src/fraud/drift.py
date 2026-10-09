"""Score histograms for drift monitoring: the training side stores a reference, serving compares."""

import numpy as np
from numpy.typing import ArrayLike


def quantile_edges(scores: ArrayLike, n_bins: int) -> list[float]:
    """Inner bin edges at score quantiles, so each reference bin holds ~1/n_bins of the scores.

    Quantile bins (not equal-width) matter here: fraud scores pile up near 0.
    """
    s = np.asarray(scores, dtype=float)
    if s.size == 0:
        raise ValueError("scores is empty")
    edges = np.quantile(s, np.linspace(0, 1, n_bins + 1)[1:-1])
    return np.unique(edges).tolist()  # ties can merge bins


def bin_fractions(scores: ArrayLike, edges: list[float]) -> list[float]:
    """Share of scores per bin: (-inf, e1], (e1, e2], ..., (e_last, inf)."""
    s = np.asarray(scores, dtype=float)
    if s.size == 0:
        raise ValueError("scores is empty")
    counts = np.bincount(np.searchsorted(edges, s, side="left"), minlength=len(edges) + 1)
    return (counts / s.size).tolist()
