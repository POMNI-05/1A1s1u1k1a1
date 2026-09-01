# frontend/job_runner.py
"""
Bridge between Streamlit UI and v1 backend.

Stable design:
- Give every request its own UUID-scoped inputs, output, logs and config.
- Run the backend package as an isolated subprocess.
- Pass a versioned request/result contract across the subprocess boundary.
- Optionally run a schema-constrained, display-only AI review.
- Copy the owned output into a session-scoped download history.
- Remove transient job files by default.

This avoids calling backend internals directly and avoids tuple/reports mismatch.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import traceback
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, BinaryIO

from ai_review import (
    WorkpaperRequest,
    WorkpaperStatus,
    audit_path_for_workpaper,
    build_ai_review_audit_record,
    read_workpaper_result,
    write_ai_review_audit,
    write_workpaper_request,
)
from tax_calculators.registry import SUPPORTED_YEARS
from tax_calculators.validation import CalculatorError

try:
    from .ai_shadow_review import run_ai_shadow_review as _run_ai_shadow_review
    from .job_options import (
        DEFAULT_REQUESTED_TABLES,
        base_rate_assessment_is_confirmed as _base_rate_assessment_is_confirmed,
        build_base_rate_entity_assessment,
        build_job_options as _build_job_options,
        normalise_policy_year as _normalise_policy_year,
        normalise_requested_tables as _normalise_requested_tables,
        normalise_reviewed_tax_depreciation as _normalise_reviewed_tax_depreciation,
    )
except ImportError:  # Streamlit imports this module from frontend/ directly.
    from ai_shadow_review import run_ai_shadow_review as _run_ai_shadow_review
    from job_options import (
        DEFAULT_REQUESTED_TABLES,
        base_rate_assessment_is_confirmed as _base_rate_assessment_is_confirmed,
        build_base_rate_entity_assessment,
        build_job_options as _build_job_options,
        normalise_policy_year as _normalise_policy_year,
        normalise_requested_tables as _normalise_requested_tables,
        normalise_reviewed_tax_depreciation as _normalise_reviewed_tax_depreciation,
    )


# ── Paths ─────────────────────────────────────────────────────────────────────

FRONTEND_DIR = Path(__file__).resolve().parent
ROOT_DIR = FRONTEND_DIR.parent
V1_DIR = ROOT_DIR / "v1"

UPLOADS_DIR = FRONTEND_DIR / "uploads"
DOWNLOADS_DIR = FRONTEND_DIR / "downloads"
JOBS_DIR = FRONTEND_DIR / "jobs"

V1_MAIN_PATH = V1_DIR / "main.py"

UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
JOBS_DIR.mkdir(parents=True, exist_ok=True)

logger = logging.getLogger(__name__)


# ── Constants ─────────────────────────────────────────────────────────────────

DEFAULT_BACKEND_TIMEOUT_SECONDS = 180
MIN_BACKEND_TIMEOUT_SECONDS = 30
MAX_BACKEND_TIMEOUT_SECONDS = 1800

# ── Basic helpers ─────────────────────────────────────────────────────────────

def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _backend_timeout_seconds() -> int:
    """Return a bounded backend timeout, allowing an environment override."""

    raw_value = os.environ.get(
        "TAX_BACKEND_TIMEOUT_SECONDS",
        str(DEFAULT_BACKEND_TIMEOUT_SECONDS),
    )
    try:
        timeout = int(raw_value)
    except (TypeError, ValueError):
        return DEFAULT_BACKEND_TIMEOUT_SECONDS
    return min(max(timeout, MIN_BACKEND_TIMEOUT_SECONDS), MAX_BACKEND_TIMEOUT_SECONDS)


def _timeout_output_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


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
    safe = "".join(
        c if c.isalnum() or c in " ._-()" else "_"
        for c in name
    ).strip()

    return safe or fallback


def _safe_client_name(client_name: str) -> str:
    safe = "".join(
        c if c.isalnum() or c in "-_" else "_"
        for c in (client_name or "")
    ).strip("_")

    return safe


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


def _copy_backend_output_to_downloads(
    backend_output: Path,
    client_name: str = "",
    history_owner_id: str = "local",
) -> tuple[Path, str]:
    safe_client = _safe_client_name(client_name)
    prefix = f"{safe_client}_" if safe_client else ""
    output_name = f"{prefix}workpaper_{_timestamp()}.xlsx"

    safe_owner = _safe_client_name(history_owner_id) or "local"
    owner_download_dir = DOWNLOADS_DIR / safe_owner
    owner_download_dir.mkdir(parents=True, exist_ok=True)
    frontend_output = owner_download_dir / output_name
    shutil.copy2(backend_output, frontend_output)

    logger.info("Copied backend output to frontend downloads: %s", frontend_output)
    return frontend_output, output_name


def _extract_warnings(stdout: str, stderr: str) -> list[str]:
    text = f"{stdout}\n{stderr}"
    warnings: list[str] = []

    for line in text.splitlines():
        upper = line.upper()

        if "WARNING" in upper or "[WARNING]" in upper:
            stripped = line.strip()
            if stripped:
                warnings.append(stripped)

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


# ── Backend subprocess ────────────────────────────────────────────────────────

def _run_v1_main(
    *,
    request_path: Path,
    result_path: Path,
) -> subprocess.CompletedProcess:
    if not V1_MAIN_PATH.exists():
        raise FileNotFoundError(f"Cannot find backend main.py at: {V1_MAIN_PATH}")

    env = os.environ.copy()

    env["TAX_WORKPAPER_REQUEST_PATH"] = str(request_path)
    env["TAX_WORKPAPER_RESULT_PATH"] = str(result_path)

    return subprocess.run(
        [sys.executable, "-m", "v1.main"],
        cwd=str(ROOT_DIR),
        text=True,
        capture_output=True,
        check=False,
        env=env,
        timeout=_backend_timeout_seconds(),
    )


# ── Error helper ──────────────────────────────────────────────────────────────

def _build_error_result(
    base_result: dict[str, Any],
    message: str,
    stdout: str = "",
    stderr: str = "",
) -> dict[str, Any]:
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
    ato_policy_year: str = "2026",
    requested_tables: dict[str, bool] | None = None,
    reviewer_notes: str = "",
    run_ai_face_check: bool = False,
    company_tax_rate_category: str = "review_required",
    base_rate_entity_assessment: dict[str, Any] | None = None,
    reviewed_tax_depreciation: float | int | str | None = None,
    tax_depreciation_approved_for_posting: bool = False,
    history_owner_id: str = "local",
    ai_provider: str = "None",
    ai_model: str = "",
    ai_api_key: str = "",
    retain_job_files: bool = False,
) -> dict[str, Any]:
    """
    Run the working v1 backend from Streamlit uploads.

    Recommended app.py call:
        run_workpaper_job(
            extra_files=uploaded_files,
            company_profile=company_profile,
            document_description=document_description,
            client_name=client_name,
            ato_policy_year=ato_policy_year,
            requested_tables=requested_tables,
            reviewer_notes=reviewer_notes,
            run_ai_face_check=run_ai_face_check,
        )
    """
    result: dict[str, Any] = {
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
        "client_name": client_name or "",
        "job_options": {},
        "job_config_path": "",
        "workpaper_request_path": "",
        "workpaper_result_path": "",
        "workpaper_result": None,
        "ai_face_check": None,
        "ai_review_audit_path": "",
        "error_code": None,
        "selected_income_year": "",
        "supported_income_years": list(SUPPORTED_YEARS),
        "error_message": None,
        "job_id": "",
        "job_cleaned_up": False,
    }

    job_root: Path | None = None

    try:
        # 0. Build frontend-selected job options.
        try:
            job_options = _build_job_options(
                ato_policy_year=ato_policy_year,
                requested_tables=requested_tables,
                reviewer_notes=reviewer_notes,
                company_profile=company_profile,
                document_description=document_description,
                client_name=client_name,
                company_tax_rate_category=company_tax_rate_category,
                base_rate_entity_assessment=base_rate_entity_assessment,
                reviewed_tax_depreciation=reviewed_tax_depreciation,
                tax_depreciation_approved_for_posting=tax_depreciation_approved_for_posting,
                retain_job_files=retain_job_files,
            )
        except CalculatorError as exc:
            # Do not let an invalid year become a generic traceback.  The UI
            # can now tell the user exactly what to change before any upload is
            # written or backend process is started.
            result.update(
                {
                    "error_code": "unsupported_income_year",
                    "selected_income_year": str(ato_policy_year),
                    "error_message": str(exc),
                }
            )
            return result

        result["job_options"] = job_options

        uploads: list[Any] = []
        uploads.extend(_as_list(extra_files))
        uploads.extend(_as_list(combined_file))
        uploads.extend(_as_list(pl_file))
        uploads.extend(_as_list(bs_file))

        if not uploads:
            result["error_message"] = "Please upload at least one Excel workbook."
            return result

        # 1. Save frontend uploads into timestamped folder.
        job_id = f"{_timestamp()}_{uuid.uuid4().hex}"
        result["job_id"] = job_id
        job_root = JOBS_DIR / job_id
        job_upload_dir = job_root / "inputs"
        job_output_dir = job_root / "output"
        job_log_dir = job_root / "logs"
        request_path = job_root / "request.json"
        result_path = job_root / "result.json"
        backend_output = job_output_dir / "tax_workpaper.xlsx"
        job_upload_dir.mkdir(parents=True, exist_ok=True)
        job_output_dir.mkdir(parents=True, exist_ok=True)
        job_log_dir.mkdir(parents=True, exist_ok=True)

        saved_inputs = [
            _save_uploaded_file(uploaded_file, job_upload_dir, index)
            for index, uploaded_file in enumerate(uploads, start=1)
        ]

        result["uploaded_files"] = [path.name for path in saved_inputs]
        result["frontend_upload_paths"] = [str(path) for path in saved_inputs]

        # Inputs already live in this job's isolated backend data directory.
        result["backend_data_paths"] = [str(path) for path in saved_inputs]

        # 3b. Write the explicit backend request contract.
        request = WorkpaperRequest(
            job_id=job_id,
            income_year=job_options["ato_policy_year"],
            work_dir=str(job_root),
            input_dir=str(job_upload_dir),
            input_paths=tuple(str(path) for path in saved_inputs),
            output_path=str(backend_output),
            log_dir=str(job_log_dir),
            job_options=job_options,
        )
        write_workpaper_request(request, request_path)
        result["workpaper_request_path"] = str(request_path)

        # 4. Run the backend package with this job's isolated paths.
        result["backend_command"] = f"{sys.executable} -m v1.main"

        try:
            completed = _run_v1_main(
                request_path=request_path,
                result_path=result_path,
            )
        except subprocess.TimeoutExpired as exc:
            return _build_error_result(
                result,
                f"Backend timed out after {exc.timeout} seconds. No output was published.",
                _timeout_output_text(exc.stdout),
                _timeout_output_text(exc.stderr),
            )

        stdout = completed.stdout or ""
        stderr = completed.stderr or ""
        full_log = f"{stdout}\n{stderr}".strip()

        result["backend_log"] = full_log
        result["warnings"] = _extract_warnings(stdout, stderr)
        result["detected"] = _detect_reports_from_log(stdout, stderr)

        if not result_path.exists():
            return _build_error_result(
                result,
                (
                    "Backend completed, but this job's result contract was not found."
                    if completed.returncode == 0
                    else f"Backend exited with code {completed.returncode} before writing its result contract."
                ),
                stdout,
                stderr,
            )

        try:
            workpaper_result = read_workpaper_result(result_path)
        except Exception as exc:
            return _build_error_result(
                result,
                f"Backend result contract was invalid: {type(exc).__name__}: {exc}",
                stdout,
                stderr,
            )

        # v1 writes its typed failure result before returning a non-zero exit
        # code. Read it first so the UI can render an intentional safety stop
        # (such as CELL-002) rather than a generic subprocess failure.
        result["workpaper_result_path"] = str(result_path)
        result["workpaper_result"] = {
            "status": workpaper_result.status.value,
            "income_year": workpaper_result.income_year,
            "review_item_count": len(workpaper_result.review_items),
            "decision_trace_count": len(workpaper_result.decision_traces),
        }
        if workpaper_result.status != WorkpaperStatus.COMPLETED:
            result["error_code"] = workpaper_result.error_code
            result["selected_income_year"] = workpaper_result.income_year
            return _build_error_result(
                result,
                workpaper_result.error_message or "Backend reported an unsuccessful workpaper run.",
                stdout,
                stderr,
            )

        if completed.returncode != 0:
            return _build_error_result(
                result,
                f"Backend exited with code {completed.returncode}.",
                stdout,
                stderr,
            )

        # 5. Use the output owned by this job only.
        if not backend_output.exists():
            return _build_error_result(
                result,
                "Backend completed, but this job's Excel output was not found.",
                stdout,
                stderr,
            )

        result["backend_output_path"] = str(backend_output)

        # 5b. Optional schema-constrained, display-only AI review.
        if run_ai_face_check:
            result["ai_face_check"] = _run_ai_shadow_review(
                workpaper_result=workpaper_result,
                ai_provider=ai_provider,
                api_key=ai_api_key,
                model=ai_model,
            )
        else:
            result["ai_face_check"] = {
                "status": "skipped",
                "summary": "AI shadow review was not selected.",
            }

        # 6. Copy backend output into frontend/downloads.
        frontend_output, output_name = _copy_backend_output_to_downloads(
            backend_output,
            client_name=client_name,
            history_owner_id=history_owner_id,
        )

        # Keep an immutable review response plus a separately editable
        # accountant disposition beside the final workbook.  This sidecar is
        # not read by the backend and can never influence the tax outcome.
        audit_path = audit_path_for_workpaper(frontend_output)
        audit_record = build_ai_review_audit_record(
            workpaper_result=workpaper_result,
            provider_name=ai_provider if run_ai_face_check else "None",
            model=ai_model if run_ai_face_check else "",
            review_response=result["ai_face_check"],
        )
        write_ai_review_audit(audit_record, audit_path)

        result.update(
            {
                "status": "success",
                "output_path": frontend_output,
                "output_name": output_name,
                "ai_review_audit_path": str(audit_path),
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

    finally:
        if job_root is not None and job_root.exists() and not retain_job_files:
            try:
                shutil.rmtree(job_root)
                result["job_cleaned_up"] = True
            except Exception:
                logger.exception("Could not clean isolated job directory: %s", job_root)
