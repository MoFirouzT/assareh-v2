from __future__ import annotations

import io
import json
import logging
import zipfile
import hashlib
from datetime import datetime, timedelta, date, timezone
from pathlib import Path
from typing import Iterable

import ccxt
import numpy as np
import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from tqdm import tqdm

from assareh.config import Settings


logger = logging.getLogger("assareh.fetch")


class BinanceDownloader:
    """Downloader that merges the original v1 implementation with Layer A.3
    improvements: Parquet output, 9-column schema, UTC timestamps,
    checksum verification, retries, and structured logging.
    """

    MONTHLY_URL = "https://data.binance.vision/data/spot/monthly/klines"
    DAILY_URL = "https://data.binance.vision/data/spot/daily/klines"

    REQUIRED_COLUMNS = [
        "open_time",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "close_time",
        "number_of_trades",
        "taker_buy_base_volume",
        "taker_buy_quote_volume",
    ]

    def __init__(self, settings: Settings | None = None, data_dir: str | Path | None = None):
        self.settings = settings or Settings()
        self.data_dir = Path(data_dir) if data_dir is not None else self.settings.data_dir
        self.raw_dir = self.data_dir / self.settings.raw_subdir
        self.raw_dir.mkdir(parents=True, exist_ok=True)

        # requests session with retries
        self.session = requests.Session()
        retries = Retry(total=5, backoff_factor=1.0, status_forcelist=[429, 500, 502, 503, 504])
        adapter = HTTPAdapter(max_retries=retries)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

        self.symbol = self.settings.symbol

    def _parquet_path(self, interval: str) -> Path:
        stem = f"{self.symbol.lower()}_{interval}"
        return self.raw_dir / f"{stem}.parquet"

    def _checksums_path(self) -> Path:
        return self.raw_dir / "checksums.jsonl"

    def _download_url_bytes(self, url: str) -> bytes | None:
        try:
            r = self.session.get(url, timeout=30)
            if r.status_code == 200:
                return r.content
            logger.debug("URL %s returned status %s", url, r.status_code)
            return None
        except Exception:
            logger.exception("Failed to GET %s", url)
            return None

    def _fetch_checksum(self, zip_url: str) -> str | None:
        checksum_url = zip_url + ".CHECKSUM"
        try:
            r = self.session.get(checksum_url, timeout=10)
            if r.status_code != 200:
                logger.debug("No checksum at %s (%s)", checksum_url, r.status_code)
                return None
            text = r.text.strip().split()[0]
            return text
        except Exception:
            logger.exception("Failed to fetch checksum for %s", zip_url)
            return None

    def _verify_sha256(self, data: bytes, expected: str) -> bool:
        h = hashlib.sha256(data).hexdigest()
        return h == expected

    def _extract_csv_bytes(self, zip_bytes: bytes) -> bytes | None:
        try:
            with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
                for name in zf.namelist():
                    if name.lower().endswith('.csv'):
                        return zf.read(name)
        except zipfile.BadZipFile:
            logger.exception("Bad zip file")
        return None

    def _parse_vision_csv(self, csv_bytes: bytes) -> pd.DataFrame:
        # Vision CSV columns (klines): 0 open_time(ms),1 open,2 high,3 low,4 close,5 volume,6 close_time(ms),7 quote_asset_volume,8 number_of_trades,9 taker_buy_base_asset_volume,10 taker_buy_quote_asset_volume,11 ignore
        df = pd.read_csv(io.BytesIO(csv_bytes), header=None)
        df = df.rename(
            columns={
                0: 'open_time',
                1: 'open',
                2: 'high',
                3: 'low',
                4: 'close',
                5: 'volume',
                6: 'close_time',
                8: 'number_of_trades',
                9: 'taker_buy_base_volume',
                10: 'taker_buy_quote_volume',
            }
        )
        # Keep required columns, coerce types
        for c in ['open', 'high', 'low', 'close', 'volume', 'taker_buy_base_volume', 'taker_buy_quote_volume']:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors='coerce')
            else:
                df[c] = pd.NA

        df['number_of_trades'] = pd.to_numeric(df.get('number_of_trades', pd.Series(dtype='Int64')), errors='coerce').fillna(0).astype('Int64')

        # times are expected to be milliseconds. Be defensive: validate numeric
        # values and fall back to unit-detection on failure.
        def _to_datetime_series(s: pd.Series, col_name: str) -> pd.Series:
            # coerce to numeric first
            num = pd.to_numeric(s, errors='coerce')
            if num.isna().all():
                raise ValueError(f"Column {col_name} has no numeric timestamps")
            # quick sanity check: reasonable unix ms range (2010-01-01 .. year 3000)
            ms_min = 1262304000000  # 2010-01-01
            ms_max = 32503680000000  # year 3000
            # microsecond range (us) is ms * 1000
            us_min = ms_min * 1000
            us_max = ms_max * 1000
            # seconds range
            sec_min = 1262304000
            sec_max = 32503680000

            # prefer ms if values fit
            if num.between(ms_min, ms_max).all():
                return pd.to_datetime(num.astype('Int64'), unit='ms', utc=True)
            # prefer us if values fit (v1 handled 16-digit us timestamps)
            if num.between(us_min, us_max).all():
                return pd.to_datetime(num.astype('Int64'), unit='us', utc=True)
            # if values look like seconds (10-digit), try seconds
            if num.between(sec_min, sec_max).all():
                return pd.to_datetime(num.astype('Int64'), unit='s', utc=True)
            # fallback: try ms conversion but catch OutOfBounds and report sample
            try:
                return pd.to_datetime(num.astype('Int64'), unit='ms', utc=True)
            except Exception:
                sample = list(num.head(10).values)
                logger.exception("Failed to parse timestamps for %s; sample=%s", col_name, sample)
                raise

        # Prefer renamed columns, fall back to positional indices if needed
        if 'open_time' in df.columns:
            src_open = df['open_time']
        else:
            src_open = df.iloc[:, 0]
        df['open_time'] = _to_datetime_series(src_open, 'open_time')

        if 'close_time' in df.columns:
            src_close = df['close_time']
        elif df.shape[1] > 6:
            src_close = df.iloc[:, 6]
        else:
            src_close = None
        if src_close is None:
            df['close_time'] = pd.NaT
        else:
            df['close_time'] = _to_datetime_series(src_close, 'close_time')

        # Ensure column order and names
        df = df[[c for c in self.REQUIRED_COLUMNS if c in df.columns]]
        # If any missing required column (shouldn't), add with NA
        for c in self.REQUIRED_COLUMNS:
            if c not in df.columns:
                df[c] = pd.NA

        return df

    def _append_checksums_log(self, url: str, sha256: str, filename: str) -> None:
        rec = {'fetched_at': datetime.now(timezone.utc).isoformat(), 'url': url, 'sha256': sha256, 'filename': filename}
        path = self._checksums_path()
        with path.open('a', encoding='utf8') as fh:
            fh.write(json.dumps(rec) + '\n')

    def _write_parquet(self, df: pd.DataFrame, path: Path) -> None:
        df.to_parquet(path, index=False, compression='zstd')

    def _merge_into_parquet(self, df: pd.DataFrame, path: Path) -> None:
        if path.exists():
            existing = pd.read_parquet(path)
            combined = pd.concat([existing, df], ignore_index=True)
            # dedupe by open_time
            combined = combined.drop_duplicates(subset=['open_time']).sort_values('open_time')
            self._write_parquet(combined, path)
        else:
            self._write_parquet(df, path)

    def _vision_month_urls(
        self,
        interval: str,
        start_year: int = 2017,
        start_month: int = 1,
    ) -> Iterable[str]:
        today = datetime.now(timezone.utc).date()
        last_month = (today.replace(day=1) - timedelta(days=1))
        year = start_year
        month = start_month
        while date(year, month, 1) <= last_month:
            url = f"{self.MONTHLY_URL}/{self.symbol}/{interval}/{self.symbol}-{interval}-{year:04d}-{month:02d}.zip"
            yield url
            if month == 12:
                year += 1
                month = 1
            else:
                month += 1

    def _vision_daily_urls_current_month(self, interval: str) -> Iterable[str]:
        today = datetime.now(timezone.utc).date()
        first_of_month = today.replace(day=1)
        day = first_of_month
        while day <= today:
            url = f"{self.DAILY_URL}/{self.symbol}/{interval}/{self.symbol}-{interval}-{day.strftime('%Y-%m-%d')}.zip"
            yield url
            day = day + timedelta(days=1)

    def download(self, interval: str, start_date: datetime | None = None) -> pd.DataFrame | None:
        """Download historical data (monthly archives + daily current month) and write Parquet.

        Returns the concatenated DataFrame or None if nothing downloaded.
        """
        path = self._parquet_path(interval)
        downloaded_any = False

        for url in tqdm(list(self._vision_month_urls(interval)), desc=f"monthly {interval}"):
            data = self._download_url_bytes(url)
            if data is None:
                continue
            checksum = self._fetch_checksum(url) or ""
            if checksum and not self._verify_sha256(data, checksum):
                raise RuntimeError(f"Checksum mismatch for {url}")
            csv_bytes = self._extract_csv_bytes(data)
            if csv_bytes is None:
                logger.warning("No CSV in %s", url)
                continue
            df = self._parse_vision_csv(csv_bytes)
            self._merge_into_parquet(df, path)
            if checksum:
                self._append_checksums_log(url, checksum, path.name)
            downloaded_any = True

        for url in tqdm(list(self._vision_daily_urls_current_month(interval)), desc=f"daily {interval}"):
            data = self._download_url_bytes(url)
            if data is None:
                continue
            checksum = self._fetch_checksum(url) or ""
            if checksum and not self._verify_sha256(data, checksum):
                raise RuntimeError(f"Checksum mismatch for {url}")
            csv_bytes = self._extract_csv_bytes(data)
            if csv_bytes is None:
                continue
            df = self._parse_vision_csv(csv_bytes)
            self._merge_into_parquet(df, path)
            if checksum:
                self._append_checksums_log(url, checksum, path.name)
            downloaded_any = True

        if not downloaded_any:
            logger.info("No archives downloaded for %s %s", self.symbol, interval)
            return None

        # return dataframe for convenience
        df = pd.read_parquet(path)
        return df

    def load(self, interval: str) -> pd.DataFrame | None:
        path = self._parquet_path(interval)
        if path.exists():
            df = pd.read_parquet(path)
            # ensure timezone-aware datetimes
            if not pd.api.types.is_datetime64tz_dtype(df['open_time']):
                df['open_time'] = pd.to_datetime(df['open_time']).dt.tz_localize('UTC')
            return df
        return None

    def _get_interval_config(self, interval: str):
        # reuse v1 table
        configs = {
            '1m': (0.5, 2000),
            '3m': (1, 1500),
            '5m': (2, 1500),
            '15m': (4, 1200),
            '30m': (8, 1000),
            '1h': (12, 1000),
            '2h': (24, 1000),
            '4h': (48, 1000),
            '6h': (72, 1000),
            '12h': (120, 1000),
            '1d': (240, 1000),
        }
        return configs.get(interval, (24, 1000))

    def _interval_timedelta(self, interval: str) -> timedelta:
        import re
        m = re.match(r"(\d+)([mhd])", interval)
        if not m:
            return timedelta(minutes=1)
        val = int(m.group(1))
        unit = m.group(2)
        if unit == 'm':
            return timedelta(minutes=val)
        if unit == 'h':
            return timedelta(hours=val)
        if unit == 'd':
            return timedelta(days=val)
        return timedelta(minutes=1)

    def _is_candle_complete(self, timestamp: datetime, interval: str) -> bool:
        now = datetime.now(timezone.utc)
        candle_dur = self._interval_timedelta(interval)
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        candle_end = timestamp + candle_dur
        return candle_end < now

    def _remove_incomplete_candles(self, df: pd.DataFrame, interval: str) -> pd.DataFrame:
        if df is None or len(df) == 0:
            return df
        last_ts = pd.to_datetime(df['open_time']).max()
        if not self._is_candle_complete(last_ts.to_pydatetime(), interval):
            logger.info("Removing incomplete candle at %s", last_ts)
            # drop rows with open_time == last_ts
            df = df[df['open_time'] != last_ts]
        return df

    def _fetch_ccxt_ohlcv(self, interval: str, since: int | None = None, limit: int | None = None) -> pd.DataFrame:
        exchange = ccxt.binance()
        if limit is None:
            _, limit = self._get_interval_config(interval)
        timeframe = interval
        all_rows = []
        current_since = since
        while True:
            if current_since:
                ohlcv = exchange.fetch_ohlcv(self.symbol, timeframe, since=current_since, limit=1000)
            else:
                ohlcv = exchange.fetch_ohlcv(self.symbol, timeframe, limit=1000)
            if not ohlcv:
                break
            all_rows.extend(ohlcv)
            if len(all_rows) >= limit or len(ohlcv) < 1000:
                break
            current_since = ohlcv[-1][0] + 1
            if current_since > datetime.now(timezone.utc).timestamp() * 1000:
                break
        if len(all_rows) > limit:
            all_rows = all_rows[:limit]
        df = pd.DataFrame(all_rows, columns=['open_time', 'open', 'high', 'low', 'close', 'volume'])
        df['close_time'] = df['open_time'] + 1
        df['number_of_trades'] = 0
        df['taker_buy_base_volume'] = 0.0
        df['taker_buy_quote_volume'] = 0.0
        df['open_time'] = pd.to_datetime(df['open_time'], unit='ms', utc=True)
        df['close_time'] = pd.to_datetime(df['close_time'], unit='ms', utc=True)
        df = df[[c for c in self.REQUIRED_COLUMNS if c in df.columns]]
        for c in self.REQUIRED_COLUMNS:
            if c not in df.columns:
                df[c] = pd.NA
        return df

    def _verify_overlap(self, existing: pd.DataFrame, new: pd.DataFrame, overlap_rows: int = 10) -> bool:
        # Align index by open_time
        existing_idx = pd.to_datetime(existing['open_time'])
        new_idx = pd.to_datetime(new['open_time'])
        common = existing_idx[existing_idx.isin(new_idx)]
        if len(common) == 0:
            logger.warning("No overlap between existing and ccxt data")
            return False
        common_sorted = sorted(common)
        if len(common_sorted) > 1:
            common_complete = common_sorted[:-1]
        else:
            common_complete = common_sorted
        if len(common_complete) < min(overlap_rows, 5):
            logger.warning("Only %d complete overlapping candles found", len(common_complete))
            if len(common_complete) == 0:
                logger.warning("Only incomplete overlap found; skipping strict verification")
                return True
        overlap_count = min(len(common_complete), overlap_rows)
        sample_times = common_complete[-overlap_count:]
        bin_sample = existing.set_index(pd.to_datetime(existing['open_time'])).loc[sample_times]
        ccxt_sample = new.set_index(pd.to_datetime(new['open_time'])).loc[sample_times]
        cols = ['open', 'high', 'low', 'close', 'volume']
        all_match = True
        for col in cols:
            try:
                if not np.allclose(bin_sample[col], ccxt_sample[col], rtol=1e-3 if col == 'volume' else 1e-5, atol=1e-8):
                    diff_mask = ~np.isclose(bin_sample[col], ccxt_sample[col], rtol=1e-3 if col == 'volume' else 1e-5, atol=1e-8)
                    diff_count = diff_mask.sum()
                    diff_pct = (diff_count / len(sample_times)) * 100
                    if diff_pct > 20:
                        logger.error("Significant mismatch in %s: %d/%d rows differ (%.1f%%)", col, diff_count, len(sample_times), diff_pct)
                        all_match = False
                    else:
                        logger.warning("Minor differences in %s: %d/%d rows (%.1f%%)", col, diff_count, len(sample_times), diff_pct)
            except Exception:
                logger.exception("Error comparing column %s", col)
        if all_match:
            logger.info("Verified %d completed candles - data compatible", overlap_count)
        return all_match

    def update_with_ccxt(self, interval: str | None = None, verify: bool = True) -> None:
        intervals = [interval] if interval else self.settings.intervals
        for intv in intervals:
            logger.info("Updating %s with ccxt", intv)
            path = self._parquet_path(intv)
            existing = self.load(intv)
            if existing is None:
                logger.warning("No existing data for %s - run download() first", intv)
                continue
            last_ts = pd.to_datetime(existing['open_time']).max()
            lookback_hours, _ = self._get_interval_config(intv)
            since_ms = int((last_ts - timedelta(hours=lookback_hours)).timestamp() * 1000)
            try:
                new = self._fetch_ccxt_ohlcv(intv, since=since_ms)
                logger.info("Fetched %d rows from ccxt", len(new))
                if verify:
                    if not self._verify_overlap(existing, new):
                        raise RuntimeError("ccxt overlap verification failed")
                # keep only rows newer than existing.max
                new_only = new[pd.to_datetime(new['open_time']) > pd.to_datetime(existing['open_time']).max()]
                new_only = self._remove_incomplete_candles(new_only, intv)
                if len(new_only) > 0:
                    self._merge_into_parquet(new_only, path)
                    logger.info("Appended %d new rows to %s", len(new_only), path)
                else:
                    logger.info("No new rows to append for %s", intv)
            except Exception:
                logger.exception("Failed ccxt update for %s", intv)

    def update(self, interval: str | None = None) -> None:
        intervals = [interval] if interval else self.settings.intervals
        for intv in intervals:
            logger.info("Running update for %s", intv)
            path = self._parquet_path(intv)
            existing = self.load(intv)
            if existing is None:
                logger.info("No existing data - running full download for %s", intv)
                self.download(intv)
                continue
            last_date = pd.to_datetime(existing['open_time']).max().to_pydatetime()
            logger.info("Last data point: %s", last_date)
            # decide whether to download monthly archives
            current_month_start = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            last_month_start = (current_month_start - timedelta(days=1)).replace(day=1)
            if last_date < last_month_start:
                start_month = (last_date + timedelta(days=1)).replace(day=1)
                # download monthly from start_month to now
                for url in self._vision_month_urls(intv, start_year=start_month.year, start_month=start_month.month):
                    data = self._download_url_bytes(url)
                    if data is None:
                        continue
                    checksum = self._fetch_checksum(url) or ""
                    if checksum and not self._verify_sha256(data, checksum):
                        raise RuntimeError(f"Checksum mismatch for {url}")
                    csv_bytes = self._extract_csv_bytes(data)
                    if csv_bytes is None:
                        continue
                    df = self._parse_vision_csv(csv_bytes)
                    self._merge_into_parquet(df, path)
                    if checksum:
                        self._append_checksums_log(url, checksum, path.name)
            # daily updates from day after last_date
            daily_start = max((last_date + timedelta(days=1)).date(), current_month_start.date())
            if daily_start <= (datetime.now(timezone.utc) - timedelta(days=1)).date():
                day = daily_start
                end_day = (datetime.now(timezone.utc) - timedelta(days=1)).date()
                while day <= end_day:
                    url = f"{self.DAILY_URL}/{self.symbol}/{intv}/{self.symbol}-{intv}-{day.strftime('%Y-%m-%d')}.zip"
                    data = self._download_url_bytes(url)
                    if data is None:
                        day = day + timedelta(days=1)
                        continue
                    checksum = self._fetch_checksum(url) or ""
                    if checksum and not self._verify_sha256(data, checksum):
                        raise RuntimeError(f"Checksum mismatch for {url}")
                    csv_bytes = self._extract_csv_bytes(data)
                    if csv_bytes is None:
                        day = day + timedelta(days=1)
                        continue
                    df = self._parse_vision_csv(csv_bytes)
                    self._merge_into_parquet(df, path)
                    if checksum:
                        self._append_checksums_log(url, checksum, path.name)
                    day = day + timedelta(days=1)

    def wipe_last_entries(self, interval: str, count: int = 1) -> None:
        path = self._parquet_path(interval)
        if path.exists():
            df = pd.read_parquet(path)
            original = len(df)
            df = df[:-count]
            df.to_parquet(path, index=False, compression='zstd')
            logger.info("Removed last %d entries from %s (was %d, now %d)", count, path, original, len(df))
        else:
            logger.warning("File %s does not exist", path)


__all__ = ["BinanceDownloader"]