# v1/main.py
from __future__ import annotations

import logging

from cleaner import load_clean_report_bundle
from config import OUTPUT_PATH, USE_SELENIUM
from utils import ensure_dirs, setup_logging
from workpaper_builder import build_workpaper
from write_workbook import write_workbook

logger = logging.getLogger(__name__)


def run() -> None:
    setup_logging()
    ensure_dirs()

    logger.info("Xero workpaper pipeline starting")

    if USE_SELENIUM:
        logger.info("Downloading Xero reports")

        from downloader import download_report

        download_report("PL")
        download_report("BS")
    else:
        logger.info("Using local Excel inputs from data/")

    reports = load_clean_report_bundle()
    workpaper = build_workpaper(reports)

    write_workbook(reports, workpaper)

    logger.info("Pipeline complete: %s", OUTPUT_PATH)


if __name__ == "__main__":
    run()