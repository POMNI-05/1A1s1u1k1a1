# v1/ato_policy.py
"""
Year-specific ATO policy layer.

Keep itr_metadata.py as the base/default metadata.
Use this file only for income-year overrides or review notes.

Important:
- This file should not contain account-name matching rules.
- This file should not silently create tax adjustments.
- It should help validate which labels/rates/thresholds apply for a chosen year.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

try:
    from .itr_metadata import ITEM_7_LABELS
except ImportError:  # Direct-script compatibility.
    from itr_metadata import ITEM_7_LABELS

from tax_calculators.registry import SUPPORTED_YEARS, get_year_source


BASE_POLICY_YEAR = "2025"


def _number(section: dict[str, Any], key: str) -> float | None:
    value = section.get(key)
    return None if value is None else float(value)


def _policy_from_source(income_year: str) -> dict[str, Any]:
    """Adapt the validated rule registry to the legacy v1 policy interface."""

    source = get_year_source(income_year)
    company = source["company_tax"]
    instant = source["instant_asset_writeoff"]
    rd = source["rd_tax_incentive"]

    notes = {
        "2024": "Pre-2025 comparison year. Review temporary incentive labels before use.",
        "2025": "Company tax return 2025 structure and enacted 2024-25 calculation rules.",
        "2026": "Company tax return 2026 structure and enacted 2025-26 calculation rules; sensitive treatments still require accountant review.",
    }
    label_overrides: dict[str, dict[str, Any]] = {}
    if income_year == "2024":
        label_overrides = {
            "7J_TRAINING": {"active": True, "removed_in": None},
            "7K": {
                "active": True,
                "removed_in": None,
                "direction": "subtract",
            },
            "7Y": {"active": False, "introduced_in": "2025"},
        }

    return {
        "notes": [notes[income_year]],
        "tax_rates": {
            "base_rate_entity": _number(company, "base_rate_entity_rate"),
            "general": _number(company, "general_rate"),
        },
        # These are premiums added to the applicable company rate, not flat
        # R&D offset rates. Non-refundable claims also require intensity tiers.
        "rd_offset_rates": {
            "refundable_premium": _number(rd, "refundable_premium"),
            "non_refundable_lower_premium": _number(
                rd, "non_refundable_lower_premium"
            ),
            "non_refundable_upper_premium": _number(
                rd, "non_refundable_upper_premium"
            ),
            "intensity_threshold": _number(
                rd, "non_refundable_intensity_threshold"
            ),
        },
        "small_business_thresholds": {
            "aggregated_turnover": _number(
                instant, "aggregated_turnover_threshold"
            ),
            "base_rate_entity_turnover": _number(
                company, "base_rate_entity_turnover_threshold"
            ),
            "rd_refundable_turnover": _number(
                rd, "refundable_turnover_threshold"
            ),
            "instant_asset_writeoff": _number(instant, "threshold"),
        },
        "item7_label_overrides": label_overrides,
        "source_registry": source,
    }


ATO_POLICY_BY_YEAR: dict[str, dict[str, Any]] = {
    year: _policy_from_source(year) for year in SUPPORTED_YEARS
}


def get_policy_for_year(income_year: str) -> dict[str, Any]:
    year = str(income_year).strip()

    if year not in ATO_POLICY_BY_YEAR:
        raise ValueError(
            f"Unsupported income year {income_year!r}. "
            f"Available years: {sorted(ATO_POLICY_BY_YEAR)}"
        )

    policy = deepcopy(ATO_POLICY_BY_YEAR[year])
    policy["income_year"] = year
    return policy


def get_item7_labels_for_year(income_year: str) -> dict[str, dict[str, Any]]:
    labels = deepcopy(ITEM_7_LABELS)
    policy = get_policy_for_year(income_year)

    for label, override in policy.get("item7_label_overrides", {}).items():
        if label not in labels:
            labels[label] = {}

        labels[label].update(override)

    return labels


def validate_policy_year(income_year: str) -> None:
    get_policy_for_year(income_year)
