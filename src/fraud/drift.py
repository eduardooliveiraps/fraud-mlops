"""Score histograms for drift monitoring: the training side stores a reference, serving compares."""

import numpy as np
from numpy.typing import ArrayLike

# Empty bins are clipped to this share so ln(actual / expected) stays finite.
PSI_EPSILON = 1e-4


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


def psi(expected: ArrayLike, actual: ArrayLike) -> float:
    """Population Stability Index: sum((actual - expected) * ln(actual / expected)) over bins.

    Rule of thumb: < 0.1 stable, 0.1-0.2 moderate shift, > 0.2 significant shift.
    """
    e, a = np.asarray(expected, dtype=float), np.asarray(actual, dtype=float)
    if e.ndim != 1 or e.shape != a.shape or e.size < 2:
        raise ValueError(f"Need 1-D bin shares of equal length >= 2, got {e.shape}, {a.shape}")
    e, a = np.clip(e, PSI_EPSILON, None), np.clip(a, PSI_EPSILON, None)
    return float(np.sum((a - e) * np.log(a / e)))
