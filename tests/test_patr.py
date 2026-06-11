"""Tests for multi-timeframe pATR (B.0). See PHASE_B.B.0 and D-012."""

from datetime import datetime, timedelta, timezone

import numpy as np
import polars as pl
import pytest

from assareh.features.patr import _tf_bars_from_1m, _wilder_patr, attach_patr

UTC = timezone.utc


def _ref_patr(high, low, close, up_first, n):
    """Independent reference: v1's pTR + Wilder recurrence (seed = SMA of first n)."""
    H = np.asarray(high, float)
    L = np.asarray(low, float)
    C = np.asarray(close, float)
    U = np.asarray(up_first, bool)
    pc = np.empty_like(C)
    pc[0] = np.nan
    pc[1:] = C[:-1]
    denom = np.where(U, H, L)
    tr1 = (H - L) / denom
    with np.errstate(invalid="ignore"):
        tr2 = np.abs(H - pc) / pc
        tr3 = np.abs(L - pc) / pc
    ptr = np.nanmax(np.vstack([tr1, tr2, tr3]), axis=0)  # row 0 → tr1 (pc is nan)
    patr = np.full(len(ptr), np.nan)
    if len(ptr) >= n:
        patr[n - 1] = ptr[:n].mean()
        for i in range(n, len(ptr)):
            patr[i] = (patr[i - 1] * (n - 1) + ptr[i]) / n
    return patr


def _bars(opens, highs, lows, closes, up_first):
    return pl.DataFrame(
        {
            "open": [float(x) for x in opens],
            "high": [float(x) for x in highs],
            "low": [float(x) for x in lows],
            "close": [float(x) for x in closes],
            "up_first": list(up_first),
        }
    )


# --- Wilder smoothing / pTR formula ---------------------------------------


def test_wilder_constant_ptr_is_analytic():
    """Identical bars → constant pTR → flat pATR after the warm-up, NaN before."""
    n_rows, window = 15, 10
    bars = _bars(
        [100.0] * n_rows, [110.0] * n_rows, [90.0] * n_rows, [100.0] * n_rows,
        [True] * n_rows,
    )
    patr = _wilder_patr(bars, window).to_numpy()
    expected = (110.0 - 90.0) / 110.0  # tr1 dominates tr2 (0.10) and tr3 (0.10)

    assert np.all(np.isnan(patr[: window - 1]))
    assert np.allclose(patr[window - 1 :], expected)


def test_wilder_matches_reference_including_gap_terms():
    """A between-bar jump makes tr2/tr3 the max; full series matches the reference."""
    # A gap-up bar (index 6): low jumps far above the previous close → tr3/tr2 dominate.
    opens = [100, 101, 102, 101, 103, 104, 130, 131, 130, 129, 131, 132]
    highs = [102, 103, 104, 103, 105, 106, 133, 134, 132, 131, 133, 134]
    lows = [99, 100, 101, 100, 102, 103, 129, 130, 128, 127, 130, 131]
    closes = [101, 102, 101, 103, 104, 105, 131, 130, 129, 131, 132, 133]
    up_first = [True, False, True, False, True, False, True, False, True, False, True, False]
    window = 4

    bars = _bars(opens, highs, lows, closes, up_first)
    got = _wilder_patr(bars, window).to_numpy()
    ref = _ref_patr(highs, lows, closes, up_first, window)

    assert np.array_equal(np.isnan(got), np.isnan(ref))
    mask = ~np.isnan(ref)
    assert np.allclose(got[mask], ref[mask])


# --- up_first (v1 UpFirstDetector semantics) ------------------------------


def _one_15m_of_1m(highs, lows, *, opens=None, closes=None):
    """Build 15 one-minute bars inside a single 15m bucket starting at 00:00."""
    start = datetime(2022, 1, 1, tzinfo=UTC)
    n = len(highs)
    o = opens if opens is not None else [100.0] * n
    c = closes if closes is not None else [100.0] * n
    return pl.DataFrame(
        {
            "open_time": [start + timedelta(minutes=i) for i in range(n)],
            "open": [float(x) for x in o],
            "high": [float(x) for x in highs],
            "low": [float(x) for x in lows],
            "close": [float(x) for x in c],
        }
    )


def _up_first_of(df1m):
    return _tf_bars_from_1m(df1m, 15)["up_first"].item()


def test_up_first_high_before_low():
    highs = [105] * 15
    lows = [95] * 15
    highs[2] = 200  # max high early
    lows[10] = 10  # min low late
    assert _up_first_of(_one_15m_of_1m(highs, lows)) is True


def test_up_first_low_before_high():
    highs = [105] * 15
    lows = [95] * 15
    lows[2] = 10  # min low early
    highs[10] = 200  # max high late
    assert _up_first_of(_one_15m_of_1m(highs, lows)) is False


