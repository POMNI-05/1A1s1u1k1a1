from __future__ import annotations

import logging
import os
import sys
import traceback
from pathlib import Path

from ai_review import (
    WorkpaperContractError,
    WorkpaperResult,
    WorkpaperStatus,
    read_workpaper_request,
    write_workpaper_result,
)

logger = logging.getLogger(__name__)


def _apply_request_environment():
    """Load the explicit request before importing legacy env-driven modules."""

    request_path_value = os.getenv("TAX_WORKPAPER_REQUEST_PATH", "").strip()
    if not request_path_value:
        return None

    request = read_workpaper_request(Path(request_path_value))
    os.environ["ATO_POLICY_YEAR"] = request.income_year
    os.environ["ITR_POLICY_YEAR"] = request.income_year
    os.environ["SELECTED_INCOME_YEAR"] = request.income_year
    os.environ["COMPANY_TAX_RATE_CATEGORY"] = str(
        request.job_options.get("company_tax_rate_category", "review_required")
    )
    os.environ["TAX_JOB_CONFIG_PATH"] = request_path_value
    os.environ["TAX_JOB_WORK_DIR"] = request.work_dir
    os.environ["TAX_DATA_DIR"] = request.input_dir
    os.environ["TAX_OUTPUT_DIR"] = str(Path(request.output_path).parent)
    os.environ["TAX_OUTPUT_PATH"] = request.output_path
    os.environ["TAX_LOG_DIR"] = request.log_dir
    return request


def _write_backend_result(result: WorkpaperResult) -> None:
    result_path_value = os.getenv("TAX_WORKPAPER_RESULT_PATH", "").strip()
    if not result_path_value:
        return
    write_workpaper_result(result, Path(result_path_value))


def _error_code(exc: Exception) -> str:
    message = str(exc).strip()
    prefix = message.split(":", maxsplit=1)[0]
    if prefix and prefix.replace("-", "").isalnum():
        return prefix
    return type(exc).__name__


def run() -> int:
    """Run the uploaded-workbook backend, optionally through a JSON contract."""

    request = None
    try:
        request = _apply_request_environment()

        try:
            from .cleaner import load_clean_report_bundle
            from .config import OUTPUT_PATH
            from .utils import ensure_dirs, setup_logging
            from .workpaper_builder import build_workpaper
            from .write_workbook import write_workbook
        except ImportError:  # Direct-script compatibility.
            from cleaner import load_clean_report_bundle
            from config import OUTPUT_PATH
            from utils import ensure_dirs, setup_logging
            from workpaper_builder import build_workpaper
            from write_workbook import write_workbook

        setup_logging()
        ensure_dirs()

        logger.info("Xero/tax workpaper pipeline starting")
        logger.info("Using uploaded/local Excel inputs from v1/data/")
        logger.info("Output target: %s", OUTPUT_PATH)

        reports = load_clean_report_bundle()
        workpaper = build_workpaper(reports)
        write_workbook(reports, workpaper)

        logger.info("Pipeline complete: %s", OUTPUT_PATH)
        if request is not None:
            _write_backend_result(
                WorkpaperResult(
                    job_id=request.job_id,
                    income_year=request.income_year,
                    status=WorkpaperStatus.COMPLETED,
                    output_path=str(OUTPUT_PATH),
                    review_items=workpaper.deterministic_review_items,
                    decision_traces=workpaper.decision_traces,
                    metadata={
                        "contract_version": "1.0",
                        "backend": "v1.main",
                    },
                )
            )
        return 0

    except Exception as exc:
        logger.error("Pipeline failed: %s: %s", type(exc).__name__, exc)
        logger.error("%s", traceback.format_exc())
        if request is not None:
            _write_backend_result(
                WorkpaperResult(
                    job_id=request.job_id,
                    income_year=request.income_year,
                    status=WorkpaperStatus.FAILED,
                    output_path=None,
                    error_code=_error_code(exc),
                    error_message=str(exc),
                    metadata={
                        "contract_version": "1.0",
                        "backend": "v1.main",
                    },
                )
            )
        return 1


if __name__ == "__main__":
    sys.exit(run())
