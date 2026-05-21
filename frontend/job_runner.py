# frontend/job_runner.py
"""
Bridge between Streamlit UI and v1 backend.

Stable design:
- Save uploaded Excel files into frontend/uploads/job_xxx/.
- Clear old Excel files from v1/data/.
- Copy uploaded Excel files into v1/data/.
- Run v1/main.py as a subprocess, same as the working backend terminal test.
- Find newest Excel output from v1/output/.
- Copy that output into frontend/downloads/ for Streamlit download.

This avoids calling backend internals directly and avoids tuple/reports mismatch.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import sys
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, BinaryIO


# ── Paths ─────────────────────────────────────────────────────────────────────
FRONTEND_DIR = Path(__file__).resolve().parent
ROOT_DIR = FRONTEND_DIR.parent
V1_DIR = ROOT_DIR / "v1"

UPLOADS_DIR = FRONTEND_DIR / "uploads"
DOWNLOADS_DIR = FRONTEND_DIR / "downloads"

V1_DATA_DIR = V1_DIR / "data"
V1_OUTPUT_DIR = V1_DIR / "output"
V1_MAIN_PATH = V1_DIR / "main.py"

UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
V1_DATA_DIR.mkdir(parents=True, exist_ok=True)
V1_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

logger = logging.getLogger(__name__)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _as_list(value: Any) -> list[Any]:
    """
    Streamlit uploader can return:
    - None
    - one UploadedFile
    - list[UploadedFile]
    """
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return list(value)
    return [value]


def _safe_filename(name: str, fallback: str = "uploaded.xlsx") -> str:
    name = name or fallback
    safe = "".join(c if c.isalnum() or c in " ._-()" else "_" for c in name).strip()
    return safe or fallback


def _safe_client_name(client_name: str) -> str:
    return "".join(
        c if c.isalnum() or c in "-_" else "_"
        for c in (client_name or "")
    ).strip("_")


def _save_uploaded_file(uploaded_file: BinaryIO, dest_dir: Path, index: int) -> Path:
    original_name = getattr(uploaded_file, "name", f"uploaded_{index}.xlsx")
    safe_name = _safe_filename(original_name, fallback=f"uploaded_{index}.xlsx")
    dest = dest_dir / f"{index:02d}_{safe_name}"

    try:
        uploaded_file.seek(0)
    except Exception:
        pass

    with open(dest, "wb") as f:
        f.write(uploaded_file.read())

    logger.info("Saved frontend upload: %s", dest)
    return dest


def _clear_excel_files(folder: Path) -> list[Path]:
    removed: list[Path] = []

    for path in folder.iterdir():
        if path.is_file() and path.suffix.lower() in {".xlsx", ".xls", ".xlsm"}:
            path.unlink()
            removed.append(path)
            logger.info("Removed old Excel file: %s", path)

    return removed


def _copy_inputs_to_v1_data(saved_inputs: list[Path]) -> list[Path]:
    copied: list[Path] = []

    for source in saved_inputs:
        dest = V1_DATA_DIR / source.name
        shutil.copy2(source, dest)
        copied.append(dest)
        logger.info("Copied upload into v1/data: %s", dest)

    return copied


def _latest_output_after(start_time: float) -> Path | None:
    candidates: list[Path] = []

    for path in V1_OUTPUT_DIR.glob("*.xlsx"):
        if path.is_file() and path.stat().st_mtime >= start_time:
            candidates.append(path)

    if not candidates:
        return None

    return max(candidates, key=lambda p: p.stat().st_mtime)


def _copy_backend_output_to_downloads(
    backend_output: Path,
    client_name: str = "",
) -> tuple[Path, str]:
    safe_client = _safe_client_name(client_name)
    prefix = f"{safe_client}_" if safe_client else ""
    output_name = f"{prefix}workpaper_{_timestamp()}.xlsx"

    frontend_output = DOWNLOADS_DIR / output_name
    shutil.copy2(backend_output, frontend_output)

    return frontend_output, output_name


def _extract_warnings(stdout: str, stderr: str) -> list[str]:
    text = f"{stdout}\n{stderr}"
    warnings: list[str] = []

    for line in text.splitlines():
        upper = line.upper()
        if "WARNING" in upper or "[WARNING]" in upper:
            warnings.append(line.strip())

    return warnings[:30]


def _detect_reports_from_log(stdout: str, stderr: str) -> dict[str, bool]:
    text = f"{stdout}\n{stderr}".lower()

    return {
        "P&L": (
            "profit_and_loss" in text
            or "profit and loss" in text
            or "p&l" in text
        ),
        "Balance Sheet": (
            "balance_sheet" in text
            or "balance sheet" in text
        ),
    }


def _run_v1_main() -> subprocess.CompletedProcess:
    if not V1_MAIN_PATH.exists():
        raise FileNotFoundError(f"Cannot find backend main.py at: {V1_MAIN_PATH}")

    return subprocess.run(
        [sys.executable, str(V1_MAIN_PATH)],
        cwd=str(V1_DIR),
        text=True,
        capture_output=True,
        check=False,
    )


def _build_error_result(
    base_result: dict,
    message: str,
    stdout: str = "",
    stderr: str = "",
) -> dict:
    full_log = f"{stdout}\n{stderr}".strip()

    if full_log:
        base_result["error_message"] = f"{message}\n\n{full_log}"
    else:
        base_result["error_message"] = message

    base_result["warnings"] = _extract_warnings(stdout, stderr)
    base_result["detected"] = _detect_reports_from_log(stdout, stderr)
    base_result["backend_log"] = full_log

    return base_result


# ── Public function called by app.py ──────────────────────────────────────────

def run_workpaper_job(
    extra_files: BinaryIO | list[BinaryIO] | None = None,
    pl_file: BinaryIO | list[BinaryIO] | None = None,
    bs_file: BinaryIO | list[BinaryIO] | None = None,
    combined_file: BinaryIO | list[BinaryIO] | None = None,
    company_profile: str = "",
    document_description: str = "",
    client_name: str = "",
) -> dict:
    """
    Run the working v1 backend from Streamlit uploads.

    Recommended app.py call:
        run_workpaper_job(extra_files=uploaded_files, ...)
    """
    result: dict = {
        "status": "error",
        "output_path": None,
        "output_name": "",
        "detected": {},
        "review_count": None,
        "warnings": [],
        "uploaded_files": [],
        "frontend_upload_paths": [],
        "backend_data_paths": [],
        "backend_output_path": None,
        "backend_command": "",
        "backend_log": "",
        "company_profile": company_profile or "",
        "document_description": document_description or "",
        "error_message": None,
    }

    try:
        uploads: list[Any] = []
        uploads.extend(_as_list(extra_files))
        uploads.extend(_as_list(combined_file))
        uploads.extend(_as_list(pl_file))
        uploads.extend(_as_list(bs_file))

        if not uploads:
            result["error_message"] = "Please upload at least one Excel workbook."
            return result

        # 1. Save frontend uploads into timestamped folder
        job_id = _timestamp()
        job_upload_dir = UPLOADS_DIR / f"job_{job_id}"
        job_upload_dir.mkdir(parents=True, exist_ok=True)

        saved_inputs = [
            _save_uploaded_file(uploaded_file, job_upload_dir, index)
            for index, uploaded_file in enumerate(uploads, start=1)
        ]

        result["uploaded_files"] = [path.name for path in saved_inputs]
        result["frontend_upload_paths"] = [str(path) for path in saved_inputs]

        # 2. Clear old backend Excel inputs
        _clear_excel_files(V1_DATA_DIR)

        # 3. Copy current uploads into v1/data
        copied_inputs = _copy_inputs_to_v1_data(saved_inputs)
        result["backend_data_paths"] = [str(path) for path in copied_inputs]

        # 4. Run backend exactly like Terminal
        start_time = datetime.now().timestamp()
        result["backend_command"] = f"{sys.executable} {V1_MAIN_PATH}"

        completed = _run_v1_main()

        stdout = completed.stdout or ""
        stderr = completed.stderr or ""
        full_log = f"{stdout}\n{stderr}".strip()

        result["backend_log"] = full_log
        result["warnings"] = _extract_warnings(stdout, stderr)
        result["detected"] = _detect_reports_from_log(stdout, stderr)

        if completed.returncode != 0:
            return _build_error_result(
                result,
                f"Backend exited with code {completed.returncode}.",
                stdout,
                stderr,
            )

        # 5. Find newest output generated by backend
        backend_output = _latest_output_after(start_time)

        if backend_output is None:
            return _build_error_result(
                result,
                "Backend completed, but no new Excel output was found in v1/output.",
                stdout,
                stderr,
            )

        result["backend_output_path"] = str(backend_output)

        # 6. Copy backend output into frontend/downloads
        frontend_output, output_name = _copy_backend_output_to_downloads(
            backend_output,
            client_name=client_name,
        )

        result.update(
            {
                "status": "success",
                "output_path": frontend_output,
                "output_name": output_name,
                "error_message": None,
            }
        )

        return result

    except Exception as exc:
        logger.exception("job_runner error")
        result["error_message"] = (
            f"{type(exc).__name__}: {exc}\n\n{traceback.format_exc()}"
        )
        return result