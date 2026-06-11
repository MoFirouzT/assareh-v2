"""Walk-forward fold geometry — the single source of truth for what is train,
val, and test in every fold (B.3).

Nothing downstream recomputes fold membership: Phase C/E consume `Fold` objects.
Three schemes (D-010, D-016):

- ``walkforward`` (default, honest): expanding-anchored multi-fold. Train always
  starts at the beginning; the val/test blocks tile **backward from the end of
  the data**, so the most recent ~`n_folds` test blocks are scored out-of-sample
  and every earlier bar rolls into the expanding training tail (D-010 —
  end-anchored placement chosen 2026-06-11; see LEARNINGS L-021). Training
  samples whose label-outcome window reaches the held-out region are **purged**,
  and an **embargo** buffer is removed on the test-adjacent side (D-004).
- ``v1_single``: v1's single 75 / 15 / 10 chronological split, reproduced
  exactly — no purge, no embargo (v1 had none). The one-off comparison arm.
- ``cpcv``: reserved for Phase C (D-016); raises ``NotImplementedError`` here so
  the API stays stable without shipping an unfinished implementation.

See D-004 (purge/embargo), D-010 (geometry + sizing), D-016 (cpcv reservation).
"""

import logging
from dataclasses import dataclass
from typing import Literal

import numpy as np
import polars as pl

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Fold:
    """One walk-forward fold. Index arrays are positions into the 15m clock.

    `train_idx` is already post-purge and post-embargo; consumers use it as-is.
    """

    fold_id: int
    train_idx: np.ndarray  # post-purge, post-embargo
    val_idx: np.ndarray  # threshold tuning + early stopping
    test_idx: np.ndarray  # held-out, scored once per fold
    embargo_bars: int


def make_walkforward_folds(
    index: pl.Series,
    *,
    horizon_bars: int = 48,
    n_folds: int = 8,
    anchor_train_bars: int = 70_000,
    test_fold_bars: int = 8_640,
    val_fold_bars: int = 4_032,
    embargo_bars: int = 48,
    holdout_bars: int = 0,
    scheme: Literal["walkforward", "v1_single", "cpcv"] = "walkforward",
) -> list[Fold]:
    """Single source of truth for what is train/val/test in every fold.

    `index` is the 15m decision-clock `open_time` series; only its length (and,
    for `v1_single`, its proportions) is used — folds are integer positions into
    it. `embargo_bars` defaults to `horizon_bars` (D-004); pass `511` alongside
    `horizon_bars=511` to reproduce the v1-faithful horizon. `anchor_train_bars`
    is the *minimum* initial training span required before the earliest fold.

    `holdout_bars` reserves the final `holdout_bars` rows as an untouched held-out
    block (D-042): the walk-forward end-anchors to `n - holdout_bars`, so no fold —
    train, val, or test — ever sees the reserved tail. The block is touched at most
    once, after D-008's threshold is already met (PLAN). Geometry (its length /
    position / evaluation rule) is pinned in D-042 before Phase E; the default `0`
    reserves nothing. Ignored for `v1_single` (the v1-faithful arm had no held-out).
    """
    n = len(index)
    if holdout_bars < 0:
        raise ValueError(f"holdout_bars must be >= 0, got {holdout_bars}")
    if scheme == "cpcv":
        raise NotImplementedError(
            "scheme='cpcv' is reserved for Phase C (D-016); the value exists so "
            "Phase C consumers need not reshape this API."
        )
    if scheme == "v1_single":
        return [_v1_single_fold(n)]
    if scheme != "walkforward":
        raise ValueError(f"scheme must be 'walkforward', 'v1_single' or 'cpcv', got {scheme!r}")

    # Train ends `max(horizon, embargo)` bars before the held-out region: purging
    # drops any label window reaching it; embargo removes the test-adjacent buffer.
    guard = max(horizon_bars, embargo_bars)
    # End-anchored tiling: the last test block ends at `wf_end` (the data end, less
    # any reserved held-out tail); folds tile backward by one (non-overlapping) test
    # block; `anchor_train_bars` is the minimum train before the oldest fold (D-010).
    wf_end = n - holdout_bars
    required = anchor_train_bars + guard + val_fold_bars + n_folds * test_fold_bars + holdout_bars
    if required > n:
        raise ValueError(
            f"need at least {required} bars for {n_folds} folds + a {anchor_train_bars}-bar "
            f"anchor + {holdout_bars}-bar held-out, but the index has only {n}."
        )

    folds: list[Fold] = []
    for f in range(n_folds):
        test_start = wf_end - (n_folds - f) * test_fold_bars
        test_end = test_start + test_fold_bars
        val_start = test_start - val_fold_bars
        train_cut = val_start - guard
        folds.append(
            Fold(
                fold_id=f,
                train_idx=np.arange(0, train_cut),
                val_idx=np.arange(val_start, test_start),
                test_idx=np.arange(test_start, test_end),
                embargo_bars=embargo_bars,
            )
        )

    logger.info(
        "make_walkforward_folds: %d folds, test spans [%d, %d) of %d bars; "
        "held-out=%d; oldest train=%d bars (anchor>=%d)",
        n_folds, folds[0].test_idx[0], wf_end, n, holdout_bars,
        folds[0].train_idx.size, anchor_train_bars,
    )
    return folds


def _v1_single_fold(n: int) -> Fold:
    """v1's single 75 / 15 / 10 chronological split (D-010), reproduced exactly.

    No purge, no embargo — v1 had neither. `val` is v1's 15% early-stopping block;
    `test` is v1's final 10% held-out block.
    """
    train_end = int(n * 0.75)
    val_end = int(n * 0.90)
    return Fold(
        fold_id=0,
        train_idx=np.arange(0, train_end),
        val_idx=np.arange(train_end, val_end),
        test_idx=np.arange(val_end, n),
        embargo_bars=0,
    )
