"""Canonical OHLCV schema and integrity models."""

from datetime import datetime
from pydantic import BaseModel
import polars as pl

OHLCV_SCHEMA: dict[str, type[pl.DataType] | pl.DataType] = {
    "open_time": pl.Datetime("us", time_zone="UTC"),
    "open": pl.Float64,
    "high": pl.Float64,
    "low": pl.Float64,
    "close": pl.Float64,
    "volume": pl.Float64,
    "close_time": pl.Datetime("us", time_zone="UTC"),
    "number_of_trades": pl.Int64,
    "taker_buy_base_volume": pl.Float64,
    "taker_buy_quote_volume": pl.Float64,
}


class GapRecord(BaseModel):
    start: datetime
    end: datetime
    n_missing: int


class IntegrityReport(BaseModel):
    timeframe: str
    n_rows: int
    date_range_start: datetime
    date_range_end: datetime
    n_duplicates: int
    gaps: list[GapRecord]
    zero_volume_count: int
    ohlc_equal_count: int
    price_min: float
    price_max: float
    ohlc_violation_count: int
    nan_counts: dict[str, int]
    passed: bool
    hard_failures: list[str]
