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

from itr_metadata import (
    TAX_RATES,
    RD_OFFSET_RATES,
    SMALL_BUSINESS_THRESHOLDS,
    ITEM_7_LABELS,
)


BASE_POLICY_YEAR = "2025"


ATO_POLICY_BY_YEAR: dict[str, dict[str, Any]] = {
    "2024": {
        "notes": [
            "Pre-2025 comparison year. Review labels and temporary incentives before use.",
        ],
        "tax_rates": TAX_RATES,
        "rd_offset_rates": RD_OFFSET_RATES,
        "small_business_thresholds": SMALL_BUSINESS_THRESHOLDS,
        "item7_label_overrides": {},
    },
    "2025": {
        "notes": [
            "Base policy year for current template logic.",
        ],
        "tax_rates": TAX_RATES,
        "rd_offset_rates": RD_OFFSET_RATES,
        "small_business_thresholds": SMALL_BUSINESS_THRESHOLDS,
        "item7_label_overrides": {},
    },
    "2026": {
        "notes": [
            "Forward-year placeholder. Review ATO company return changes before production use.",
        ],
        "tax_rates": TAX_RATES,
        "rd_offset_rates": RD_OFFSET_RATES,
        "small_business_thresholds": SMALL_BUSINESS_THRESHOLDS,
        "item7_label_overrides": {},
    },
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