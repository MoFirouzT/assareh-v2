import logging
import re
from datetime import datetime, timedelta
from typing import cast

import polars as pl

from assareh.data.schemas import CrossTimeframeReport, GapRecord, IntegrityReport

logger = logging.getLogger(__name__)

_OHLC_COLS = ("open", "high", "low", "close")
_SOFT_COLS = ("volume", "close_time", "number_of_trades", "taker_buy_base_volume", "taker_buy_quote_volume")
_FLOAT_COLS = {"volume", "taker_buy_base_volume", "taker_buy_quote_volume"}


def _parse_interval(timeframe: str) -> timedelta:
    m = re.match(r"^(\d+)([mhd])$", timeframe)
    if not m:
        raise ValueError(f"Cannot parse timeframe: {timeframe!r}")
    val, unit = int(m.group(1)), m.group(2)
    if unit == "m":
        return timedelta(minutes=val)
    if unit == "h":
        return timedelta(hours=val)
    return timedelta(days=val)


def check_integrity(df: pl.DataFrame, timeframe: str) -> IntegrityReport:
    hard_failures: list[str] = []
    n_rows = df.height

    # UTC timezone (backstop — loader should have caught this)
    ot_dtype = df.schema.get("open_time")
    if ot_dtype != pl.Datetime("us", "UTC"):
        hard_failures.append(
            f"open_time dtype is {ot_dtype!r}, expected Datetime('us', 'UTC')"
        )

    date_range_start = cast(datetime, df["open_time"].min())
    date_range_end = cast(datetime, df["open_time"].max())

    # Duplicates
    n_duplicates = n_rows - df["open_time"].n_unique()
    if n_duplicates > 0:
        hard_failures.append(f"Found {n_duplicates} duplicate open_time value(s)")

    # Non-monotonic timestamps
    if n_rows > 1:
        non_mono = (
            df.lazy()
            .select(pl.col("open_time").diff().dt.total_microseconds().alias("d"))
            .filter(pl.col("d").is_not_null() & (pl.col("d") <= 0))
            .collect()
            .height
        )
        if non_mono > 0:
            hard_failures.append(f"Found {non_mono} non-monotonic timestamp(s)")

    # NaN / null in OHLC
    for col in _OHLC_COLS:
        n = df[col].null_count() + int(df[col].is_nan().sum())
        if n > 0:
            hard_failures.append(f"NaN/null in '{col}': {n} row(s)")

    # OHLC arithmetic violations
    ohlc_violation_count = df.filter(
        (pl.col("high") < pl.max_horizontal("open", "close"))
        | (pl.col("low") > pl.min_horizontal("open", "close"))
    ).height
    if ohlc_violation_count > 0:
        hard_failures.append(f"OHLC arithmetic violation in {ohlc_violation_count} row(s)")

    # Price sanity bounds
    close_valid = df["close"].fill_nan(None).drop_nulls()
    _cmin = close_valid.min()
    _cmax = close_valid.max()
    price_min = float(_cmin) if _cmin is not None else float("nan")  # type: ignore[arg-type]
    price_max = float(_cmax) if _cmax is not None else float("nan")  # type: ignore[arg-type]
    out_of_bounds = df.filter(
        (pl.col("close") < 100) | (pl.col("close") > 1_000_000)
    ).height
    if out_of_bounds > 0:
        hard_failures.append(
            f"close price out of bounds [100, 1_000_000] in {out_of_bounds} row(s)"
        )

    # Negative volume
    neg_vol = df.filter(pl.col("volume") < 0).height
    if neg_vol > 0:
        hard_failures.append(f"Negative volume in {neg_vol} row(s)")

    # Gaps (soft) — vectorised via Polars, safe on multi-million row DataFrames
    interval_td = _parse_interval(timeframe)
    interval_us = int(interval_td.total_seconds() * 1_000_000)
    gaps: list[GapRecord] = []
    if n_rows > 1:
        gap_df = (
            df.lazy()
            .select("open_time")
            .with_columns(pl.col("open_time").shift(1).alias("prev_time"))
            .drop_nulls()
            .with_columns(
                (pl.col("open_time") - pl.col("prev_time"))
                .dt.total_microseconds()
                .alias("diff_us")
            )
            .filter(pl.col("diff_us") > interval_us)
            .collect()
        )
        for row in gap_df.iter_rows(named=True):
            gaps.append(GapRecord(
                start=row["prev_time"],
                end=row["open_time"],
                n_missing=round(row["diff_us"] / interval_us) - 1,
            ))

    # Zero-volume bars (soft)
    zero_volume_count = df.filter(pl.col("volume") == 0).height

    # OHLC-equal bars (soft)
    ohlc_equal_count = df.filter(
        (pl.col("open") == pl.col("high"))
        & (pl.col("high") == pl.col("low"))
        & (pl.col("low") == pl.col("close"))
    ).height

    # NaN counts for non-OHLC columns (soft)
    nan_counts: dict[str, int] = {}
    for col in _SOFT_COLS:
        if col not in df.columns:
            continue
        n = df[col].null_count()
        if col in _FLOAT_COLS:
            n += int(df[col].is_nan().sum())
        nan_counts[col] = n

    return IntegrityReport(
        timeframe=timeframe,
        n_rows=n_rows,
        date_range_start=date_range_start,
        date_range_end=date_range_end,
        n_duplicates=n_duplicates,
        gaps=gaps,
        zero_volume_count=zero_volume_count,
        ohlc_equal_count=ohlc_equal_count,
        price_min=price_min,
        price_max=price_max,
        ohlc_violation_count=ohlc_violation_count,
        nan_counts=nan_counts,
        passed=len(hard_failures) == 0,
        hard_failures=hard_failures,
    )