def test_up_first_tie_resolves_on_close_le_open():
    # One 1m bar holds both the global max-high and global min-low (a wide bar).
    highs = [150] * 15
    lows = [50] * 15
    opens = [100.0] * 15
    closes = [100.0] * 15
    highs[5] = 200
    lows[5] = 10
    opens[5] = 100.0

    closes[5] = 90.0  # close <= open  → up_first True
    assert _up_first_of(_one_15m_of_1m(highs, lows, opens=opens, closes=closes)) is True

    closes[5] = 110.0  # close > open  → up_first False
    assert _up_first_of(_one_15m_of_1m(highs, lows, opens=opens, closes=closes)) is False


# --- higher-tf lag: causal vs v1-faithful ---------------------------------


def _walk_1m(n_minutes, seed=0):
    """Deterministic 1m OHLCV walk and its truncated 15m frame."""
    rng = np.random.default_rng(seed)
    start = datetime(2022, 1, 1, tzinfo=UTC)
    steps = rng.normal(0, 2.0, n_minutes).cumsum()
    close = 100.0 + steps
    open_ = np.empty(n_minutes)
    open_[0] = 100.0
    open_[1:] = close[:-1]
    span = np.abs(rng.normal(0, 1.0, n_minutes)) + 0.5
    high = np.maximum(open_, close) + span
    low = np.minimum(open_, close) - span
    df1m = pl.DataFrame(
        {
            "open_time": [start + timedelta(minutes=i) for i in range(n_minutes)],
            "open": open_, "high": high, "low": low, "close": close,
            "volume": [100.0] * n_minutes,
            "close_time": [start + timedelta(minutes=i + 1) for i in range(n_minutes)],
            "number_of_trades": [500] * n_minutes,
            "taker_buy_base_volume": [50.0] * n_minutes,
            "taker_buy_quote_volume": [1e6] * n_minutes,
        }
    )
    df15 = (
        df1m.sort("open_time")
        .group_by(pl.col("open_time").dt.truncate("15m").alias("open_time"), maintain_order=True)
        .agg(
            open=pl.col("open").first(), high=pl.col("high").max(),
            low=pl.col("low").min(), close=pl.col("close").last(),
        )
        .sort("open_time")
    )
    return df1m, df15


def test_default_columns_present():
    df1m, df15 = _walk_1m(240 * 12)  # 12 four-hour bars of 1m data
    out = attach_patr(df15, df1m)
    assert {"patr_15", "patr_60", "patr_240"}.issubset(out.columns)
    assert out.height == df15.height


def test_causal_vs_faithful_lag_one_15m_step():
    # window=3 so 1h pATR turns non-null quickly; 20h of data → 20 one-hour bars.
    df1m, df15 = _walk_1m(60 * 20)
    window = 3
    causal = attach_patr(df15, df1m, timeframes_minutes=(15, 60), window=window, higher_tf_lag="causal")
    faithful = attach_patr(df15, df1m, timeframes_minutes=(15, 60), window=window, higher_tf_lag="v1_faithful")

    # Ground-truth 1h pATR keyed by the 1h bar's open time.
    bars60 = _tf_bars_from_1m(df1m.sort("open_time"), 60)
    bars60 = bars60.with_columns(_wilder_patr(bars60, window).alias("patr"))
    row_of = {t: i for i, t in enumerate(df15["open_time"].to_list())}

    # Pick an interior 1h bar with a non-null pATR whose close+1 stays in range.
    picked = None
    for t, p in zip(bars60["open_time"].to_list(), bars60["patr"].to_list()):
        r = row_of.get(t)
        if p is not None and np.isfinite(p) and r is not None and r + 5 < df15.height:
            picked = (r, p)
            break
    assert picked is not None
    r, p = picked
    k = 4  # 60 // 15

    c = causal["patr_60"].to_list()
    f = faithful["patr_60"].to_list()
    # Causal releases the bar's pATR exactly at its close (open row r + k).
    assert c[r + k] == pytest.approx(p)
    # v1-faithful releases it one 15m bar earlier (open row r + k - 1) — the leak.
    assert f[r + k - 1] == pytest.approx(p)
    # ... and causal has NOT yet released it one step before its close.
    assert c[r + k - 1] != pytest.approx(p)


def test_causal_leaves_leading_null_faithful_backfills():
    df1m, df15 = _walk_1m(60 * 20)
    causal = attach_patr(df15, df1m, timeframes_minutes=(15, 60), window=3, higher_tf_lag="causal")
    faithful = attach_patr(df15, df1m, timeframes_minutes=(15, 60), window=3, higher_tf_lag="v1_faithful")
    # Before the first 1h bar closes, the honest arm has no value; v1 bfills one in.
    assert causal["patr_60"][0] is None
    assert faithful["patr_60"][0] is not None
