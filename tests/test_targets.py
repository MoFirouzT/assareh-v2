"""Tests for the triple-barrier labeler (B.1). See PHASE_B B.1 and D-006/027/028/029/036/038."""

import polars as pl

from assareh.labels import LABEL_SCHEMA, make_labels

# Decision-bar setup: 15 flat 1m bars → one 15m bar closing at 100, pATR 1% ⇒
# profit_level = (1 + 4·0.01)·100 = 104, stop_level = (1 − 2.5·0.01)·100 = 97.5.
FLAT = (100.0, 100.0, 100.0, 100.0)
DECISION = [FLAT] * 15
PATR = 0.01


def _rt3(res, row=0):
    return res.frame["rt3"][row]


# --- basic first-touch ordering (honest 1m arm) ---------------------------


def test_profit_then_stop_is_long(synthetic_barrier_path):
    bars = DECISION + [(100.0, 105.0, 100.0, 101.0)] + [FLAT] * 29  # target at bar 15
    df1m, df15 = synthetic_barrier_path(bars, patr=PATR)
    res = make_labels(df15, df1m, horizon_bars=2)
    assert _rt3(res) == 1
    assert res.frame["is_complete"][0] is True


def test_stop_then_profit_is_short(synthetic_barrier_path):
    bars = DECISION + [(100.0, 100.0, 96.0, 99.0)] + [FLAT] * 29  # stop at bar 15
    df1m, df15 = synthetic_barrier_path(bars, patr=PATR)
    res = make_labels(df15, df1m, horizon_bars=2)
    assert _rt3(res) == -1


def test_no_touch_is_zero(synthetic_barrier_path):
    bars = DECISION + [FLAT] * 30  # fully-observed horizon, nothing touched
    df1m, df15 = synthetic_barrier_path(bars, patr=PATR)
    res = make_labels(df15, df1m, horizon_bars=2)
    assert _rt3(res) == 0
    assert res.frame["is_complete"][0] is True


# --- D-006: 1m honest vs 15m v1-faithful disagree on a same-15m-bar straddle


def test_honest_and_faithful_disagree_on_same_15m_bar(synthetic_barrier_path):
    # 15m bucket 1 straddles both barriers, but the 1m path hits the stop first.
    bucket1 = [(100.0, 100.0, 96.0, 98.0)] + [FLAT] * 4 + [(100.0, 105.0, 100.0, 101.0)] + [FLAT] * 9
    bars = DECISION + bucket1 + [FLAT] * 15
    df1m, df15 = synthetic_barrier_path(bars, patr=PATR)

    honest = make_labels(df15, df1m, horizon_bars=2, resolution="1m")
    faithful = make_labels(df15, df1m, horizon_bars=2, resolution="15m")

    assert _rt3(honest) == -1  # 1m: stop (bar 15) before target (bar 20)
    assert _rt3(faithful) == 1  # 15m optimistic: favorable barrier assumed first
    assert honest.frame["ambig_1m"][0] is False  # stop & target in different 1m bars
    assert honest.frame["ambig_15m"][0] is True  # but the same 15m bar
    assert faithful.frame["ambig_15m"][0] is True


# --- D-028: intra-1m-bar tie-break resolves deterministically on close vs open


def test_tie_break_close_above_open_is_long(synthetic_barrier_path):
    bars = DECISION + [(100.0, 105.0, 96.0, 101.0)] + [FLAT] * 29  # one bar straddles both
    df1m, df15 = synthetic_barrier_path(bars, patr=PATR)
    res = make_labels(df15, df1m, horizon_bars=2)
    assert _rt3(res) == 1  # close > open ⇒ high (profit) first
    assert res.frame["ambig_1m"][0] is True


def test_tie_break_close_below_open_is_short(synthetic_barrier_path):
    bars = DECISION + [(100.0, 105.0, 96.0, 99.0)] + [FLAT] * 29
    df1m, df15 = synthetic_barrier_path(bars, patr=PATR)
    res = make_labels(df15, df1m, horizon_bars=2)
    assert _rt3(res) == -1  # close < open ⇒ low (stop) first
    assert res.frame["ambig_1m"][0] is True


# --- horizon boundary -----------------------------------------------------


def test_touch_on_last_in_window_bar_counts(synthetic_barrier_path):
    # horizon_bars=1 ⇒ window is the 15 1m bars 15..29; bar 29 is the last in-window.
    bars = DECISION + [FLAT] * 14 + [(100.0, 105.0, 100.0, 101.0)] + [FLAT] * 15
    df1m, df15 = synthetic_barrier_path(bars, patr=PATR)
    res = make_labels(df15, df1m, horizon_bars=1)
    assert _rt3(res) == 1