def check_cross_timeframe_alignment(
    dfs: dict[str, pl.DataFrame],
) -> CrossTimeframeReport:
    """Check that all timeframes share a consistent grid against the 1m reference.

    Hard failure: any coarser-tf open_time not present on the 1m grid.
    Soft: spacing deviations per timeframe, coverage notes.
    """
    reference_tf = "1m"
    hard_failures: list[str] = []
    misaligned_opens: dict[str, int] = {}
    spacing_violations: dict[str, int] = {}
    coverage_mismatch: dict[str, str] = {}

    if reference_tf not in dfs:
        hard_failures.append(f"Reference timeframe '{reference_tf}' not present in dfs")
        return CrossTimeframeReport(
            reference_timeframe=reference_tf,
            misaligned_opens=misaligned_opens,
            spacing_violations=spacing_violations,
            coverage_mismatch=coverage_mismatch,
            passed=False,
            hard_failures=hard_failures,
        )

    ref_df = dfs[reference_tf]
    ref_start = cast(datetime, ref_df["open_time"].min())
    ref_end = cast(datetime, ref_df["open_time"].max())

    # Spacing violations for every timeframe (same logic as gaps, cross-checked direction)
    for tf, df in dfs.items():
        nominal_us = int(_parse_interval(tf).total_seconds() * 1_000_000)
        n_viol = (
            df.lazy()
            .select(pl.col("open_time").diff().dt.total_microseconds().alias("d"))
            .drop_nulls()
            .filter(pl.col("d") != nominal_us)
            .collect()
            .height
        )
        spacing_violations[tf] = n_viol

    # Grid containment and coverage for coarser timeframes.
    # "On the 1m grid" is a mathematical property: the timestamp must be an
    # exact multiple of 1 minute from the UTC epoch (seconds == 0 and
    # microseconds == 0 when expressed as a Unix timestamp mod 60s).
    # Using a modulo check rather than an anti-join against the 1m series
    # separates genuine off-grid timestamps from 1m coverage gaps, which
    # are two distinct issues.
    one_minute_us = int(_parse_interval(reference_tf).total_seconds() * 1_000_000)
    for tf, df in dfs.items():
        if tf == reference_tf:
            continue

        # Hard check: every coarser open_time must be at a whole-minute boundary
        n_misaligned = (
            df.lazy()
            .select((pl.col("open_time").cast(pl.Int64) % one_minute_us).alias("mod"))
            .filter(pl.col("mod") != 0)
            .collect()
            .height
        )
        misaligned_opens[tf] = n_misaligned
        if n_misaligned > 0:
            hard_failures.append(
                f"{tf}: {n_misaligned} open_time(s) not on the {reference_tf} grid"
            )

        # Coverage note: describe the overlap with the reference
        tf_start = cast(datetime, df["open_time"].min())
        tf_end = cast(datetime, df["open_time"].max())
        overlap_start = max(ref_start, tf_start)
        overlap_end = min(ref_end, tf_end)
        if overlap_start > overlap_end:
            coverage_mismatch[tf] = (
                f"no overlap with {reference_tf} "
                f"[{ref_start.date()}, {ref_end.date()}]"
            )
        else:
            coverage_mismatch[tf] = f"overlap [{overlap_start.date()}, {overlap_end.date()}]"

    logger.info(
        "Cross-timeframe alignment: hard_failures=%d, misaligned_opens=%s",
        len(hard_failures),
        misaligned_opens,
    )
    return CrossTimeframeReport(
        reference_timeframe=reference_tf,
        misaligned_opens=misaligned_opens,
        spacing_violations=spacing_violations,
        coverage_mismatch=coverage_mismatch,
        passed=len(hard_failures) == 0,
        hard_failures=hard_failures,
    )
