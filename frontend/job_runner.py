# frontend/job_runner.py
"""
Bridge between Streamlit UI and v1 backend.

Design:
- Frontend only saves uploaded Excel files.
- v1 backend keeps responsibility for detecting P&L / Balance Sheet.
- Supports:
    1. One combined workbook
    2. Separate P&L and Balance Sheet files
    3. Multiple uploaded Excel files
- Avoids forcing PL_RAW_PATH and BS_RAW_PATH to the same workbook,
  because that can cause Balance Sheet to be selected as P&L sheet.
"""

from __future__ import annotations

import logging
import shutil
import sys
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, BinaryIO, Iterable


# ── Paths ─────────────────────────────────────────────────────────────────────
FRONTEND_DIR = Path(__file__).resolve().parent
ROOT_DIR = FRONTEND_DIR.parent
V1_DIR = ROOT_DIR / "v1"

# Make project root and v1 importable
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
if str(V1_DIR) not in sys.path:
    sys.path.insert(0, str(V1_DIR))

UPLOADS_DIR = FRONTEND_DIR / "uploads"
DOWNLOADS_DIR = FRONTEND_DIR / "downloads"
V1_DATA_DIR = V1_DIR / "data"

UPLOADS_DIR.mkdir(exist_ok=True)
DOWNLOADS_DIR.mkdir(exist_ok=True)
V1_DATA_DIR.mkdir(exist_ok=True)

logger = logging.getLogger(__name__)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _as_list(value: Any) -> list[Any]:
    """
    Streamlit file_uploader may return:
    - None
    - one UploadedFile
    - list[UploadedFile] when accept_multiple_files=True

    Convert all cases into a list.
    """
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return list(value)
    return [value]


def _safe_filename(name: str, fallback: str = "uploaded.xlsx") -> str:
    """
    Make uploaded filename safe for local filesystem.
    Keeps extension where possible.
    """
    name = name or fallback
    safe = "".join(c if c.isalnum() or c in " ._-()" else "_" for c in name).strip()
    if not safe:
        safe = fallback
    return safe


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _timestamped_output_name(client_name: str = "") -> str:
    ts = _timestamp()
    safe_client = "".join(
        c if c.isalnum() or c in "-_" else "_"
        for c in (client_name or "")
    ).strip("_")

    prefix = f"{safe_client}_" if safe_client else ""
    return f"{prefix}workpaper_{ts}.xlsx"


def _save_uploaded_file(uploaded_file: BinaryIO, dest_dir: Path, prefix: str, index: int) -> Path:
    """
    Save a Streamlit UploadedFile to dest_dir.
    """
    original_name = getattr(uploaded_file, "name", f"{prefix}_{index}.xlsx")
    safe_name = _safe_filename(original_name, fallback=f"{prefix}_{index}.xlsx")

    # Avoid duplicate filename collisions
    dest = dest_dir / f"{prefix}_{index:02d}_{safe_name}"

    # Important: reset pointer if possible
    try:
        uploaded_file.seek(0)
    except Exception:
        pass

    with open(dest, "wb") as f:
        f.write(uploaded_file.read())

    logger.info("Saved uploaded file: %s", dest)
    return dest


def _clear_excel_files_from_v1_data() -> None:
    """
    Clear old Excel inputs from v1/data before a frontend run.

    Reason:
    The backend scans v1/data. If old files remain there, frontend uploads can
    compete with stale files, causing wrong report selection.
    """
    for path in V1_DATA_DIR.iterdir():
        if path.is_file() and path.suffix.lower() in {".xlsx", ".xls", ".xlsm"}:
            path.unlink()
            logger.info("Removed old v1/data input: %s", path)


def _copy_inputs_to_v1_data(input_paths: Iterable[Path]) -> list[Path]:
    """
    Copy uploaded files into v1/data so backend can scan them naturally.
    """
    copied: list[Path] = []

    for path in input_paths:
        dest = V1_DATA_DIR / path.name
        shutil.copy2(path, dest)
        copied.append(dest)
        logger.info("Copied frontend upload to v1/data: %s", dest)

    return copied


def _set_backend_config(output_path: Path, company_profile: str, document_description: str) -> None:
    """
    Configure v1 backend for this frontend job.

    Important:
    Do NOT force PL_RAW_PATH and BS_RAW_PATH to the same combined workbook.
    Let cleaner.load_raw_reports() auto-detect from v1/data.
    """
    try:
        import v1.config as v1_config
    except Exception:
        import v1.config as v1_config

    # Output path
    v1_config.OUTPUT_PATH = str(output_path)

    # Let cleaner auto-detect reports from v1/data
    # Use "" rather than None because some codebases call Path(...) or truthiness checks.
    if hasattr(v1_config, "PL_RAW_PATH"):
        v1_config.PL_RAW_PATH = ""
    if hasattr(v1_config, "BS_RAW_PATH"):
        v1_config.BS_RAW_PATH = ""

    # If backend supports configurable data dir, point it at v1/data
    if hasattr(v1_config, "DATA_DIR"):
        v1_config.DATA_DIR = str(V1_DATA_DIR)

    # Store audit metadata for future workbook notes
    v1_config._JOB_COMPANY_PROFILE = (company_profile or "").strip()
    v1_config._JOB_DOCUMENT_DESCRIPTION = (document_description or "").strip()


