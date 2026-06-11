"""Target statistics and diagnostics (B.2).

`target_stats` characterizes a `LabelResult` before any model trusts it:
three-class balance, the timeout (no-touch) rate v1 never logged, the per-quarter
class distribution (crypto regimes move the positive rate a lot), and the median
forward distance to first touch — the practical overlap measure that sets
expectations for the effective sample size (B.3) and the embargo (D-004).

The pre-cost breakeven reference is `m_stop / (m_target + m_stop)` = 38.5% for
4 / 2.5 (D-007). Every precision number is judged against it, never against 50%.
"""

import logging
from typing import Any, cast

import numpy as np
import polars as pl

from assareh.labels.targets import LabelResult

logger = logging.getLogger(__name__)

_BAR15_US = 15 * 60_000_000


def breakeven_precost(m_target: float, m_stop: float) -> float:
    """Pre-cost breakeven hit rate for a payoff of `m_target : m_stop` (D-007)."""
    return m_stop / (m_target + m_stop)


def target_stats(
    result: LabelResult | pl.DataFrame,
    df1m: pl.DataFrame | None = None,
) -> dict[str, Any]:
    """Diagnostics over the complete (resolved) rows of a `LabelResult`.

    Pass the `LabelResult` (so the labeler config — multipliers, horizon — is
    available) or a bare frame. Supply the **same** `df1m` that produced the
    labels to also get overlap metrics (median/mean forward distance to first
    touch); `first_touch_idx_1m` indexes into that substrate.
    """
    if isinstance(result, LabelResult):
        frame, config = result.frame, result.attrs
    else:
        frame, config = result, {}

    done = frame.filter(pl.col("is_complete"))
    n = done.height
    if n == 0:
        raise ValueError("no complete rows to summarize")

    def _frac(value: int) -> float:
        return cast(float, (done["rt3"] == value).mean())  # n > 0 guarded above

    stats: dict[str, Any] = {
        "n_total": frame.height,
        "n_complete": n,
        "n_incomplete": frame.height - n,
        "positive_rate": _frac(1),
        "no_touch_rate": _frac(0),
        "negative_rate": _frac(-1),
        "ambig_15m_rate": cast(float, done["ambig_15m"].cast(pl.Float64).mean()),
        "ambig_1m_rate": (
            cast(float, done["ambig_1m"].cast(pl.Float64).mean())
            if done["ambig_1m"].null_count() < n
            else None
        ),
    }

    m_target, m_stop = config.get("m_target"), config.get("m_stop")
    if m_target is not None and m_stop is not None:
        stats["breakeven_precost"] = breakeven_precost(m_target, m_stop)

    stats["per_quarter"] = (
        done.with_columns(
            pl.col("open_time").dt.year().alias("year"),
            pl.col("open_time").dt.quarter().alias("q"),
        )
        .group_by("year", "q")
        .agg(
            n=pl.len(),
            positive_rate=(pl.col("rt3") == 1).mean(),
            no_touch_rate=(pl.col("rt3") == 0).mean(),
            negative_rate=(pl.col("rt3") == -1).mean(),
        )
        .sort("year", "q")
        .with_columns(quarter=pl.format("{}Q{}", "year", "q"))
        .select("quarter", "n", "positive_rate", "no_touch_rate", "negative_rate")
    )

    if df1m is not None:
        stats.update(_overlap_stats(done, df1m, config.get("horizon_bars")))

    logger.info(
        "target_stats: n_complete=%d +1/0/-1 = %.3f/%.3f/%.3f",
        n, stats["positive_rate"], stats["no_touch_rate"], stats["negative_rate"],
    )
    return stats


def _overlap_stats(
    done: pl.DataFrame, df1m: pl.DataFrame, horizon_bars: int | None
) -> dict[str, Any]:
    """Forward distance to first touch, in 15m bars (label overlap proxy)."""
    t1m = df1m.sort("open_time")["open_time"].cast(pl.Int64).to_numpy()
    touched = done.filter(pl.col("rt3") != 0)
    if touched.height == 0:
        return {"median_touch_bars": None, "mean_touch_bars": None}

    idx = touched["first_touch_idx_1m"].to_numpy()
    touch_us = t1m[idx]
    entry_close_us = touched["open_time"].cast(pl.Int64).to_numpy() + _BAR15_US
    # Bars held forward, counting the touch bar itself (≥ 1).
    held = np.floor((touch_us - entry_close_us) / _BAR15_US).astype(int) + 1

    out: dict[str, Any] = {
        "median_touch_bars": float(np.median(held)),
        "mean_touch_bars": float(np.mean(held)),
    }
    if horizon_bars is not None:
        # Timeouts occupy the full horizon; combine for the overall span median.
        n_timeout = done.height - touched.height
        spans = np.concatenate([held, np.full(n_timeout, horizon_bars, dtype=int)])
        out["median_span_bars"] = float(np.median(spans))
    return out
