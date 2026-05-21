import pytest
from datetime import datetime, timezone, timedelta
import polars as pl


@pytest.fixture
def synthetic_ohlcv():
    """Generate a tiny synthetic OHLCV polars DataFrame for testing."""
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    times = [now - timedelta(minutes=i) for i in reversed(range(10))]
    opens = [100 + i for i in range(10)]
    highs = [o + 1 for o in opens]
    lows = [o - 1 for o in opens]
    closes = [o + 0.5 for o in opens]
    volume = [10.0 for _ in range(10)]
    df = pl.DataFrame(
        {
            "open_time": times,
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": volume,
            "close_time": [t + timedelta(minutes=1) for t in times],
            "number_of_trades": [1 for _ in times],
            "taker_buy_base_volume": [5.0 for _ in times],
            "taker_buy_quote_volume": [500.0 for _ in times],
        }
    )
    return df