def _run_backend_pipeline() -> tuple[Any, Any, Any]:
    """
    Run v1 backend in the same shape as backend main.py.

    Returns:
        raw_pl_df, raw_bs_df, workpaper
    """
    try:
        from v1.utils import setup_logging, ensure_dirs
        from v1.cleaner import load_raw_reports
        from v1.workpaper_builder import build_workpaper
        from v1.write_workbook import write_workbook
    except Exception:
        from v1.utils import setup_logging, ensure_dirs
        from v1.cleaner import load_raw_reports
        from v1.workpaper_builder import build_workpaper
        from v1.write_workbook import write_workbook

    setup_logging()
    ensure_dirs()

    raw_pl_df, raw_bs_df = load_raw_reports()
    workpaper = build_workpaper()

    # Your current backend write_workbook accepts 2 args, not 3.
    write_workbook(raw_pl_df, raw_bs_df)

    return raw_pl_df, raw_bs_df, workpaper


def _build_result_summary(
    output_path: Path,
    output_name: str,
    copied_inputs: list[Path],
    workpaper: Any,
) -> dict:
    """
    Build clean result dict for app.py.
    """
    review_count = 0

    labelled_pl = getattr(workpaper, "labelled_pl", None)
    labelled_bs = getattr(workpaper, "labelled_bs", None)

    if labelled_pl is not None and "Confidence" in labelled_pl.columns:
        review_count += int(
            labelled_pl["Confidence"]
            .astype(str)
            .str.lower()
            .isin(["medium", "low"])
            .sum()
        )

    if labelled_bs is not None and "Confidence" in labelled_bs.columns:
        review_count += int(
            labelled_bs["Confidence"]
            .astype(str)
            .str.lower()
            .isin(["medium", "low"])
            .sum()
        )

    warnings: list[str] = []
    bs_checks = getattr(workpaper, "bs_checks", None)

    if bs_checks is not None and not bs_checks.empty:
        for _, row in bs_checks.iterrows():
            for col in bs_checks.columns:
                val = row.get(col)
                if isinstance(val, (int, float)) and abs(val) > 1:
                    warnings.append(
                        f"{row.get('Check', 'BS check')}: variance {val:,.2f} in {col}"
                    )

    return {
        "status": "success",
        "output_path": output_path,
        "output_name": output_name,
        "detected": {
            "P&L": labelled_pl is not None,
            "Balance Sheet": labelled_bs is not None,
        },
        "review_count": review_count,
        "warnings": warnings,
        "uploaded_files": [p.name for p in copied_inputs],
        "error_message": None,
    }


# ── Main job ──────────────────────────────────────────────────────────────────

def run_workpaper_job(
    pl_file: BinaryIO | list[BinaryIO] | None = None,
    bs_file: BinaryIO | list[BinaryIO] | None = None,
    combined_file: BinaryIO | list[BinaryIO] | None = None,
    company_profile: str = "",
    document_description: str = "",
    client_name: str = "",
    extra_files: BinaryIO | list[BinaryIO] | None = None,
) -> dict:
    """
    Run the full v1 workpaper pipeline from frontend uploads.

    Supports both old app.py calling style:
        run_workpaper_job(pl_file=..., bs_file=..., combined_file=...)

    And future multi-file style:
        run_workpaper_job(combined_file=[file1, file2, file3])
        run_workpaper_job(extra_files=[file1, file2, file3])

    Returns:
        {
            "status": "success" | "error",
            "output_path": Path | None,
            "output_name": str,
            "detected": {...},
            "review_count": int,
            "warnings": list[str],
            "uploaded_files": list[str],
            "error_message": str | None,
        }
    """
    result: dict = {
        "status": "error",
        "output_path": None,
        "output_name": "",
        "detected": {},
        "review_count": 0,
        "warnings": [],
        "uploaded_files": [],
        "error_message": None,
    }

    try:
        all_uploads: list[tuple[str, Any]] = []

        for idx, file in enumerate(_as_list(combined_file), start=1):
            all_uploads.append(("combined", file))

        for idx, file in enumerate(_as_list(pl_file), start=1):
            all_uploads.append(("pl", file))

        for idx, file in enumerate(_as_list(bs_file), start=1):
            all_uploads.append(("bs", file))

        for idx, file in enumerate(_as_list(extra_files), start=1):
            all_uploads.append(("extra", file))

        if not all_uploads:
            result["error_message"] = (
                "Please upload at least one Excel workbook. "
                "You can upload a combined workbook or separate P&L / Balance Sheet files."
            )
            return result

        # 1. Save uploads to frontend/uploads/job_timestamp/
        job_id = _timestamp()
        job_upload_dir = UPLOADS_DIR / f"job_{job_id}"
        job_upload_dir.mkdir(parents=True, exist_ok=True)

        saved_inputs: list[Path] = []
        for index, (prefix, uploaded_file) in enumerate(all_uploads, start=1):
            saved_inputs.append(
                _save_uploaded_file(
                    uploaded_file=uploaded_file,
                    dest_dir=job_upload_dir,
                    prefix=prefix,
                    index=index,
                )
            )

        # 2. Clean old Excel files from v1/data to avoid stale input conflicts
        _clear_excel_files_from_v1_data()

        # 3. Copy current uploads into v1/data
        copied_inputs = _copy_inputs_to_v1_data(saved_inputs)

        # 4. Configure backend output path and metadata
        output_name = _timestamped_output_name(client_name)
        output_path = DOWNLOADS_DIR / output_name
        _set_backend_config(
            output_path=output_path,
            company_profile=company_profile,
            document_description=document_description,
        )

        # 5. Run backend
        _raw_pl_df, _raw_bs_df, workpaper = _run_backend_pipeline()

        # 6. Return summary for Streamlit
        result.update(
            _build_result_summary(
                output_path=output_path,
                output_name=output_name,
                copied_inputs=copied_inputs,
                workpaper=workpaper,
            )
        )

    except Exception as exc:
        logger.exception("job_runner error")
        result["error_message"] = (
            f"{type(exc).__name__}: {exc}\n\n{traceback.format_exc()}"
        )

    return result