"""Tests for sample weights and effective sample size (B.3). See D-005, D-017."""

import numpy as np
import pytest

from assareh.splits import (
    average_uniqueness,
    class_weights,
    effective_n_uniqueness,
    n_eff_kish,
    renormalize,
    sample_weights,
)


# --- average uniqueness (LdP ch.4) ----------------------------------------


def test_uniqueness_fully_overlapping_approaches_one_over_n():
    spans = np.array([[0, 10]] * 5)  # five labels share one window
    u = average_uniqueness(spans)
    assert np.allclose(u, 1 / 5)


def test_uniqueness_fully_disjoint_is_one():
    spans = np.array([[0, 5], [5, 10], [10, 15]])  # contiguous, non-overlapping
    u = average_uniqueness(spans)
    assert np.allclose(u, 1.0)


def test_uniqueness_partial_overlap_is_analytic():
    # [0,4) and [2,6): concurrency is 1,1,2,2,1,1 over t=0..5.
    # Each window averages 1/c over its four bars = (1+1+0.5+0.5)/4 = 0.75.
    spans = np.array([[0, 4], [2, 6]])
    assert np.allclose(average_uniqueness(spans), 0.75)


def test_uniqueness_rejects_bad_spans():
    with pytest.raises(ValueError):
        average_uniqueness(np.array([[5, 5]]))  # end not > start


def test_effective_n_captures_overlap_unlike_kish():
    # 100 labels sharing one window: ~1 effectively-independent label, not ~100.
    spans = np.array([[0, 50]] * 100)
    assert effective_n_uniqueness(spans) == pytest.approx(1.0)
    # Kish on uniform weights would (wrongly) report ~100 — the L-022 distinction.
    assert n_eff_kish(np.ones(100)) == pytest.approx(100.0)


def test_effective_n_disjoint_equals_count():
    spans = np.array([[0, 5], [5, 10], [10, 15]])
    assert effective_n_uniqueness(spans) == pytest.approx(3.0)


# --- class weights (v1-faithful positive-vs-rest) -------------------------


def test_class_weights_positive_gets_negative_fraction():
    y = np.array([-1, -1, 0, 1])  # frac_neg = 0.5, frac_pos = 0.25
    w = class_weights(y)
    assert w[3] == 0.5  # the +1 sample gets the negative fraction
    assert np.all(w[:3] == 0.25)  # 0 and -1 get the positive fraction


# --- Kish N_eff and renormalization ---------------------------------------


def test_n_eff_equal_weights_equals_count():
    assert n_eff_kish(np.ones(10)) == pytest.approx(10.0)


def test_n_eff_drops_with_concentration():
    w = np.array([100.0, 1.0, 1.0, 1.0])
    assert n_eff_kish(w) < 4.0


def test_renormalize_sums_to_n():
    w = np.array([0.1, 0.2, 0.3, 0.4, 0.5])
    out = renormalize(w)
    assert out.sum() == pytest.approx(len(w))


def test_renormalize_custom_target():
    w = np.array([1.0, 3.0])
    assert renormalize(w, target=8.0).sum() == pytest.approx(8.0)


def test_sample_weights_compose_and_renormalize():
    labels = np.array([1, -1, 0, 1])
    spans = np.array([[0, 4], [1, 5], [2, 6], [3, 7]])
    w = sample_weights(labels, spans)
    assert w.sum() == pytest.approx(len(labels))  # renormalized to N (asserted per D-005)
    assert np.all(w >= 0)
