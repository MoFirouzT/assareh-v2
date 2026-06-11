"""Tests for target diagnostics (B.2). See PHASE_B B.2 and D-007."""

import polars as pl

from assareh.labels import breakeven_precost, make_labels, target_stats

FLAT = (100.0, 100.0, 100.0, 100.0)
PATR = 0.01


def test_breakeven_precost_is_38_5_percent():
    assert breakeven_precost(4.0, 2.5) == 2.5 / 6.5


def _two_resolvable_decisions(synthetic_barrier_path):
    # 4 fifteen-minute buckets. Decision 0 hits the profit barrier at bar 15
    # (one bar forward); decision 1 sees a flat window (no-touch); decisions 2–3
    # run off the data tail (incomplete).
    bars = [FLAT] * 15 + [(100.0, 105.0, 100.0, 101.0)] + [FLAT] * 44
    df1m, df15 = synthetic_barrier_path(bars, patr=PATR)
    res = make_labels(df15, df1m, horizon_bars=2)
    return res, df1m


def test_class_balance_and_timeout_rate(synthetic_barrier_path):
    res, df1m = _two_resolvable_decisions(synthetic_barrier_path)
    stats = target_stats(res, df1m)

    assert stats["n_complete"] == 2
    assert stats["positive_rate"] == 0.5
    assert stats["no_touch_rate"] == 0.5  # the timeout rate v1 never logged
    assert stats["negative_rate"] == 0.0
    total = stats["positive_rate"] + stats["no_touch_rate"] + stats["negative_rate"]
    assert total == 1.0


def test_breakeven_carried_from_label_config(synthetic_barrier_path):
    res, df1m = _two_resolvable_decisions(synthetic_barrier_path)
    stats = target_stats(res, df1m)
    assert stats["breakeven_precost"] == 2.5 / 6.5


def test_overlap_forward_distance(synthetic_barrier_path):
    res, df1m = _two_resolvable_decisions(synthetic_barrier_path)
    stats = target_stats(res, df1m)
    # Decision 0's profit barrier is hit in the first forward 15m bar ⇒ 1 bar held.
    assert stats["median_touch_bars"] == 1.0
    assert stats["median_span_bars"] is not None  # timeouts folded in at horizon


def test_per_quarter_is_frame_with_rates(synthetic_barrier_path):
    res, df1m = _two_resolvable_decisions(synthetic_barrier_path)
    pq = target_stats(res, df1m)["per_quarter"]
    assert isinstance(pq, pl.DataFrame)
    assert set(pq.columns) == {"quarter", "n", "positive_rate", "no_touch_rate", "negative_rate"}
    assert pq["n"].sum() == res.frame["is_complete"].sum()


def test_accepts_bare_frame_without_config(synthetic_barrier_path):
    res, _ = _two_resolvable_decisions(synthetic_barrier_path)
    stats = target_stats(res.frame)  # no LabelResult attrs, no df1m
    assert "breakeven_precost" not in stats
    assert "median_touch_bars" not in stats
    assert stats["positive_rate"] == 0.5
