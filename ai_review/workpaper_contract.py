"""Versioned JSON contracts for the isolated workpaper backend process."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .models import (
    DecisionTrace,
    ReviewItem,
    ReviewSeverity,
    WorkpaperRequest,
    WorkpaperResult,
    WorkpaperStatus,
)

WORKPAPER_CONTRACT_VERSION = "1.0"


class WorkpaperContractError(ValueError):
    """Raised when an inter-process workpaper request or result is unsafe."""


_REQUEST_FIELDS = frozenset(
    {
        "schema_version",
        "job_id",
        "income_year",
        "work_dir",
        "input_dir",
        "input_paths",
        "output_path",
        "log_dir",
        "job_options",
    }
)
_RESULT_FIELDS = frozenset(
    {
        "schema_version",
        "job_id",
        "income_year",
        "status",
        "output_path",
        "warnings",
        "review_items",
        "decision_traces",
        "metadata",
        "error_code",
        "error_message",
    }
)


def _require_exact_fields(payload: Mapping[str, Any], expected: frozenset[str], name: str) -> None:
    missing = expected.difference(payload)
    extra = set(payload).difference(expected)
    if missing or extra:
        detail = []
        if missing:
            detail.append(f"missing={sorted(missing)}")
        if extra:
            detail.append(f"extra={sorted(extra)}")
        raise WorkpaperContractError(f"{name} has invalid fields: {', '.join(detail)}")


def _require_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WorkpaperContractError(f"{field} must be a non-empty string")
    return value.strip()


def _require_text_list(value: Any, field: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise WorkpaperContractError(f"{field} must be a non-empty array of strings")
    return tuple(_require_text(item, f"{field}[{index}]") for index, item in enumerate(value))


def request_from_dict(payload: Mapping[str, Any]) -> WorkpaperRequest:
    """Validate and parse a workpaper request payload."""

    if not isinstance(payload, Mapping):
        raise WorkpaperContractError("Workpaper request must be an object")
    _require_exact_fields(payload, _REQUEST_FIELDS, "Workpaper request")
    if payload["schema_version"] != WORKPAPER_CONTRACT_VERSION:
        raise WorkpaperContractError("Unsupported workpaper request schema_version")
    if not isinstance(payload["job_options"], dict):
        raise WorkpaperContractError("job_options must be an object")

    request = WorkpaperRequest(
        job_id=_require_text(payload["job_id"], "job_id"),
        income_year=_require_text(payload["income_year"], "income_year"),
        work_dir=_require_text(payload["work_dir"], "work_dir"),
        input_dir=_require_text(payload["input_dir"], "input_dir"),
        input_paths=_require_text_list(payload["input_paths"], "input_paths"),
        output_path=_require_text(payload["output_path"], "output_path"),
        log_dir=_require_text(payload["log_dir"], "log_dir"),
        job_options=dict(payload["job_options"]),
    )
    if request.job_options.get("ato_policy_year") != request.income_year:
        raise WorkpaperContractError("income_year must match job_options.ato_policy_year")
    _validate_owned_paths(request)
    return request


def request_to_dict(request: WorkpaperRequest) -> dict[str, Any]:
    """Serialize a request using the current contract version."""

    return {
        "schema_version": WORKPAPER_CONTRACT_VERSION,
        "job_id": request.job_id,
        "income_year": request.income_year,
        "work_dir": request.work_dir,
        "input_dir": request.input_dir,
        "input_paths": list(request.input_paths),
        "output_path": request.output_path,
        "log_dir": request.log_dir,
        "job_options": request.job_options,
    }


def _validate_owned_paths(request: WorkpaperRequest) -> None:
    work_dir = Path(request.work_dir).resolve()
    candidates = [
        ("input_dir", Path(request.input_dir)),
        ("output_path", Path(request.output_path)),
        ("log_dir", Path(request.log_dir)),
        *(("input_paths", Path(path)) for path in request.input_paths),
    ]
    for field, candidate in candidates:
        try:
            candidate.resolve().relative_to(work_dir)
        except ValueError as exc:
            raise WorkpaperContractError(f"{field} must be inside work_dir") from exc


def result_to_dict(result: WorkpaperResult) -> dict[str, Any]:
    """Serialize a typed backend result without exposing Python objects."""

    return {
        "schema_version": WORKPAPER_CONTRACT_VERSION,
        "job_id": result.job_id,
        "income_year": result.income_year,
        "status": result.status.value,
        "output_path": result.output_path,
        "warnings": list(result.warnings),
        "review_items": [_review_item_to_dict(item) for item in result.review_items],
        "decision_traces": [asdict(trace) for trace in result.decision_traces],
        "metadata": result.metadata,
        "error_code": result.error_code,
        "error_message": result.error_message,
    }


def result_from_dict(payload: Mapping[str, Any]) -> WorkpaperResult:
    """Validate and parse a backend result payload."""

    if not isinstance(payload, Mapping):
        raise WorkpaperContractError("Workpaper result must be an object")
    _require_exact_fields(payload, _RESULT_FIELDS, "Workpaper result")
    if payload["schema_version"] != WORKPAPER_CONTRACT_VERSION:
        raise WorkpaperContractError("Unsupported workpaper result schema_version")

    try:
        status = WorkpaperStatus(payload["status"])
    except (TypeError, ValueError) as exc:
        raise WorkpaperContractError("Workpaper result has an invalid status") from exc

    output_path = payload["output_path"]
    if output_path is not None and not isinstance(output_path, str):
        raise WorkpaperContractError("output_path must be a string or null")
    warnings = _optional_text_list(payload["warnings"], "warnings")
    review_items = tuple(
        _review_item_from_dict(item) for item in _require_list(payload, "review_items")
    )
    traces = tuple(
        _decision_trace_from_dict(item)
        for item in _require_list(payload, "decision_traces")
    )
    metadata_value = payload["metadata"]
    if not isinstance(metadata_value, dict) or not all(
        isinstance(key, str) and isinstance(value, str) for key, value in metadata_value.items()
    ):
        raise WorkpaperContractError("metadata must be an object of strings")

    return WorkpaperResult(
        job_id=_require_text(payload["job_id"], "job_id"),
        income_year=_require_text(payload["income_year"], "income_year"),
        status=status,
        output_path=output_path,
        warnings=warnings,
        review_items=review_items,
        decision_traces=traces,
        metadata=dict(metadata_value),
        error_code=_optional_text(payload["error_code"]),
        error_message=_optional_text(payload["error_message"]),
    )


def _require_list(payload: Mapping[str, Any], field: str) -> list[Any]:
    value = payload[field]
    if not isinstance(value, list):
        raise WorkpaperContractError(f"{field} must be an array")
    return value


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    return _require_text(value, "optional text")


def _optional_text_list(value: Any, field: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise WorkpaperContractError(f"{field} must be an array of strings")
    return tuple(_require_text(item, f"{field}[{index}]") for index, item in enumerate(value))


def _review_item_to_dict(item: ReviewItem) -> dict[str, Any]:
    return {
        "review_id": item.review_id,
        "decision_id": item.decision_id,
        "severity": item.severity.value,
        "title": item.title,
        "evidence": list(item.evidence),
        "required_action": item.required_action,
    }


def _review_item_from_dict(payload: Any) -> ReviewItem:
    if not isinstance(payload, dict):
        raise WorkpaperContractError("review_items entries must be objects")
    expected = {"review_id", "decision_id", "severity", "title", "evidence", "required_action"}
    _require_exact_fields(payload, frozenset(expected), "review_items entry")
    try:
        severity = ReviewSeverity(payload["severity"])
    except (TypeError, ValueError) as exc:
        raise WorkpaperContractError("review_items entry has invalid severity") from exc
    decision_id = payload["decision_id"]
    if decision_id is not None and not isinstance(decision_id, str):
        raise WorkpaperContractError("review_items decision_id must be a string or null")
    return ReviewItem(
        review_id=_require_text(payload["review_id"], "review_id"),
        decision_id=decision_id,
        severity=severity,
        title=_require_text(payload["title"], "title"),
        evidence=_optional_text_list(payload["evidence"], "review_items evidence"),
        required_action=_require_text(payload["required_action"], "required_action"),
    )


def _decision_trace_from_dict(payload: Any) -> DecisionTrace:
    if not isinstance(payload, dict):
        raise WorkpaperContractError("decision_traces entries must be objects")
    expected = set(DecisionTrace.__dataclass_fields__)
    _require_exact_fields(payload, frozenset(expected), "decision_traces entry")
    source_row = payload["source_row"]
    if source_row is not None and not isinstance(source_row, int):
        raise WorkpaperContractError("decision trace source_row must be an integer or null")
    return DecisionTrace(
        decision_id=_require_text(payload["decision_id"], "decision_id"),
        account_name=_require_text(payload["account_name"], "account_name"),
        report_type=_require_text(payload["report_type"], "report_type"),
        source_row=source_row,
        income_year=_require_text(payload["income_year"], "income_year"),
        rule_pack=_require_text(payload["rule_pack"], "rule_pack"),
        itr_ref=_require_text(payload["itr_ref"], "itr_ref"),
        itr_label=_require_text(payload["itr_label"], "itr_label"),
        treatment=_require_text(payload["treatment"], "treatment"),
        confidence=_require_text(payload["confidence"], "confidence"),
        review_required=payload["review_required"] is True,
        rule_id=_optional_text(payload["rule_id"]),
        matched_pattern=_optional_text(payload["matched_pattern"]),
        matched_text=_optional_text(payload["matched_text"]),
        source_references=_optional_text_list(
            payload["source_references"],
            "decision trace source_references",
        ),
        override_id=_optional_text(payload["override_id"]),
        override_reason=_optional_text(payload["override_reason"]),
    )


def write_workpaper_request(request: WorkpaperRequest, path: Path) -> None:
    _write_json(path, request_to_dict(request))


def read_workpaper_request(path: Path) -> WorkpaperRequest:
    return request_from_dict(_read_json(path, "Workpaper request"))


def write_workpaper_result(result: WorkpaperResult, path: Path) -> None:
    _write_json(path, result_to_dict(result))


def read_workpaper_result(path: Path) -> WorkpaperResult:
    return result_from_dict(_read_json(path, "Workpaper result"))


def _read_json(path: Path, name: str) -> Mapping[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise WorkpaperContractError(f"Unable to read {name}: {path}") from exc
    if not isinstance(payload, dict):
        raise WorkpaperContractError(f"{name} must be an object")
    return payload


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(f"{path.suffix}.tmp")
    temp_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    temp_path.replace(path)
