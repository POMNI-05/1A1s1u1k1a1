import logging

from utils import setup_logging, ensure_dirs
from config import USE_SELENIUM, OUTPUT_PATH
from cleaner import load_raw_reports
from workpaper_builder import build_tax_reconciliation
from write_workbook import write_workbook

setup_logging()
ensure_dirs()

logger = logging.getLogger(__name__)


def run():
    logger.info("=" * 60)
    logger.info("Xero Automation Pipeline - Starting")
    logger.info("=" * 60)

    if USE_SELENIUM:
        logger.info("STEP 0 - Downloading reports from Xero...")
        from downloader import download_report
        download_report("PL")
        download_report("BS")
    else:
        logger.info("STEP 0 - Using local Excel files")

    logger.info("STEP 1 - Loading raw Xero reports")
    raw_pl_df, raw_bs_df = load_raw_reports()

    logger.info("STEP 2 - Building tax reconciliation")
    tax_rec_df = build_tax_reconciliation(raw_pl_df, raw_bs_df)

    logger.info("STEP 3 - Writing final workbook")
    write_workbook(
        raw_pl_df=raw_pl_df,
        raw_bs_df=raw_bs_df,
        tax_rec_df=tax_rec_df,
    )

    logger.info("=" * 60)
    logger.info(f"Pipeline complete. Output: {OUTPUT_PATH}")
    logger.info("=" * 60)


if __name__ == "__main__":
    run()