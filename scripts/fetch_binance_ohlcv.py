from __future__ import annotations

import argparse
import logging

from assareh.config import Settings
from data_downloader import BinanceDownloader


def configure_logging(level: str) -> None:
    logging.basicConfig(
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        level=getattr(logging, level.upper(), logging.INFO),
    )


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Fetch Binance OHLCV and write Parquet files")
    p.add_argument("--intervals", nargs="*", help="Intervals to fetch (overrides settings)")
    p.add_argument("--dry-run", action="store_true", help="Don't perform network calls; show planned actions")
    return p.parse_args()


def main(argv: list[str] | None = None) -> int:
    args = parse_args() if argv is None else parse_args()
    settings = Settings()
    configure_logging(settings.log_level)
    logger = logging.getLogger("assareh.fetch")

    intervals = args.intervals if args.intervals else settings.intervals

    downloader = BinanceDownloader(settings=settings, data_dir=settings.data_dir)

    if args.dry_run:
        logger.info("Dry run: would update the following intervals: %s", intervals)
        for intv in intervals:
            path = downloader._parquet_path(intv)
            logger.info("Would ensure Parquet: %s", path)
        return 0

    try:
        for intv in intervals:
            logger.info("Updating archives for %s", intv)
            downloader.update(intv)
            logger.info("Filling tail with ccxt for %s", intv)
            downloader.update_with_ccxt(intv, verify=True)
    except Exception:
        logger.exception("Fetch failed")
        return 2

    logger.info("Fetch completed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
