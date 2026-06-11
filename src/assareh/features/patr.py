"""Multi-timeframe percent-ATR (pATR) attached to the 15m decision clock.

The pATR *formula* is v1's, locked by D-012:
- directional true range via the ``up_first`` flag derived from 1m sub-candles,
- Wilder smoothing (window 10), seeded by the SMA of the first ``window`` pTR
  values, with the first ``window - 1`` rows left null.

The higher-timeframe *join lag* is the one place we improve on v1 (D-012):
v1 lags ``patr_60`` / ``patr_240`` by ``k - 1`` 15m steps and, because v1 labels
candles by their open time, that releases each higher-tf value one 15m bar
*before* the bar closes — a 15-minute look-ahead leak. The honest arm lags by
``k`` (one fully-closed higher-tf bar); the v1-faithful arm reproduces ``k - 1``
plus v1's ffill/bfill. See GLOSSARY (pATR / pTR / Wilder / up_first / higher-tf
join lag) and D-012.
"""

import logging
from typing import Literal

import numpy as np
import polars as pl

logger = logging.getLogger(__name__)

_OHLC = ("open", "high", "low", "close")


def _tf_bars_from_1m(df1m: pl.DataFrame, tf: int) -> pl.DataFrame:
    """Aggregate 1m bars into ``tf``-minute bars, open-labeled, with ``up_first``.

    ``up_first`` reproduces v1's ``UpFirstDetector``: per tf bar, True iff the
    high is reached before the low across its 1m sub-candles; on a tie (both
    extremes in the same 1m bar) iff that bar's ``close <= open``.
    """
    high_max = pl.col("high").max()
    low_min = pl.col("low").min()
    return (
        df1m.lazy()
        .with_columns(pl.col("open_time").dt.truncate(f"{tf}m").alias("open_time_tf"))
        .group_by("open_time_tf", maintain_order=True)
        .agg(
            open=pl.col("open").first(),
            high=high_max,
            low=low_min,
            close=pl.col("close").last(),
            # arg-of-extreme via earliest 1m bar achieving the group extreme
            t_max=pl.col("open_time").filter(pl.col("high") == high_max).first(),
            t_min=pl.col("open_time").filter(pl.col("low") == low_min).first(),
            close_at_max=pl.col("close").filter(pl.col("high") == high_max).first(),
            open_at_max=pl.col("open").filter(pl.col("high") == high_max).first(),
        )
        .with_columns(
            up_first=pl.when(pl.col("t_max") == pl.col("t_min"))
            .then(pl.col("close_at_max") <= pl.col("open_at_max"))
            .otherwise(pl.col("t_max") < pl.col("t_min"))
        )
        .sort("open_time_tf")
        .rename({"open_time_tf": "open_time"})
        .select("open_time", *_OHLC, "up_first")
        .collect()
    )


def _wilder_patr(bars: pl.DataFrame, window: int) -> pl.Series:
    """Percent ATR over ``bars`` (sorted by time): pTR then Wilder smoothing."""
    prev_close = pl.col("close").shift(1)
    denom = pl.when(pl.col("up_first")).then(pl.col("high")).otherwise(pl.col("low"))
    tr1 = (pl.col("high") - pl.col("low")) / denom
    tr2 = (pl.col("high") - prev_close).abs() / prev_close
    tr3 = (pl.col("low") - prev_close).abs() / prev_close
    # max_horizontal skips nulls, so the first bar (no prev_close) falls back to tr1.
    ptr = bars.select(pl.max_horizontal(tr1, tr2, tr3).alias("ptr"))["ptr"]

    # Cross to numpy: the Wilder recurrence is sequential (not a polars expression).
    ptr_np = ptr.to_numpy()
    n = window
    patr = np.full(len(ptr_np), np.nan, dtype=float)
    if len(ptr_np) >= n:
        patr[n - 1] = ptr_np[:n].mean()
        for i in range(n, len(ptr_np)):
            patr[i] = (patr[i - 1] * (n - 1) + ptr_np[i]) / n
    # Warm-up rows are undefined, not a computed NaN: surface them as null so the
    # whole series uses one missing-marker (null), consistent with the higher-tf
    # pre-roll and the downstream pATR-fill policy (D-037 / D-038).
    return pl.Series("patr", patr).fill_nan(None)


def attach_patr(
    df15: pl.DataFrame,
    df1m: pl.DataFrame,
    *,
    window: int = 10,
    timeframes_minutes: tuple[int, ...] = (15, 60, 240),
    higher_tf_lag: Literal["causal", "v1_faithful"] = "causal",
) -> pl.DataFrame:
    """Return ``df15`` with a ``patr_<tf>`` column attached per requested timeframe.

    ``patr_15`` uses ``df15``'s canonical OHLC; higher timeframes are aggregated
    from ``df1m``. ``up_first`` for every timeframe is derived from ``df1m``.
    Higher timeframes (tf > 15) are lagged onto the 15m clock per
    ``higher_tf_lag`` (see module docstring / D-012):

    - ``"causal"`` (default, honest): ``shift(k)`` with ``k = tf // 15`` then
      forward-fill; the value first appears at the bar's close, leading rows null.
    - ``"v1_faithful"``: ``shift(k - 1)`` then ffill + bfill — v1's 15-minute leak.
    """
    if higher_tf_lag not in ("causal", "v1_faithful"):
        raise ValueError(f"higher_tf_lag must be 'causal' or 'v1_faithful', got {higher_tf_lag!r}")

    df15 = df15.sort("open_time")
    df1m = df1m.sort("open_time")
    out = df15

    for tf in timeframes_minutes:
        if tf < 15 or tf % 15 != 0:
            raise ValueError(f"timeframe {tf} must be a positive multiple of 15")

        bars = _tf_bars_from_1m(df1m, tf)
        if tf == 15:
            # Use the canonical 15m OHLC (decision clock); keep 1m-derived up_first.
            bars = (
                df15.select("open_time", *_OHLC)
                .join(bars.select("open_time", "up_first"), on="open_time", how="left")
                .sort("open_time")
            )

        bars = bars.with_columns(_wilder_patr(bars, window).alias("patr"))
        col = bars.select("open_time", pl.col("patr").alias(f"patr_{tf}"))
        out = out.join(col, on="open_time", how="left").sort("open_time")

        if tf != 15:
            k = tf // 15
            lag = k if higher_tf_lag == "causal" else k - 1
            expr = pl.col(f"patr_{tf}").shift(lag).forward_fill()
            if higher_tf_lag == "v1_faithful":
                expr = expr.backward_fill()
            out = out.with_columns(expr.alias(f"patr_{tf}"))

    logger.info(
        "Attached %s to 15m frame (window=%d, higher_tf_lag=%s)",
        [f"patr_{tf}" for tf in timeframes_minutes],
        window,
        higher_tf_lag,
    )
    return out