def test_touch_one_bar_past_horizon_is_zero(synthetic_barrier_path):
    # Target sits at bar 30 — one bar past the horizon_bars=1 window (15..29).
    bars = DECISION + [FLAT] * 15 + [(100.0, 105.0, 100.0, 101.0)] + [FLAT] * 14
    df1m, df15 = synthetic_barrier_path(bars, patr=PATR)
    res = make_labels(df15, df1m, horizon_bars=1)
    assert _rt3(res) == 0


# --- D-027: entry price is the close of the 15m bar at t -------------------


def test_entry_price_is_15m_close_not_open(synthetic_barrier_path):
    # First 15m bar: open 100 (bar 0), close 110 (bar 14) — close differs from open.
    decision = [(100.0, 110.0, 100.0, 110.0)] + [(110.0, 110.0, 110.0, 110.0)] * 14
    bars = decision + [(110.0, 110.0, 110.0, 110.0)] * 15
    df1m, df15 = synthetic_barrier_path(bars, patr=PATR)
    res = make_labels(df15, df1m, horizon_bars=1)
    assert res.frame["entry_price"][0] == 110.0
    assert res.frame["profit_level"][0] == (1 + 4 * PATR) * 110.0  # anchored on close
    assert res.frame["stop_level"][0] == (1 - 2.5 * PATR) * 110.0


# --- D-029: tail rows sentineled but retained -----------------------------


def test_tail_rows_are_sentineled_and_retained(synthetic_barrier_path):
    bars = DECISION + [FLAT] * 15  # only 2 15m bars; horizon_bars=2 runs off the end
    df1m, df15 = synthetic_barrier_path(bars, patr=PATR)
    res = make_labels(df15, df1m, horizon_bars=2)
    assert res.frame.height == df15.height  # row retained
    assert res.frame["rt3"][0] is None
    assert res.frame["is_complete"][0] is False
    assert res.frame["first_touch_idx_1m"][0] is None


def test_label_result_schema(synthetic_barrier_path):
    bars = DECISION + [FLAT] * 30
    df1m, df15 = synthetic_barrier_path(bars, patr=PATR)
    res = make_labels(df15, df1m, horizon_bars=2)
    assert res.frame.schema == pl.Schema(LABEL_SCHEMA)


# --- D-036: gap-fill discipline probe -------------------------------------


def test_gap_fill_resolves_touch_before_gap(synthetic_barrier_path):
    # (a) honest resolves the barrier before an in-horizon gap ⇒ non-null match.
    bars = DECISION + [(100.0, 105.0, 100.0, 101.0)] + [FLAT] * 29  # target at bar 15
    df1m, df15 = synthetic_barrier_path(bars, patr=PATR, drop_minutes={25})  # gap after touch
    res = make_labels(df15, df1m, horizon_bars=2, gap_fill="observed")
    assert _rt3(res) == 1


def test_gap_before_touch_is_null_but_v1_noncausal_resolves(synthetic_barrier_path):
    # (b) honest reaches the gap before any touch ⇒ null;
    # (c) v1_noncausal fills the gap and resolves ⇒ non-null. They must differ.
    bars = DECISION + [FLAT] * 5 + [FLAT] * 9 + [(100.0, 105.0, 100.0, 101.0)] + [FLAT] * 14
    # bars: decision(0-14), 15-19 flat, 20 dropped(gap), 21-29 flat, 30 target, 31-44 flat
    df1m, df15 = synthetic_barrier_path(bars, patr=PATR, drop_minutes={20})

    honest = make_labels(df15, df1m, horizon_bars=2, gap_fill="observed")
    v1 = make_labels(df15, df1m, horizon_bars=2, gap_fill="v1_noncausal")

    assert _rt3(honest) is None
    assert honest.frame["is_complete"][0] is False
    assert _rt3(v1) == 1
    assert _rt3(honest) != _rt3(v1)


# --- D-038: pATR fill policy probe ----------------------------------------


def test_patr_unrealised_is_null_but_v1_fill_resolves(synthetic_barrier_path):
    # pATR is unrealised (None) at the decision bar.
    bars = DECISION + [(100.0, 105.0, 100.0, 101.0)] + [FLAT] * 29  # target at bar 15
    df1m, df15 = synthetic_barrier_path(bars, patr=[None, PATR, PATR])

    honest = make_labels(df15, df1m, horizon_bars=2, patr_fill="realised_only")
    v1 = make_labels(df15, df1m, horizon_bars=2, patr_fill="v1_ffill_bfill")

    assert _rt3(honest) is None
    assert honest.frame["is_complete"][0] is False
    assert honest.frame["profit_level"][0] is None
    assert _rt3(v1) == 1  # pATR back-filled from a later bar ⇒ barrier realised
    assert _rt3(honest) != _rt3(v1)
