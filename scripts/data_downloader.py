"""Stub for BinanceDownloader to be adapted in Phase A.3.

This module contains a minimal stub so the repo has the expected layout for
Phase A.1. The full downloader implementation is added in Phase A.3.
"""

import logging

logger = logging.getLogger("assareh.fetch")


class BinanceDownloader:
    def __init__(self, data_dir):
        self.data_dir = data_dir

    def update(self, interval: str):
        logger.info("Stub update called for %s", interval)
