"""Entrypoint stub for fetching Binance OHLCV data.

Implements a minimal CLI-style entrypoint that will be expanded in Phase A.3.
"""

from assareh.config import Settings
from .data_downloader import BinanceDownloader
import logging


def main() -> int:
    settings = Settings()
    logging.basicConfig(level=settings.log_level)
    dl = BinanceDownloader(settings.data_dir)
    for intv in settings.intervals:
        dl.update(intv)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
