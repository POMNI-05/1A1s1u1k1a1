# v1/main.py
## Overview of main.py:
"""
main.py
  ├─ utils.setup_logging(), ensure_dirs()
  ├─ if USE_SELENIUM:
  │     └─ downloader.download_report("PL"), download_report("BS")
  ├─ cleaner.load_raw_reports()
  ├─ workpaper_builder.build_workpaper()
  │     ├─ cleaner.load_clean_reports()
  │     ├─ labeller.label_report(PL)
  │     │     └─ itr_rules.match_financial_label()
  │     ├─ labeller.label_report(BS)
  │     │     └─ itr_rules.match_financial_label()
  │     ├─ build tax reconciliation
  │     ├─ build BS checks
  │     └─ build review/support tables
  └─ write_workbook.write_workbook()
        ├─ copy raw Xero sheets
        ├─ write side labels
        ├─ write tax reconciliation
        ├─ write support schedules
        └─ save xero_workpaper.xlsx
"""
from __future__ import annotations

import logging

from cleaner import load_raw_reports
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
        logger.info("Using local Excel exports in data/")

    raw_pl_df, raw_bs_df = load_raw_reports()
    workpaper = build_workpaper()
    write_workbook(raw_pl_df, raw_bs_df, workpaper)
    logger.info("Pipeline complete: %s", OUTPUT_PATH)


if __name__ == "__main__":
    run()