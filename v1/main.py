# v1/main.py
from __future__ import annotations

import logging
import sys
import traceback

from cleaner import load_clean_report_bundle
from config import OUTPUT_PATH
from utils import ensure_dirs, setup_logging
from workpaper_builder import build_workpaper
from write_workbook import write_workbook

logger = logging.getLogger(__name__)


def run() -> int:
    """
    Uploaded-file workflow only.

    This version intentionally does not:
    - open Xero
    - use Selenium
    - use BeautifulSoup
    - download files from browser

    Expected flow:
    frontend/job_runner.py saves uploaded files into v1/data/
    then this script scans v1/data/, detects P&L/BS/support schedules,
    builds the workpaper, and writes the Excel output.
    """
    setup_logging()
    ensure_dirs()

    logger.info("Xero/tax workpaper pipeline starting")
    logger.info("Using uploaded/local Excel inputs from v1/data/")
    logger.info("Output target: %s", OUTPUT_PATH)

    try:
        reports = load_clean_report_bundle()
        workpaper = build_workpaper(reports)
        write_workbook(reports, workpaper)

        logger.info("Pipeline complete: %s", OUTPUT_PATH)
        return 0

    except Exception as exc:
        logger.error("Pipeline failed: %s: %s", type(exc).__name__, exc)
        logger.error("%s", traceback.format_exc())
        return 1


if __name__ == "__main__":
    sys.exit(run())