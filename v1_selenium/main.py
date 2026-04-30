# v1_selenium/main.py
# Orchestrator — runs the full pipeline end to end

import logging

from utils import setup_logging, ensure_dirs
from config import USE_SELENIUM, OUTPUT_PATH
from cleaner import load_raw_reports
from workpaper_builder import build_workpaper
from write_workbook import write_workbook

setup_logging()
ensure_dirs()

logger = logging.getLogger(__name__)


def run():
    logger.info("═" * 60)
    logger.info("Xero Automation Pipeline — Starting")
    logger.info("═" * 60)

    # Step 0: Selenium download or local files
    if USE_SELENIUM:
        logger.info("STEP 0 — Downloading reports from Xero...")
        from downloader import download_report

        download_report("PL")
        download_report("BS")
        logger.info("✓ Step 0 complete — reports downloaded")
    else:
        logger.info("STEP 0 — Skipped Selenium download")
        logger.info("Using local Excel files from v1_selenium/data/")

    # Step 1: Load raw files
    logger.info("STEP 1 — Loading raw Excel files...")
    raw_pl_df, raw_bs_df = load_raw_reports()

    logger.info(f"  Raw P&L rows:           {len(raw_pl_df)}")
    logger.info(f"  Raw Balance Sheet rows: {len(raw_bs_df)}")
    logger.info("✓ Step 1 complete — raw files loaded")

    # Step 2: Build tax reconciliation
    logger.info("STEP 2 — Building tax workpaper...")
    tax_rec_df, checks_df = build_workpaper(raw_pl_df, raw_bs_df)
    logger.info("✓ Step 2 complete — tax workpaper built")

    # Step 3: Write output workbook
    logger.info("STEP 3 — Writing output workbook...")
    write_workbook(
        raw_pl_df=raw_pl_df,
        raw_bs_df=raw_bs_df,
        tax_rec_df=tax_rec_df,
        checks_df=checks_df,
    )
    logger.info("✓ Step 3 complete — workbook written")

    logger.info("═" * 60)
    logger.info(f"Pipeline complete. Output: {OUTPUT_PATH}")
    logger.info("═" * 60)


if __name__ == "__main__":
    run()