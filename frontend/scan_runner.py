"""Frontend scan runner for the staged generator workflow."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, BinaryIO

try:
    from .job_runner import ROOT_DIR, _as_list, _safe_filename
except ImportError:  # Streamlit imports this module from frontend/ directly.
    from job_runner import ROOT_DIR, _as_list, _safe_filename  # type: ignore


FRONTEND_DIR = Path(__file__).resolve().parent
SCAN_JOBS_DIR = FRONTEND_DIR / "scan_jobs"
SCAN_JOBS_DIR.mkdir(parents=True, exist_ok=True)


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _save_uploaded_file(uploaded_file: BinaryIO, dest_dir: Path, index: int) -> Path:
    original_name = getattr(uploaded_file, "name", f"uploaded_{index}.xlsx")
    dest = dest_dir / f"{index:02d}_{_safe_filename(original_name)}"
    try:
        uploaded_file.seek(0)
    except Exception:
        pass
    with dest.open("wb") as handle:
        handle.write(uploaded_file.read())
    return dest


def run_scan_job(
    *,
    uploaded_files: BinaryIO | list[BinaryIO] | None,
    profile: dict[str, Any],
) -> dict[str, Any]:
    uploads = _as_list(uploaded_files)
    if not uploads:
        return {
            "status": "error",
            "error_message": "Please upload at least one Excel workbook before scanning.",
        }

    scan_id = f"{_timestamp()}_{uuid.uuid4().hex}"
    scan_root = SCAN_JOBS_DIR / scan_id
    input_dir = scan_root / "inputs"
    output_dir = scan_root / "output"
    input_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    saved_paths = [
        _save_uploaded_file(uploaded_file, input_dir, index)
        for index, uploaded_file in enumerate(uploads, start=1)
    ]
    source_hashes = {path.name: _sha256(path) for path in saved_paths}
    result_path = output_dir / "scan_result.json"

    env = os.environ.copy()
    env["TAX_SCAN_ID"] = scan_id
    env["TAX_DATA_DIR"] = str(input_dir)
    env["TAX_JOB_WORK_DIR"] = str(scan_root)
    env["TAX_SCAN_RESULT_PATH"] = str(result_path)
    env["TAX_SCAN_SOURCE_HASHES"] = json.dumps(source_hashes)

    completed = subprocess.run(
        [sys.executable, "-m", "v1.scan_workbooks"],
        cwd=str(ROOT_DIR),
        text=True,
        capture_output=True,
        check=False,
        env=env,
        timeout=180,
    )

    if result_path.exists():
        result = json.loads(result_path.read_text(encoding="utf-8"))
    else:
        result = {
            "status": "error",
            "scan_id": scan_id,
            "error_message": "Scan process did not write a result contract.",
            "detected_reports": [],
            "observations": [],
            "suggestions": [],
            "questions": [],
            "warnings": [],
            "source_file_hashes": source_hashes,
        }

    result.update(
        {
            "scan_root": str(scan_root),
            "input_dir": str(input_dir),
            "source_files": [str(path) for path in saved_paths],
            "profile": profile,
            "backend_log": f"{completed.stdout or ''}\n{completed.stderr or ''}".strip(),
        }
    )
    if completed.returncode != 0 and result.get("status") == "success":
        result["status"] = "error"
        result["error_message"] = "Scan process failed after writing a partial result."
    return result


def verify_scan_sources(scan_result: dict[str, Any]) -> tuple[bool, list[str]]:
    mismatches: list[str] = []
    for path_text in scan_result.get("source_files") or []:
        path = Path(path_text)
        expected = (scan_result.get("source_file_hashes") or {}).get(path.name)
        if not path.exists():
            mismatches.append(f"{path.name}: source file is missing")
            continue
        actual = _sha256(path)
        if expected and actual != expected:
            mismatches.append(f"{path.name}: source hash changed")
    return not mismatches, mismatches


def open_scan_source_files(scan_result: dict[str, Any]) -> list[BinaryIO]:
    return [Path(path_text).open("rb") for path_text in scan_result.get("source_files") or []]


def cleanup_scan(scan_result: dict[str, Any] | None) -> None:
    if not scan_result:
        return
    scan_root = scan_result.get("scan_root")
    if scan_root:
        shutil.rmtree(scan_root, ignore_errors=True)
