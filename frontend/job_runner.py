# frontend/job_runner.py
"""
Bridge between Streamlit UI and v1 backend.

Responsibilities:
- Save uploaded files to uploads/ folder
- Point v1 config paths to uploaded files
- Call v1 backend pipeline
- Return structured result dict to app.py

app.py handles UI only.
job_runner.py handles execution.
v1/ handles all tax logic.
"""
from __future__ import annotations

import logging
import shutil
import sys
import traceback
from datetime import datetime
from pathlib import Path
from typing import BinaryIO

from v1.utils import ensure_dirs

# ── Make v1 importable ────────────────────────────────────────────────────────
FRONTEND_DIR = Path(__file__).resolve().parent
ROOT_DIR     = FRONTEND_DIR.parent
V1_DIR       = ROOT_DIR / "v1"
sys.path.insert(0, str(V1_DIR))

UPLOADS_DIR   = FRONTEND_DIR / "uploads"
DOWNLOADS_DIR = FRONTEND_DIR / "downloads"

UPLOADS_DIR.mkdir(exist_ok=True)
DOWNLOADS_DIR.mkdir(exist_ok=True)

logger = logging.getLogger(__name__)


# ── File helpers ──────────────────────────────────────────────────────────────

def save_uploaded_file(uploaded_file: BinaryIO, filename: str) -> Path:
    """Save a Streamlit UploadedFile to uploads/ and return its path."""
    dest = UPLOADS_DIR / filename
    with open(dest, "wb") as f:
        f.write(uploaded_file.read())
    logger.info("Saved upload: %s", dest)
    return dest


def _timestamped_output_name(client_name: str = "") -> str:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in client_name).strip("_")
    prefix = f"{safe}_" if safe else ""
    return f"{prefix}workpaper_{ts}.xlsx"


# ── Main job ──────────────────────────────────────────────────────────────────

def run_workpaper_job(
    pl_file:          BinaryIO | None,
    bs_file:          BinaryIO | None,
    combined_file:    BinaryIO | None,
    company_profile:  str,
    document_description: str,
    client_name:      str = "",
) -> dict:
    """
    Run the full v1 workpaper pipeline.

    Returns:
        {
            "status":        "success" | "error",
            "output_path":   Path | None,
            "output_name":   str,
            "detected":      {...},
            "review_count":  int,
            "warnings":      [...],
            "error_message": str | None,
        }
    """
    result: dict = {
        "status":        "error",
        "output_path":   None,
        "output_name":   "",
        "detected":      {},
        "review_count":  0,
        "warnings":      [],
        "error_message": None,
    }

    try:
        # ── 1. Save uploaded files ─────────────────────────────────────────
        pl_path       = None
        bs_path       = None
        combined_path = None

        if combined_file is not None:
            combined_path = save_uploaded_file(combined_file, "combined_input.xlsx")
        if pl_file is not None:
            pl_path = save_uploaded_file(pl_file, "profit_and_loss_raw.xlsx")
        if bs_file is not None:
            bs_path = save_uploaded_file(bs_file, "balance_sheet_raw.xlsx")

        if combined_path is None and (pl_path is None or bs_path is None):
            result["error_message"] = "Please upload either a combined workbook or separate P&L and Balance Sheet files."
            return result

        # ── 2. Point v1 config to uploaded files ──────────────────────────
        import config as v1_config

        if combined_path:
            # If combined: copy to v1/data/ so cleaner can find it
            dest_combined = V1_DIR / "data" / "combined_input.xlsx"
            shutil.copy2(combined_path, dest_combined)
            # v1 cleaner will auto-detect sheets inside
            v1_config.PL_RAW_PATH = str(dest_combined)
            v1_config.BS_RAW_PATH = str(dest_combined)
        else:
            dest_pl = V1_DIR / "data" / "profit_and_loss_raw.xlsx"
            dest_bs = V1_DIR / "data" / "balance_sheet_raw.xlsx"
            shutil.copy2(pl_path, dest_pl)
            shutil.copy2(bs_path, dest_bs)
            v1_config.PL_RAW_PATH = str(dest_pl)
            v1_config.BS_RAW_PATH = str(dest_bs)

        # ── 3. Set output path to downloads/ ──────────────────────────────
        output_name = _timestamped_output_name(client_name)
        output_path = DOWNLOADS_DIR / output_name
        v1_config.OUTPUT_PATH = str(output_path)

        # ── 4. Store metadata for audit trail ────────────────────────────
        # These aren't yet used by the backend rules, but stored for future use
        v1_config._JOB_COMPANY_PROFILE      = company_profile.strip()
        v1_config._JOB_DOCUMENT_DESCRIPTION = document_description.strip()

        # ── 5. Run backend ────────────────────────────────────────────────
        from v1.utils import setup_logging, ensure_dirs
        setup_logging()
        ensure_dirs()

        from v1.cleaner import load_raw_reports
        raw_pl_df, raw_bs_df = load_raw_reports()

        from v1.workpaper_builder import build_workpaper
        workpaper = build_workpaper()

        from v1.write_workbook import write_workbook
        write_workbook(raw_pl_df, raw_bs_df, workpaper)

        # ── 6. Build result summary ───────────────────────────────────────
        detected = {
            "P&L":           pl_path is not None or combined_path is not None,
            "Balance Sheet": bs_path is not None or combined_path is not None,
        }

        # Count review items from labelled P&L + BS
        review_count = 0
        if workpaper.labelled_pl is not None and "Confidence" in workpaper.labelled_pl.columns:
            review_count += workpaper.labelled_pl["Confidence"].astype(str).str.lower().isin(["medium", "low"]).sum()
        if workpaper.labelled_bs is not None and "Confidence" in workpaper.labelled_bs.columns:
            review_count += workpaper.labelled_bs["Confidence"].astype(str).str.lower().isin(["medium", "low"]).sum()

        # Collect warnings from BS checks
        warnings = []
        if workpaper.bs_checks is not None and not workpaper.bs_checks.empty:
            for _, row in workpaper.bs_checks.iterrows():
                for col in workpaper.bs_checks.columns:
                    val = row.get(col)
                    if isinstance(val, (int, float)) and abs(val) > 1:
                        warnings.append(f"{row.get('Check', 'BS check')}: variance {val:,.2f} in {col}")

        result.update({
            "status":      "success",
            "output_path": output_path,
            "output_name": output_name,
            "detected":    detected,
            "review_count": int(review_count),
            "warnings":    warnings,
        })

    except Exception as exc:
        logger.exception("job_runner error")
        result["error_message"] = f"{type(exc).__name__}: {exc}\n\n{traceback.format_exc()}"

    return result