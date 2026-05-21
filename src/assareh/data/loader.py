from typing import Literal
import polars as pl


def load_ohlcv(
    timeframe: Literal["1m", "15m", "1h", "4h"],
    settings,
) -> pl.DataFrame:
    """Load raw OHLCV from Parquet. Asserts schema matches OHLCV_SCHEMA.

    Populated in Phase A.4. For now this is a placeholder that will raise
    if called to make the missing implementation explicit.
    """
    raise NotImplementedError("load_ohlcv is implemented in Phase A.4")
