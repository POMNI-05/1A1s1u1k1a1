"""Durable, local audit records for display-only AI review.

The audit file is deliberately a sidecar to the generated workbook.  It is not
an input to the deterministic calculation and cannot change a tax outcome.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from .models import DecisionTrace, WorkpaperResult
from .providers import (
    SHADOW_REVIEW_PROMPT_VERSION,
    ShadowReviewInput,
    build_shadow_review_input,
)
from .validation import AI_REVIEW_RESPONSE_SCHEMA


AI_REVIEW_AUDIT_SCHEMA_VERSION = "1.0"
AI_REVIEW_RESPONSE_SCHEMA_VERSION = "1.0"
ACCOUNTANT_DISPOSITION_STATUSES = frozenset(
    {"pending", "accepted", "rejected", "not_applicable"}
)


class AiReviewAuditError(ValueError):
    """Raised when an AI-review audit record is invalid or cannot be updated."""


def audit_path_for_workpaper(workbook_path: Path | str) -> Path:
    """Return the sidecar audit path for a generated workbook."""

    return Path(workbook_path).with_suffix(".ai_review_audit.json")


def _canonical_input_json(review_input: ShadowReviewInput) -> str:
    """Return stable JSON for the exact minimised evidence sent to a provider."""

    return json.dumps(
        {
            "income_year": review_input.income_year,
            "review_items": review_input.review_items,
            "decision_traces": review_input.decision_traces,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def shadow_review_input_sha256(
    workpaper_result: WorkpaperResult,
    decision_traces: Sequence[DecisionTrace],
) -> str:
    """Hash minimised review evidence without retaining a duplicate raw payload."""

    review_input = build_shadow_review_input(workpaper_result, decision_traces)
    return hashlib.sha256(_canonical_input_json(review_input).encode("utf-8")).hexdigest()


def build_ai_review_audit_record(
    *,
    workpaper_result: WorkpaperResult,
    provider_name: str,
    model: str,
    review_response: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Create a non-authoritative audit record for one workpaper review.

    The record keeps only schema-validated display findings and operational
    status.  It intentionally omits raw workbook content, source file paths,
    backend logs, prompt text, and API credentials.
    """

    response = dict(review_response or {})
    response_status = response.get("status", "skipped")
    if not isinstance(response_status, str) or not response_status.strip():
        raise AiReviewAuditError("AI review response status must be a non-empty string")

    findings = response.get("findings", [])
    limitations = response.get("limitations", [])
    if not isinstance(findings, list) or not isinstance(limitations, list):
        raise AiReviewAuditError("AI review findings and limitations must be lists")

    return {
        "audit_schema_version": AI_REVIEW_AUDIT_SCHEMA_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "workpaper": {
            "job_id": workpaper_result.job_id,
            "income_year": workpaper_result.income_year,
        },
        "provider": {
            "name": provider_name.strip() or "None",
            "model": model.strip(),
        },
        "review_contract": {
            "response_schema_name": AI_REVIEW_RESPONSE_SCHEMA["name"],
            "response_schema_version": AI_REVIEW_RESPONSE_SCHEMA_VERSION,
            "prompt_version": SHADOW_REVIEW_PROMPT_VERSION,
        },
        "input_sha256": shadow_review_input_sha256(
            workpaper_result,
            workpaper_result.decision_traces,
        ),
        "response": {
            "status": response_status.strip(),
            "findings": findings,
            "limitations": limitations,
        },
        "accountant_disposition": {
            "status": "pending",
            "reviewer": "",
            "note": "",
            "updated_at": None,
        },
    }


def write_ai_review_audit(record: Mapping[str, Any], path: Path | str) -> Path:
    """Atomically write an audit sidecar, avoiding a partially written record."""

    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    try:
        temporary.write_text(
            json.dumps(dict(record), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(destination)
    finally:
        if temporary.exists():
            temporary.unlink()
    return destination


def read_ai_review_audit(path: Path | str) -> dict[str, Any]:
    """Read the local audit sidecar and validate only fields required for use."""

    source = Path(path)
    try:
        data = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AiReviewAuditError(f"Could not read AI review audit: {exc}") from exc
    if not isinstance(data, dict):
        raise AiReviewAuditError("AI review audit must be a JSON object")
    if data.get("audit_schema_version") != AI_REVIEW_AUDIT_SCHEMA_VERSION:
        raise AiReviewAuditError("Unsupported AI review audit schema version")
    if not isinstance(data.get("accountant_disposition"), dict):
        raise AiReviewAuditError("AI review audit has no accountant disposition")
    return data


def update_accountant_disposition(
    path: Path | str,
    *,
    status: str,
    reviewer: str = "",
    note: str = "",
) -> dict[str, Any]:
    """Record an accountant decision without changing the AI finding itself."""

    if status not in ACCOUNTANT_DISPOSITION_STATUSES:
        choices = ", ".join(sorted(ACCOUNTANT_DISPOSITION_STATUSES))
        raise AiReviewAuditError(f"Unsupported accountant disposition; choose one of: {choices}")

    record = read_ai_review_audit(path)
    record["accountant_disposition"] = {
        "status": status,
        "reviewer": reviewer.strip(),
        "note": note.strip(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    write_ai_review_audit(record, path)
    return record
