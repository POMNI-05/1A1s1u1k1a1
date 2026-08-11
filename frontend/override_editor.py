# frontend/override_editor.py
"""
Frontend helper for reading/writing backend user ITR overrides.

This file lets Streamlit:
- read v1/user_itr_overrides.json
- append a new user-approved override
- validate basic override shape before saving

Important:
- This does not edit itr_rules.py.
- It only edits user_itr_overrides.json.
"""

from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any


FRONTEND_DIR = Path(__file__).resolve().parent
ROOT_DIR = FRONTEND_DIR.parent
V1_DIR = ROOT_DIR / "v1"

OVERRIDE_FILE = V1_DIR / "user_itr_overrides.json"
_OVERRIDE_LOCK = threading.RLock()


DEFAULT_OVERRIDE_DOC = {
    "version": 1,
    "description": (
        "User/custom ITR labelling overrides. These are applied after base "
        "itr_rules matching and before workbook output."
    ),
    "overrides": [],
}


VALID_REPORT_TYPES = {
    "profit_and_loss",
    "balance_sheet",
    "trial_balance",
    "general_ledger",
    "unknown",
}

VALID_MATCH_TYPES = {"exact", "contains", "regex"}


def load_override_doc(path: Path = OVERRIDE_FILE) -> dict[str, Any]:
    if not path.exists():
        return dict(DEFAULT_OVERRIDE_DOC)

    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError:
        return dict(DEFAULT_OVERRIDE_DOC)

    if not isinstance(data, dict):
        return dict(DEFAULT_OVERRIDE_DOC)

    data.setdefault("version", 1)
    data.setdefault("description", DEFAULT_OVERRIDE_DOC["description"])
    data.setdefault("overrides", [])

    if not isinstance(data["overrides"], list):
        data["overrides"] = []

    return data


def save_override_doc(data: dict[str, Any], path: Path = OVERRIDE_FILE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def validate_override(override: dict[str, Any]) -> list[str]:
    errors: list[str] = []

    if not isinstance(override, dict):
        return ["Override must be a dictionary/object."]

    report_type = str(override.get("report_type", "") or "").strip()
    match_type = str(override.get("match_type", "") or "").strip()

    if report_type not in VALID_REPORT_TYPES:
        errors.append(
            f"report_type must be one of: {', '.join(sorted(VALID_REPORT_TYPES))}"
        )

    if match_type not in VALID_MATCH_TYPES:
        errors.append(
            f"match_type must be one of: {', '.join(sorted(VALID_MATCH_TYPES))}"
        )

    if not str(override.get("account_pattern", "") or "").strip():
        errors.append("account_pattern is required.")

    updates = override.get("set")
    if not isinstance(updates, dict) or not updates:
        errors.append("set must be a non-empty object/dictionary.")

    if isinstance(updates, dict):
        if not updates.get("ITR Ref"):
            errors.append("set.ITR Ref is required.")
        if not updates.get("ITR Label"):
            errors.append("set.ITR Label is required.")

    return errors


def build_override_from_form(
    *,
    name: str,
    report_type: str,
    account_pattern: str,
    match_type: str,
    itr_ref: str,
    itr_label: str,
    treatment: str,
    confidence: str,
    review_note: str,
    reason: str,
    section_pattern: str = "",
) -> dict[str, Any]:
    now = datetime.now().isoformat(timespec="seconds")

    return {
        "enabled": True,
        "name": name.strip() or f"User override {now}",
        "report_type": report_type,
        "match_type": match_type,
        "account_pattern": account_pattern.strip(),
        "section_pattern": section_pattern.strip(),
        "reason": reason.strip() or "User-approved override from frontend.",
        "created_at": now,
        "set": {
            "ITR Ref": itr_ref.strip(),
            "ITR Label": itr_label.strip(),
            "Treatment": treatment.strip(),
            "Confidence": confidence.strip(),
            "Review Note": review_note.strip(),
            "Label Reason": (
                "User override applied after base ITR rule matching. "
                + (reason.strip() or "")
            ).strip(),
        },
    }


def append_override(override: dict[str, Any], path: Path = OVERRIDE_FILE) -> dict[str, Any]:
    errors = validate_override(override)

    if errors:
        raise ValueError("; ".join(errors))

    with _OVERRIDE_LOCK:
        data = load_override_doc(path)
        data["overrides"].append(override)
        save_override_doc(data, path)

    return data
