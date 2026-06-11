"""Triple-barrier target construction on the 15m decision clock (B.1).

`make_labels` rebuilds v1's three-class triple-barrier label (`rt3`) cleanly,
with the one methodological improvement of the phase: barrier-touch order is
resolved on the **1m** substrate (honest arm) instead of v1's 15m-optimistic
assumption (v1-faithful arm). See PHASE_B.md B.1 and:

- D-006  barrier-touch resolution source (1m honest / 15m v1-faithful)
- D-026  both barriers anchored on 15m pATR by default
- D-027  entry price = close of the 15m bar at `t`
- D-028  1m intra-bar tie-break (close>open ⇒ high-first, else low-first)
- D-029  `LabelResult` schema + typed-null tail/unresolvable sentinels
- D-036  gap-fill discipline probe (observed / zoh_causal / v1_noncausal)
- D-038  pATR fill policy probe (realised_only / v1_ffill_bfill)

v1's `target2`/`target3`/`stop2` meta-label path is intentionally NOT reproduced
(discarded v1 experiment — L-006 corrected, D-014, L-017). v1's downstream
`qualified` sample-filter is a Phase D/E concern (D-040 resolved, D-041), not a
labeler one.
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, cast

import numpy as np
import polars as pl

logger = logging.getLogger(__name__)

# Microsecond constants (open_time is Datetime("us", tz=UTC)).
_MIN_US = 60_000_000
_BAR15_US = 15 * _MIN_US
_INF_US = np.iinfo(np.int64).max

# D-029 schema (PHASE_B.md B.1): one row per 15m bar, never reindexed/filtered.
# target3 / stop2_level are intentionally absent (D-014, L-006).
LABEL_SCHEMA: dict[str, type[pl.DataType] | pl.DataType] = {
    "open_time": pl.Datetime("us", time_zone="UTC"),
    "rt3": pl.Int8,
    "first_touch_idx_1m": pl.Int64,
    "entry_price": pl.Float64,
    "profit_level": pl.Float64,
    "stop_level": pl.Float64,
    "ambig_15m": pl.Boolean,
    "ambig_1m": pl.Boolean,
    "is_complete": pl.Boolean,
}


@dataclass(frozen=True)
class LabelResult:
    """The label table plus scalar diagnostics.

    `frame` is the D-029 DataFrame (the primary artifact downstream consumers
    join on `open_time`). `attrs` holds per-arm scalar diagnostics — ambiguity
    rates, no-touch fraction, class balance — read by B.2's `target_stats`.
    """

    frame: pl.DataFrame
    attrs: dict[str, Any]


def _require(df: pl.DataFrame, cols: tuple[str, ...], name: str) -> None:
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise ValueError(f"{name} is missing required columns: {missing}")


def _patr_arrays(
    df15: pl.DataFrame,
    target_patr_col: str,
    stop_patr_col: str,
    patr_fill: Literal["realised_only", "v1_ffill_bfill"],
) -> tuple[np.ndarray, np.ndarray]:
    """Return (target_patr, stop_patr) as float arrays, applying the D-038 probe.

    `realised_only` (honest) leaves NaN where pATR is unrealised at `t`; those
    rows become typed-null labels. `v1_ffill_bfill` reproduces v1's
    `fillna('ffill').fillna('bfill')` chain on a copy, fabricating barrier
    widths from future pATR (L-010).
    """
    cols = [target_patr_col] if target_patr_col == stop_patr_col else [target_patr_col, stop_patr_col]
    sub = df15.select(cols)
    if patr_fill == "v1_ffill_bfill":
        sub = sub.with_columns(pl.col(c).forward_fill().backward_fill() for c in cols)
    elif patr_fill != "realised_only":
        raise ValueError(f"patr_fill must be 'realised_only' or 'v1_ffill_bfill', got {patr_fill!r}")
    tgt = sub[target_patr_col].to_numpy().astype(float)
    stop = sub[stop_patr_col].to_numpy().astype(float)
    return tgt, stop


def _resolution_1m(
    df1m: pl.DataFrame,
    gap_fill: Literal["observed", "zoh_causal", "v1_noncausal"],
) -> tuple[np.ndarray, ...]:
    """Prepare the 1m substrate arrays per the D-036 gap-fill probe.

    `observed` (honest) keeps gaps and lets the walk halt at them. The two
    comparison arms densify the minute grid first: `zoh_causal` repeats the last
    observed bar (causal, fabricates), `v1_noncausal` linearly interpolates
    between bracketing bars (reproduces v1's non-causal LinearInterpolator,
    L-008). Returns (t, open, high, low, close, gap_after) — `gap_after[k]` marks
    that the minute after bar k is missing (always False on a densified grid
    except at the data tail).
    """
    df1m = df1m.sort("open_time")
    if gap_fill in ("zoh_causal", "v1_noncausal"):
        grid = pl.datetime_range(
            cast(datetime, df1m["open_time"].min()),
            cast(datetime, df1m["open_time"].max()),
            interval="1m",
            time_zone="UTC",
            eager=True,
        ).alias("open_time")
        df1m = pl.DataFrame({"open_time": grid}).join(df1m, on="open_time", how="left")
        ohlc = ("open", "high", "low", "close")
        if gap_fill == "zoh_causal":
            df1m = df1m.with_columns(pl.col(c).forward_fill() for c in ohlc)
        else:  # v1_noncausal: linear interpolation reaches into the next real bar
            df1m = df1m.with_columns(pl.col(c).interpolate() for c in ohlc)
    elif gap_fill != "observed":
        raise ValueError(
            f"gap_fill must be 'observed', 'zoh_causal' or 'v1_noncausal', got {gap_fill!r}"
        )

    t = df1m["open_time"].cast(pl.Int64).to_numpy()
    o = df1m["open"].to_numpy().astype(float)
    h = df1m["high"].to_numpy().astype(float)
    low = df1m["low"].to_numpy().astype(float)
    c = df1m["close"].to_numpy().astype(float)
    gap_after = np.ones(len(t), dtype=bool)  # last bar: data ends ⇒ gap
    if len(t) > 1:
        gap_after[:-1] = np.diff(t) != _MIN_US
    return t, o, h, low, c, gap_after


# The first-touch search is sequential per decision (each decision has its own
# barrier levels), so it crosses the numpy boundary rather than staying in a
# polars expression — same pattern as the Wilder recurrence in features/patr.py.
def _walk_1m(
    t: np.ndarray,
    o: np.ndarray,
    h: np.ndarray,
    low: np.ndarray,
    c: np.ndarray,
    gap_after: np.ndarray,
    entry_us: np.ndarray,
    profit: np.ndarray,
    stop: np.ndarray,
    patr_ok: np.ndarray,
    horizon_us: int,
) -> tuple[list[int | None], list[int | None], list[bool | None], list[bool]]:
    """Honest 1m forward walk (D-006). Returns rt3, first_touch_idx_1m, ambig_1m,
    is_complete, one entry per decision."""
    n = len(t)
    rt3: list[int | None] = []
    ftidx: list[int | None] = []
    ambig: list[bool | None] = []
    complete: list[bool] = []

    def emit(label: int | None, idx: int | None, amb: bool | None, comp: bool) -> None:
        rt3.append(label)
        ftidx.append(idx)
        ambig.append(amb)
        complete.append(comp)

    for j in range(len(entry_us)):
        if not patr_ok[j]:  # D-038 honest: unrealised pATR ⇒ typed null
            emit(None, None, None, False)
            continue

        e = int(entry_us[j])
        end = e + horizon_us
        lo = int(np.searchsorted(t, e, side="left"))
        hi = int(np.searchsorted(t, end, side="left"))  # exclusive window end

        # First in-window missing minute (D-036 observed): the walk cannot see
        # past it. A gap at/after the window end does not count.
        gap_time = _INF_US
        if lo >= n or t[lo] != e:
            gap_time = e  # the entry-adjacent minute itself is missing
        else:
            sub = gap_after[lo:hi]
            nz = np.nonzero(sub)[0]
            if len(nz):
                miss = int(t[lo + int(nz[0])]) + _MIN_US
                if miss < end:
                    gap_time = miss

        hw = h[lo:hi]
        lw = low[lo:hi]
        tgt_hits = hw >= profit[j]
        stp_hits = lw <= stop[j]
        it = lo + int(tgt_hits.argmax()) if tgt_hits.any() else None
        is_ = lo + int(stp_hits.argmax()) if stp_hits.any() else None
        tu = t[it] if it is not None else _INF_US
        tl = t[is_] if is_ is not None else _INF_US
        first_touch = min(tu, tl)

        if first_touch < gap_time:
            if tu < tl:
                emit(1, it, False, True)
            elif tl < tu:
                emit(-1, is_, False, True)
            else:  # same 1m bar straddles both barriers — D-028 tie-break
                emit(1 if c[it] > o[it] else -1, it, True, True)
        elif first_touch == _INF_US and gap_time == _INF_US:
            # No touch, fully-observed horizon ⇒ genuine no-touch (timeout).
            emit(0, None, False, True)
        else:
            # Gap reached before any touch, or horizon runs off the data tail.
            emit(None, None, None, False)

    return rt3, ftidx, ambig, complete


def _walk_15m(
    high: np.ndarray,
    low: np.ndarray,
    profit: np.ndarray,
    stop: np.ndarray,
    patr_ok: np.ndarray,
    horizon_bars: int,
) -> tuple[list[int | None], list[bool], list[bool]]:
    """15m-optimistic resolution (v1-faithful, D-006). Also supplies `ambig_15m`
    for the honest arm: the 15m same-bar ambiguity rate bounds how far the two
    arms can diverge. Returns rt3_15, ambig_15m, is_complete."""
    n = len(high)
    rt3: list[int | None] = []
    ambig: list[bool] = []
    complete: list[bool] = []
    big = horizon_bars + 1

    def emit(label: int | None, amb: bool, comp: bool) -> None:
        rt3.append(label)
        ambig.append(amb)
        complete.append(comp)

    for j in range(n):
        if not patr_ok[j] or j + 1 + horizon_bars > n:
            emit(None, False, False)
            continue
        s = j + 1
        hw = high[s : s + horizon_bars]
        lw = low[s : s + horizon_bars]
        tgt_hits = hw >= profit[j]
        stp_hits = lw <= stop[j]
        it = int(tgt_hits.argmax()) if tgt_hits.any() else big
        is_ = int(stp_hits.argmax()) if stp_hits.any() else big
        if it == big and is_ == big:
            emit(0, False, True)
        elif it < is_:
            emit(1, False, True)
        elif is_ < it:
            emit(-1, False, True)
        else:  # both barriers first touched in the same 15m bar — v1 optimistic
            emit(1, True, True)

    return rt3, ambig, complete


def make_labels(
    df15: pl.DataFrame,
    df1m: pl.DataFrame,
    *,
    target_patr_col: str = "patr_15",
    stop_patr_col: str = "patr_15",
    m_target: float = 4.0,
    m_stop: float = 2.5,
    horizon_bars: int = 48,
    resolution: Literal["1m", "15m"] = "1m",
    gap_fill: Literal["observed", "zoh_causal", "v1_noncausal"] = "observed",
    patr_fill: Literal["realised_only", "v1_ffill_bfill"] = "realised_only",
) -> LabelResult:
    """Triple-barrier labels on the 15m decision clock.

    Barriers at decision `t` (D-026 revised, D-027):
        entry_price  = df15['close'][t]
        profit_level = (1 + m_target × df15[target_patr_col][t]) × entry_price
        stop_level   = (1 − m_stop   × df15[stop_patr_col][t])   × entry_price

    `resolution` selects the honest 1m arm vs. the v1-faithful 15m-optimistic arm
    (D-006). `gap_fill` (D-036) and `patr_fill` (D-038) are the data-handling
    leakage probes; their honest defaults are 'observed' and 'realised_only'.
    `horizon_bars` defaults to 48 (~3×4h, D-003); pass 511 to reproduce v1.

    Returns a `LabelResult` whose `frame` follows the D-029 schema (one row per
    15m bar; tail/unresolvable rows carry `rt3 = null`, `is_complete = False`).
    """
    if resolution not in ("1m", "15m"):
        raise ValueError(f"resolution must be '1m' or '15m', got {resolution!r}")
    _require(df15, ("open_time", "high", "low", "close", target_patr_col, stop_patr_col), "df15")
    _require(df1m, ("open_time", "open", "high", "low", "close"), "df1m")

    df15 = df15.sort("open_time")
    open_time = df15["open_time"]
    close15 = df15["close"].to_numpy().astype(float)
    high15 = df15["high"].to_numpy().astype(float)
    low15 = df15["low"].to_numpy().astype(float)
    entry_us = open_time.cast(pl.Int64).to_numpy() + _BAR15_US  # close of the 15m bar at t

    tgt_patr, stop_patr = _patr_arrays(df15, target_patr_col, stop_patr_col, patr_fill)
    patr_ok = np.isfinite(tgt_patr) & np.isfinite(stop_patr)
    profit = (1.0 + m_target * tgt_patr) * close15
    stop = (1.0 - m_stop * stop_patr) * close15

    # The 15m scan always runs: it is the v1-faithful arm and the source of the
    # ambig_15m diagnostic for the honest arm (D-006 added detail).
    rt3_15, ambig_15m, complete_15 = _walk_15m(high15, low15, profit, stop, patr_ok, horizon_bars)

    if resolution == "1m":
        t, o, h, low_, c, gap_after = _resolution_1m(df1m, gap_fill)
        rt3, ftidx, ambig_1m, is_complete = _walk_1m(
            t, o, h, low_, c, gap_after, entry_us, profit, stop, patr_ok, horizon_bars * _BAR15_US
        )
    else:
        rt3, is_complete = rt3_15, complete_15
        ftidx = [None] * df15.height
        ambig_1m = [None] * df15.height

    # Null the barrier levels where pATR was unrealised so they are never read as
    # fabricated widths (the honest D-038 contract).
    frame = pl.DataFrame(
        [
            open_time.alias("open_time"),
            pl.Series("rt3", rt3, dtype=pl.Int8),
            pl.Series("first_touch_idx_1m", ftidx, dtype=pl.Int64),
            pl.Series("entry_price", close15, dtype=pl.Float64),
            pl.Series("profit_level", np.where(patr_ok, profit, np.nan), dtype=pl.Float64),
            pl.Series("stop_level", np.where(patr_ok, stop, np.nan), dtype=pl.Float64),
            pl.Series("ambig_15m", ambig_15m, dtype=pl.Boolean),
            pl.Series("ambig_1m", ambig_1m, dtype=pl.Boolean),
            pl.Series("is_complete", is_complete, dtype=pl.Boolean),
        ]
    ).with_columns(
        pl.col("profit_level").fill_nan(None),
        pl.col("stop_level").fill_nan(None),
    )
    assert frame.schema == pl.Schema(LABEL_SCHEMA), frame.schema

    attrs = _diagnostics(
        frame,
        resolution=resolution,
        gap_fill=gap_fill,
        patr_fill=patr_fill,
        horizon_bars=horizon_bars,
        m_target=m_target,
        m_stop=m_stop,
    )
    logger.info(
        "make_labels: %d/%d complete (resolution=%s gap_fill=%s patr_fill=%s horizon=%d) "
        "rates +1/0/-1 = %.3f/%.3f/%.3f",
        attrs["n_complete"], attrs["n_total"], resolution, gap_fill, patr_fill, horizon_bars,
        attrs["positive_rate"], attrs["no_touch_rate"], attrs["negative_rate"],
    )
    return LabelResult(frame=frame, attrs=attrs)


def _diagnostics(frame: pl.DataFrame, **config: Any) -> dict[str, Any]:
    """Per-arm scalar diagnostics over the complete rows (read by B.2)."""
    done = frame.filter(pl.col("is_complete"))
    n_complete = done.height

    def _rate(expr: pl.Expr) -> float | None:
        return float(done.select(expr.mean()).item()) if n_complete else None

    return {
        **config,
        "n_total": frame.height,
        "n_complete": n_complete,
        "n_incomplete": frame.height - n_complete,
        "positive_rate": _rate((pl.col("rt3") == 1).cast(pl.Float64)),
        "negative_rate": _rate((pl.col("rt3") == -1).cast(pl.Float64)),
        "no_touch_rate": _rate((pl.col("rt3") == 0).cast(pl.Float64)),
        "ambig_15m_rate": _rate(pl.col("ambig_15m").cast(pl.Float64)),
        "ambig_1m_rate": (
            _rate(pl.col("ambig_1m").cast(pl.Float64)) if config["resolution"] == "1m" else None
        ),
    }
