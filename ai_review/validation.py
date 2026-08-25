"""Strict validation for the provider-neutral AI review response."""

from __future__ import annotations

from collections.abc import Collection, Mapping
from typing import Any

from .models import AiReview, AiReviewFinding, ReviewSeverity


class AiReviewPayloadError(ValueError):
    """Raised when a provider response cannot safely be used as an AI review."""


AI_REVIEW_RESPONSE_SCHEMA: dict[str, Any] = {
    "name": "tax_workpaper_ai_review",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["status", "findings", "limitations"],
        "properties": {
            "status": {"type": "string", "enum": ["completed"]},
            "findings": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "severity",
                        "decision_id",
                        "evidence",
                        "missing_facts",
                        "recommended_review_action",
                    ],
                    "properties": {
                        "severity": {
                            "type": "string",
                            "enum": [item.value for item in ReviewSeverity],
                        },
                        "decision_id": {"type": "string", "minLength": 1},
                        "evidence": {
                            "type": "array",
                            "minItems": 1,
                            "items": {"type": "string", "minLength": 1},
                        },
                        "missing_facts": {
                            "type": "array",
                            "items": {"type": "string", "minLength": 1},
                        },
                        "recommended_review_action": {
                            "type": "string",
                            "minLength": 1,
                        },
                    },
                },
            },
            "limitations": {
                "type": "array",
                "items": {"type": "string", "minLength": 1},
            },
        },
    },
}

_RESPONSE_FIELDS = frozenset({"status", "findings", "limitations"})
_FINDING_FIELDS = frozenset(
    {
        "severity",
        "decision_id",
        "evidence",
        "missing_facts",
        "recommended_review_action",
    }
)


def _require_exact_fields(
    value: Mapping[str, Any],
    expected: Collection[str],
    location: str,
) -> None:
    actual = set(value)
    missing = set(expected).difference(actual)
    extra = actual.difference(expected)
    if missing or extra:
        details: list[str] = []
        if missing:
            details.append(f"missing={sorted(missing)}")
        if extra:
            details.append(f"extra={sorted(extra)}")
        raise AiReviewPayloadError(f"{location} has invalid fields: {', '.join(details)}")


def _require_string_list(value: Any, location: str, *, non_empty: bool) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise AiReviewPayloadError(f"{location} must be an array of strings")
    if non_empty and not value:
        raise AiReviewPayloadError(f"{location} must not be empty")

    cleaned: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            raise AiReviewPayloadError(f"{location}[{index}] must be a non-empty string")
        cleaned.append(item.strip())
    return tuple(cleaned)


def parse_ai_review(
    payload: Mapping[str, Any],
    *,
    decision_ids: Collection[str],
) -> AiReview:
    """Validate a provider payload and return an immutable `AiReview`.

    The provider is permitted to report only against decisions the deterministic
    pipeline supplied. An unknown decision ID is rejected rather than displayed.
    """

    if not isinstance(payload, Mapping):
        raise AiReviewPayloadError("AI review response must be an object")
    _require_exact_fields(payload, _RESPONSE_FIELDS, "AI review response")

    if payload["status"] != "completed":
        raise AiReviewPayloadError("AI review status must be 'completed'")
    if not isinstance(payload["findings"], list):
        raise AiReviewPayloadError("findings must be an array")

    known_decision_ids = set(decision_ids)
    findings: list[AiReviewFinding] = []
    for index, finding in enumerate(payload["findings"]):
        location = f"findings[{index}]"
        if not isinstance(finding, Mapping):
            raise AiReviewPayloadError(f"{location} must be an object")
        _require_exact_fields(finding, _FINDING_FIELDS, location)

        severity_value = finding["severity"]
        try:
            severity = ReviewSeverity(severity_value)
        except (TypeError, ValueError) as exc:
            allowed = ", ".join(item.value for item in ReviewSeverity)
            raise AiReviewPayloadError(f"{location}.severity must be one of: {allowed}") from exc

        decision_id = finding["decision_id"]
        if not isinstance(decision_id, str) or not decision_id.strip():
            raise AiReviewPayloadError(f"{location}.decision_id must be a non-empty string")
        if decision_id not in known_decision_ids:
            raise AiReviewPayloadError(
                f"{location}.decision_id does not belong to this workpaper"
            )

        action = finding["recommended_review_action"]
        if not isinstance(action, str) or not action.strip():
            raise AiReviewPayloadError(
                f"{location}.recommended_review_action must be a non-empty string"
            )

        findings.append(
            AiReviewFinding(
                severity=severity,
                decision_id=decision_id.strip(),
                evidence=_require_string_list(
                    finding["evidence"],
                    f"{location}.evidence",
                    non_empty=True,
                ),
                missing_facts=_require_string_list(
                    finding["missing_facts"],
                    f"{location}.missing_facts",
                    non_empty=False,
                ),
                recommended_review_action=action.strip(),
            )
        )

    limitations = _require_string_list(payload["limitations"], "limitations", non_empty=False)
    return AiReview(status="completed", findings=tuple(findings), limitations=limitations)
