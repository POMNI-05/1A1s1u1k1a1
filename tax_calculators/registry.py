"""Load and validate versioned ATO rule sources."""

from __future__ import annotations

import json
from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from typing import Any

from .validation import CalculatorError, ReviewRequiredError, to_decimal

SUPPORTED_YEARS = ("2024", "2025", "2026")
RULE_STATUSES = {"enacted", "review_required"}
_SOURCE_DIR = Path(__file__).with_name("sources")
_REQUIRED_SECTIONS = {
    "company_tax",
    "depreciation",
    "division7a",
    "instant_asset_writeoff",
    "rd_tax_incentive",
}
_REQUIRED_NUMERIC_KEYS = {
    "company_tax": {
        "base_rate_entity_rate",
        "general_rate",
        "base_rate_entity_turnover_threshold",
        "passive_income_max_ratio",
    },
    "depreciation": {
        "prime_cost_factor",
        "diminishing_value_factor",
        "day_denominator",
    },
    "division7a": {"benchmark_interest_rate"},
    "instant_asset_writeoff": {"threshold", "aggregated_turnover_threshold"},
    "rd_tax_incentive": {
        "refundable_turnover_threshold",
        "refundable_premium",
        "non_refundable_intensity_threshold",
        "non_refundable_lower_premium",
        "non_refundable_upper_premium",
        "notional_deduction_cap",
    },
}


class SourceValidationError(CalculatorError):
    """Raised when a versioned rules file is missing or malformed."""


def normalise_income_year(income_year: str | int) -> str:
    year = str(income_year).strip()
    if year not in SUPPORTED_YEARS:
        supported = ", ".join(SUPPORTED_YEARS)
        raise CalculatorError(f"Unsupported income year {year!r}; use one of: {supported}")
    return year


@lru_cache(maxsize=len(SUPPORTED_YEARS))
def _load_year_source(income_year: str) -> dict[str, Any]:
    path = _SOURCE_DIR / f"{income_year}.json"
    try:
        source = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SourceValidationError(f"Unable to load calculator source {path.name}") from exc

    if source.get("income_year") != income_year:
        raise SourceValidationError(f"{path.name} has the wrong income_year")
    if source.get("schema_version") != "1.0":
        raise SourceValidationError(f"{path.name} has an unsupported schema_version")
    missing = _REQUIRED_SECTIONS.difference(source)
    if missing:
        raise SourceValidationError(f"{path.name} is missing sections: {sorted(missing)}")

    for section_name in _REQUIRED_SECTIONS:
        section = source[section_name]
        if not isinstance(section, dict):
            raise SourceValidationError(f"{section_name} must be an object")
        if section.get("status") not in RULE_STATUSES:
            raise SourceValidationError(f"{section_name} has an invalid status")
        source_url = section.get("source_url")
        if not isinstance(source_url, str) or not source_url.startswith("https://www.ato.gov.au/"):
            raise SourceValidationError(f"{section_name} must cite an official ATO URL")

        for key in _REQUIRED_NUMERIC_KEYS[section_name]:
            value = section.get(key)
            if value is None and section["status"] == "review_required":
                continue
            if not isinstance(value, str):
                raise SourceValidationError(
                    f"{section_name}.{key} must be a decimal string"
                )
            try:
                numeric_value = to_decimal(value, f"{section_name}.{key}")
            except CalculatorError as exc:
                raise SourceValidationError(str(exc)) from exc
            if numeric_value < 0:
                raise SourceValidationError(
                    f"{section_name}.{key} must be non-negative"
                )
    return source


def get_year_source(income_year: str | int) -> dict[str, Any]:
    """Return a defensive copy of a validated source document."""

    year = normalise_income_year(income_year)
    return deepcopy(_load_year_source(year))


def get_rule_section(
    income_year: str | int,
    section_name: str,
    *,
    require_enacted: bool = True,
) -> dict[str, Any]:
    source = get_year_source(income_year)
    section = source.get(section_name)
    if not isinstance(section, dict):
        raise SourceValidationError(f"Unknown rule section {section_name!r}")
    if require_enacted and section["status"] != "enacted":
        raise ReviewRequiredError(
            f"{section_name} for income year {source['income_year']} requires accountant review"
        )
    return section


def get_decimal_rule(
    income_year: str | int,
    section_name: str,
    key: str,
    *,
    require_enacted: bool = True,
) -> Any:
    section = get_rule_section(
        income_year,
        section_name,
        require_enacted=require_enacted,
    )
    value = section.get(key)
    if value is None:
        raise ReviewRequiredError(
            f"{section_name}.{key} is not confirmed for income year {income_year}"
        )
    return to_decimal(value, f"{section_name}.{key}")
