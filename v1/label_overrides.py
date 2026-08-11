# v1/label_overrides.py
"""
User/custom override layer for ITR labelling.

Design:
- itr_rules.py / itr_rules_2026.py remain the official/base rule engine.
- user_itr_overrides.json stores user-approved custom corrections.
- This module applies overrides after normal rule matching.
- Overrides affect the labelled DataFrame and therefore the generated workbook.
- Overrides do not mutate itr_rules.py directly.

Supported match types:
- exact: account name must equal account_pattern after normalisation
- contains: account_pattern must appear inside account name
- regex: account_pattern is treated as a regular expression

Optional filters:
- report_type
- section_pattern

Example override:
{
  "enabled": true,
  "name": "Consulting income to 6C",
  "report_type": "profit_and_loss",
  "match_type": "contains",
  "account_pattern": "consulting income",
  "section_pattern": "",
  "set": {
    "ITR Ref": "Inc - 6C",
    "ITR Label": "Other sales of goods and services",
    "Treatment": "financial_label_only",
    "Confidence": "high",
    "Review Note": "User override: ordinary service income.",
    "Label Reason": "User override applied after base rule matching."
  }
}
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_OVERRIDE_PATH = BASE_DIR / "user_itr_overrides.json"


OVERRIDE_AUDIT_COLUMNS = [
    "Override Applied",
    "Override Name",
    "Override Reason",
]


def _normalise_text(value: Any) -> str:
    text = str(value or "").strip().lower()

    if text in {"nan", "none"}:
        return ""

    text = text.replace("&", " and ")
    text = re.sub(r"[\u2010-\u2015\u2212\-_\/]+", " ", text)
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    return text


def _load_override_file(path: Path = DEFAULT_OVERRIDE_PATH) -> dict[str, Any]:
    if not path.exists():
        return {
            "version": 1,
            "description": "User/custom ITR labelling overrides.",
            "overrides": [],
        }

    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in override file: {path}") from exc

    if not isinstance(data, dict):
        raise ValueError(f"Override file must contain a JSON object: {path}")

    data.setdefault("version", 1)
    data.setdefault("overrides", [])

    if not isinstance(data["overrides"], list):
        raise ValueError("'overrides' must be a list in user_itr_overrides.json")

    return data


def load_overrides(path: Path = DEFAULT_OVERRIDE_PATH) -> list[dict[str, Any]]:
    data = _load_override_file(path)

    overrides: list[dict[str, Any]] = []

    for item in data.get("overrides", []):
        if not isinstance(item, dict):
            continue

        if item.get("enabled", True) is False:
            continue

        if not item.get("account_pattern"):
            continue

        if not isinstance(item.get("set", {}), dict):
            continue

        overrides.append(item)

    return overrides


def _match_pattern(value: str, pattern: str, match_type: str) -> bool:
    value_norm = _normalise_text(value)
    pattern_norm = _normalise_text(pattern)

    if not pattern_norm:
        return True

    match_type = str(match_type or "contains").strip().lower()

    if match_type == "exact":
        return value_norm == pattern_norm

    if match_type == "contains":
        return pattern_norm in value_norm

    if match_type == "regex":
        try:
            return re.search(pattern, value, flags=re.IGNORECASE) is not None
        except re.error:
            return False

    # Conservative fallback.
    return pattern_norm in value_norm


def override_matches_row(
    override: dict[str, Any],
    *,
    account_name: str,
    report_type: str,
    report_section: str = "",
) -> bool:
    wanted_report = str(override.get("report_type", "") or "").strip().lower()
    current_report = str(report_type or "").strip().lower()

    if wanted_report and wanted_report != current_report:
        return False

    match_type = str(override.get("match_type", "contains") or "contains")
    account_pattern = str(override.get("account_pattern", "") or "")
    section_pattern = str(override.get("section_pattern", "") or "")

    if not _match_pattern(account_name, account_pattern, match_type):
        return False

    if section_pattern and not _match_pattern(report_section, section_pattern, "contains"):
        return False

    return True


def apply_label_override(
    mapping: dict[str, Any],
    *,
    account_name: str,
    report_type: str,
    report_section: str = "",
    overrides: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Apply the first matching enabled override to one ITR mapping.

    First-match wins intentionally:
    - more specific overrides should be placed above broad overrides
    - this keeps behaviour predictable for the frontend/user
    """
    result = dict(mapping)

    result.setdefault("Override Applied", "")
    result.setdefault("Override Name", "")
    result.setdefault("Override Reason", "")

    active_overrides = overrides if overrides is not None else load_overrides()

    for override in active_overrides:
        if not override_matches_row(
            override,
            account_name=account_name,
            report_type=report_type,
            report_section=report_section,
        ):
            continue

        updates = override.get("set", {}) or {}

        for key, value in updates.items():
            result[str(key)] = value

        override_name = str(override.get("name", "") or "Unnamed override")
        result["Override Applied"] = "Yes"
        result["Override Name"] = override_name
        result["Override Reason"] = str(
            override.get("reason", "")
            or "User/custom override matched this account."
        )

        old_reason = str(mapping.get("Label Reason", "") or "").strip()
        new_reason = str(result.get("Label Reason", "") or "").strip()

        if old_reason and new_reason and old_reason != new_reason:
            result["Label Reason"] = f"{new_reason} Original base reason: {old_reason}"
        elif old_reason and not new_reason:
            result["Label Reason"] = f"User override applied. Original base reason: {old_reason}"

        return result

    return result


def validate_override_schema(override: dict[str, Any]) -> list[str]:
    """
    Lightweight validation for AI/frontend-created overrides.
    Return a list of human-readable errors.
    """
    errors: list[str] = []

    if not isinstance(override, dict):
        return ["Override must be a JSON object."]

    if not override.get("account_pattern"):
        errors.append("Missing account_pattern.")

    match_type = str(override.get("match_type", "contains") or "contains").lower()
    if match_type not in {"exact", "contains", "regex"}:
        errors.append("match_type must be one of: exact, contains, regex.")

    report_type = str(override.get("report_type", "") or "").lower()
    if report_type and report_type not in {
        "profit_and_loss",
        "balance_sheet",
        "trial_balance",
        "general_ledger",
        "unknown",
    }:
        errors.append("report_type is not recognised.")

    updates = override.get("set")
    if not isinstance(updates, dict) or not updates:
        errors.append("set must be a non-empty object of label fields to update.")

    if match_type == "regex":
        try:
            re.compile(str(override.get("account_pattern", "")))
        except re.error as exc:
            errors.append(f"Invalid regex account_pattern: {exc}")

    return errors