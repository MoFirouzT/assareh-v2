"""Sample weights and effective sample size (B.3).

Overlapping labels break the i.i.d. assumption twice over — in training and in
the width of any confidence interval. Two factors compose (D-005):

    weight = class_imbalance × average_uniqueness

then the per-fold weights are renormalized to sum to `N` (the training row count)
so the effective learning rate is independent of fold size. No time decay
(D-017). All of this must be computed on **training-fold labels only** — windows
confined to the fold — or test-period overlap structure leaks into the weights.

Two distinct "effective sample size" notions, do not conflate them (D-005 added
detail, L-022):

- `effective_n_uniqueness` = `Σ ūᵢ`, the LdP count of effectively-independent
  labels. This is the **CI denominator** (`SE ≈ σ/√N_eff`): it falls one-to-two
  orders of magnitude below the raw row count under heavy overlap, which is the
  whole point of an overlap-aware interval.
- `n_eff_kish` = `(Σw)²/Σw²`, the dispersion of a weight *vector*. A useful
  diagnostic for how uneven the training weights are, but it measures weight
  inequality, **not** label overlap — with near-uniform uniqueness it stays ≈ `N`
  and would give over-confident CIs. Not the CI denominator.
"""

import logging

import numpy as np

logger = logging.getLogger(__name__)


def average_uniqueness(label_spans: np.ndarray) -> np.ndarray:
    """LdP ch.4 average uniqueness per sample.

    `label_spans`: shape (n, 2), int — columns are (start_idx, end_idx_exclusive)
    into the 15m decision clock. For each sample, average `1 / concurrency` over
    the bars in its own label window, where concurrency `c_t` counts how many
    labels are live at bar `t`.

    Sanity: `ū_i = 1` when every `c_t = 1` (disjoint labels); `ū_i → 1/n` when all
    `n` labels share one window.
    """
    spans = np.asarray(label_spans)
    if spans.ndim != 2 or spans.shape[1] != 2:
        raise ValueError(f"label_spans must have shape (n, 2), got {spans.shape}")
    if spans.shape[0] == 0:
        return np.empty(0, dtype=float)
    starts = spans[:, 0].astype(np.int64)
    ends = spans[:, 1].astype(np.int64)
    if np.any(ends <= starts):
        raise ValueError("each label span must have end_idx_exclusive > start_idx")

    off = int(starts.min())
    span_len = int(ends.max()) - off
    # Concurrency via a difference array over the union timeline.
    delta = np.zeros(span_len + 1, dtype=np.int64)
    np.add.at(delta, starts - off, 1)
    np.add.at(delta, ends - off, -1)
    concurrency = np.cumsum(delta[:-1])

    # 1/c_t, zero where no label is live (those bars fall in no sample's window,
    # so they never enter a sum below — guarding only avoids a divide warning).
    inv = np.zeros(span_len, dtype=float)
    live = concurrency > 0
    inv[live] = 1.0 / concurrency[live]
    prefix = np.concatenate([[0.0], np.cumsum(inv)])

    lengths = ends - starts
    return (prefix[ends - off] - prefix[starts - off]) / lengths


def class_weights(labels: np.ndarray) -> np.ndarray:
    """v1's class-imbalance weights (D-005), reproduced as positive-vs-rest.

    v1's `QualifiedWeightedConvCandlesDataset` weighted each sample by the
    *opposite* class frequency on a binary positive / non-positive split
    (`models.py:153`, `trainers.py:131-134`): a positive label (`+1`) gets the
    negative fraction, everything else (`0` and `−1`) gets the positive fraction.
    This up-weights the ~minority long class against the dominant rest.
    """
    y = np.asarray(labels)
    n = len(y)
    if n == 0:
        return np.empty(0, dtype=float)
    frac_neg = float(np.mean(y < 0))
    frac_pos = float(np.mean(y > 0))
    return np.where(y > 0, frac_neg, frac_pos).astype(float)


def effective_n_uniqueness(label_spans: np.ndarray) -> float:
    """Overlap-aware effective sample size: `Σ ūᵢ` (LdP). The CI denominator.

    The count of effectively-independent labels given their overlap — far below
    the raw row count when labels overlap heavily. Use this in `SE ≈ σ/√N_eff`
    for test-metric confidence intervals (D-005, L-022), **not** `n_eff_kish`.
    """
    return float(np.sum(average_uniqueness(label_spans)))


def n_eff_kish(weights: np.ndarray) -> float:
    """Kish weight dispersion: `(Σw)² / Σw²`. A diagnostic, **not** the CI N_eff.

    Measures how uneven a weight vector is (equals the count for uniform weights).
    It does not capture label overlap — for overlap-aware CIs use
    `effective_n_uniqueness` (D-005 added detail, L-022).
    """
    w = np.asarray(weights, dtype=float)
    ss = float(np.sum(w**2))
    if ss == 0:
        return 0.0
    return float(np.sum(w) ** 2 / ss)


def renormalize(weights: np.ndarray, target: float | None = None) -> np.ndarray:
    """Scale weights so they sum to `target` (default: the row count `N`)."""
    w = np.asarray(weights, dtype=float)
    if len(w) == 0:
        return w
    total = float(np.sum(w))
    if total == 0:
        raise ValueError("cannot renormalize all-zero weights")
    goal = float(len(w)) if target is None else target
    return w * (goal / total)


def sample_weights(labels: np.ndarray, label_spans: np.ndarray) -> np.ndarray:
    """Final per-sample weights: `class × uniqueness`, renormalized to sum to `N`.

    `labels` and `label_spans` must be aligned and confined to a single training
    fold (D-005 scope rule). No time decay (D-017).
    """
    w = class_weights(labels) * average_uniqueness(label_spans)
    return renormalize(w)
