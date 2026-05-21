import logging
from typing import Literal

import polars as pl

from assareh.config import Settings
from assareh.data.schemas import OHLCV_SCHEMA

logger = logging.getLogger(__name__)


def load_ohlcv(
    timeframe: Literal["1m", "15m", "1h", "4h"],
    settings: Settings,
) -> pl.DataFrame:
    """Load raw OHLCV from Parquet. Casts to OHLCV_SCHEMA; raises on missing columns."""
    path = settings.raw_dir / f"{settings.symbol.lower()}_{timeframe}.parquet"
    if not path.exists():
        raise FileNotFoundError(f"No Parquet file for timeframe '{timeframe}': {path}")

    df = pl.read_parquet(path)

    missing = [col for col in OHLCV_SCHEMA if col not in df.columns]
    if missing:
        raise ValueError(f"Parquet for '{timeframe}' missing required columns: {missing}")

    # Cast to canonical schema — handles ms vs us timestamp precision differences
    # from pandas round-trip via the downloader.
    try:
        df = df.select([pl.col(col).cast(dtype) for col, dtype in OHLCV_SCHEMA.items()])
    except Exception as e:
        raise ValueError(f"Schema cast failed for '{timeframe}': {e}") from e

    logger.info("Loaded %d rows for %s from %s", df.height, timeframe, path)
    return df
