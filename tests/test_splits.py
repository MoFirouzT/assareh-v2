"""Tests for walk-forward fold geometry (B.3). See D-004 and D-010."""

import numpy as np
import polars as pl
import pytest

from assareh.splits import Fold, make_walkforward_folds

# Small but well-formed geometry: anchor 50, three 20-bar test folds, 10-bar val.
KW = dict(
    horizon_bars=5,
    n_folds=3,
    anchor_train_bars=50,
    test_fold_bars=20,
    val_fold_bars=10,
    embargo_bars=5,
)


def _index(n: int) -> pl.Series:
    return pl.Series("open_time", range(n))


def _folds(n: int = 200) -> list[Fold]:
    return make_walkforward_folds(_index(n), **KW)


def test_purge_no_train_window_overlaps_test():
    for fold in _folds():
        last_train = int(fold.train_idx[-1])
        # The label-outcome window [i, i+horizon] of the last kept train sample
        # must end strictly before the held-out region.
        assert last_train + KW["horizon_bars"] < int(fold.test_idx[0])
        assert np.intersect1d(fold.train_idx, fold.test_idx).size == 0


def test_embargo_gap_at_least_embargo_bars():
    for fold in _folds():
        gap = int(fold.test_idx[0]) - int(fold.train_idx[-1]) - 1
        assert gap >= fold.embargo_bars


def test_chronological_ordering_train_val_test():
    for fold in _folds():
        assert int(fold.train_idx[-1]) < int(fold.val_idx[0])
        assert int(fold.val_idx[-1]) < int(fold.test_idx[0])


def test_expanding_train_and_non_overlapping_tests():
    folds = _folds()
    for a, b in zip(folds, folds[1:]):
        assert b.train_idx[-1] > a.train_idx[-1]  # train expands
        assert int(b.test_idx[0]) == int(a.test_idx[-1]) + 1  # tests tile, no overlap


def test_test_fold_size_matches_config():
    for fold in _folds():
        assert fold.test_idx.size == KW["test_fold_bars"]
        assert fold.val_idx.size == KW["val_fold_bars"]


def test_end_anchored_last_test_reaches_data_end():
    n = 200
    folds = _folds(n)
    assert int(folds[-1].test_idx[-1]) == n - 1  # most recent block is scored


def test_anchor_is_minimum_initial_train():
    # fold 0 (oldest) must train on at least the anchor before the first fold.
    folds = _folds()
    assert folds[0].train_idx.size >= KW["anchor_train_bars"]


def test_v1_single_reproduces_75_15_10():
    n = 1000
    (fold,) = make_walkforward_folds(_index(n), scheme="v1_single")
    assert fold.train_idx.size == 750
    assert fold.val_idx.size == 150
    assert fold.test_idx.size == 100
    # contiguous, full coverage, no purge gap (v1 had none)
    assert int(fold.train_idx[-1]) == 749
    assert int(fold.val_idx[0]) == 750
    assert int(fold.test_idx[0]) == 900
    assert int(fold.test_idx[-1]) == 999
    assert fold.embargo_bars == 0


def test_cpcv_scheme_is_reserved_not_implemented():
    with pytest.raises(NotImplementedError):
        make_walkforward_folds(_index(200), scheme="cpcv")


def test_unknown_scheme_raises():
    with pytest.raises(ValueError):
        make_walkforward_folds(_index(200), scheme="bogus")  # type: ignore[arg-type]


def test_folds_that_do_not_fit_raise():
    with pytest.raises(ValueError, match="only"):
        _folds(n=100)  # too short for 3 folds


def test_embargo_wider_than_horizon_widens_the_purge():
    wide = dict(KW, embargo_bars=12)  # > horizon 5
    for fold in make_walkforward_folds(_index(200), **wide):
        gap = int(fold.val_idx[0]) - int(fold.train_idx[-1]) - 1
        assert gap >= 12
