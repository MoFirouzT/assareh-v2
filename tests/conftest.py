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
