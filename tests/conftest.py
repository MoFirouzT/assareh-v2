import re
from datetime import datetime, timedelta, timezone

import polars as pl
import pytest

from assareh.data.schemas import OHLCV_SCHEMA


def _parse_interval(interval: str) -> timedelta:
    m = re.match(r"^(\d+)([mhd])$", interval)
    if not m:
        raise ValueError(f"Bad interval: {interval!r}")
    val, unit = int(m.group(1)), m.group(2)
    if unit == "m":
        return timedelta(minutes=val)
    if unit == "h":
        return timedelta(hours=val)
    return timedelta(days=val)


@pytest.fixture
def make_ohlcv():
    """Factory: build a schema-valid OHLCV frame from explicit OHLC arrays.

    For numeric indicator tests (e.g. pATR) that need controlled intra-bar paths,
    rather than the generic issue-injecting `synthetic_ohlcv` fixture. Times are
    generated from `start` stepping `interval`; `volume` defaults to a constant.
    """

    def _factory(
        opens: list[float],
        highs: list[float],
        lows: list[float],
        closes: list[float],
        *,
        interval: str = "1m",
        start: datetime = datetime(2022, 1, 1, tzinfo=timezone.utc),
        volumes: list[float] | None = None,
    ) -> pl.DataFrame:
        n = len(opens)
        if not (len(highs) == len(lows) == len(closes) == n):
            raise ValueError("OHLC arrays must be the same length")
        td = _parse_interval(interval)
        times = [start + td * i for i in range(n)]
        vols = volumes if volumes is not None else [100.0] * n
        return pl.DataFrame(
            {
                "open_time": times,
                "open": [float(x) for x in opens],
                "high": [float(x) for x in highs],
                "low": [float(x) for x in lows],
                "close": [float(x) for x in closes],
                "volume": [float(x) for x in vols],
                "close_time": [t + td for t in times],
                "number_of_trades": [500] * n,
                "taker_buy_base_volume": [50.0] * n,
                "taker_buy_quote_volume": [50.0 * 30_000.0] * n,
            },
            schema=OHLCV_SCHEMA,
        )

    return _factory


@pytest.fixture
def synthetic_barrier_path(make_ohlcv):
    """Factory: matched 1m / 15m frames + a `patr_15` column from a 1m price path.

    For B.1 triple-barrier tests (PHASE_B B.1 Tests). Pass an explicit list of
    1m `(open, high, low, close)` bars; the 15m frame is aggregated from them
    (open=first, high=max, low=min, close=last over each 15m bucket). `patr` is
    the percent-ATR attached to every 15m bar — a scalar, or a list aligned to
    the 15m rows (use `None` to make a decision bar's pATR unrealised for the
    D-038 probe). To drill a gap into the 1m substrate, pass `drop_minutes` as a
    set of 0-based 1m indices to delete after construction.
    """

    def _build(
        minute_bars: list[tuple[float, float, float, float]],
        *,
        patr: float | list[float | None] = 0.01,
        start: datetime = datetime(2022, 1, 1, tzinfo=timezone.utc),
        drop_minutes: set[int] | None = None,
    ) -> tuple[pl.DataFrame, pl.DataFrame]:
        opens = [b[0] for b in minute_bars]
        highs = [b[1] for b in minute_bars]
        lows = [b[2] for b in minute_bars]
        closes = [b[3] for b in minute_bars]
        df1m = make_ohlcv(opens, highs, lows, closes, interval="1m", start=start)

        df15 = (
            df1m.sort("open_time")
            .group_by(pl.col("open_time").dt.truncate("15m").alias("open_time"), maintain_order=True)
            .agg(
                open=pl.col("open").first(),
                high=pl.col("high").max(),
                low=pl.col("low").min(),
                close=pl.col("close").last(),
            )
            .sort("open_time")
        )
        n15 = df15.height
        pcol = [patr] * n15 if not isinstance(patr, list) else patr
        if len(pcol) != n15:
            raise ValueError(f"patr list length {len(pcol)} != number of 15m bars {n15}")
        df15 = df15.with_columns(pl.Series("patr_15", pcol, dtype=pl.Float64))

        if drop_minutes:
            keep = [i for i in range(df1m.height) if i not in drop_minutes]
            df1m = df1m[keep]

        return df1m, df15

    return _build


@pytest.fixture
def synthetic_ohlcv():
    """Fixture factory: call with (rows, interval, issues) to get a synthetic OHLCV DataFrame.

    Supported issues: duplicate, gap, ohlc_violation, negative_volume,
                      nan_in_close, nan_in_volume, price_out_of_bounds, non_monotonic.
    """

    def _factory(
        rows: int = 20,
        interval: str = "1m",
        issues: set[str] | None = None,
    ) -> pl.DataFrame:
        if issues is None:
            issues = set()

        td = _parse_interval(interval)
        base = datetime(2022, 1, 1, tzinfo=timezone.utc)

        times: list = [base + td * i for i in range(rows)]
        base_price = 30_000.0
        opens:  list = [base_price + i * 10.0 for i in range(rows)]
        highs:  list = [o + 50.0 for o in opens]
        lows:   list = [o - 50.0 for o in opens]
        closes: list = [o + 25.0 for o in opens]
        volumes: list = [100.0 for _ in range(rows)]
        close_times: list = [t + td for t in times]
        n_trades: list = [500 for _ in range(rows)]
        tbv:  list = [50.0 for _ in range(rows)]
        tbqv: list = [50.0 * base_price for _ in range(rows)]

        if "duplicate" in issues:
            # append an exact copy of row 0 — creates a duplicate open_time
            for lst, src in [
                (times, times[0]), (opens, opens[0]), (highs, highs[0]),
                (lows, lows[0]), (closes, closes[0]), (volumes, volumes[0]),
                (close_times, close_times[0]), (n_trades, n_trades[0]),
                (tbv, tbv[0]), (tbqv, tbqv[0]),
            ]:
                lst.append(src)

        if "non_monotonic" in issues:
            # swap rows 1 and 2 — creates a backward timestamp jump
            times[1], times[2] = times[2], times[1]

        if "gap" in issues:
            # remove the middle row — creates a gap of 2× the interval
            mid = rows // 2
            for lst in [times, opens, highs, lows, closes, volumes,
                        close_times, n_trades, tbv, tbqv]:
                lst.pop(mid)

        if "ohlc_violation" in issues:
            highs[0] = opens[0] - 100.0  # high below open → violation

        if "negative_volume" in issues:
            volumes[0] = -1.0

        if "nan_in_close" in issues:
            closes[0] = None  # null in Float64 column

        if "nan_in_volume" in issues:
            volumes[0] = None

        if "price_out_of_bounds" in issues:
            closes[0] = 50.0  # below the $100 lower bound

        if "off_grid" in issues:
            # shift one bar by 30 seconds — no longer on a 1m boundary
            times[rows // 2] = times[rows // 2] + timedelta(seconds=30)

        return pl.DataFrame(
            {
                "open_time": times,
                "open": opens,
                "high": highs,
                "low": lows,
                "close": closes,
                "volume": volumes,
                "close_time": close_times,
                "number_of_trades": n_trades,
                "taker_buy_base_volume": tbv,
                "taker_buy_quote_volume": tbqv,
            },
            schema=OHLCV_SCHEMA,
        )

    return _factory
