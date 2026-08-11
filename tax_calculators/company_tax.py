"""Australian company tax rate selection and indicative tax calculation."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from .registry import get_decimal_rule, get_rule_section, normalise_income_year
from .validation import (
    CalculatorError,
    quantize_money,
    require_confirmation,
    require_non_negative,
)

RateCategory = Literal["base_rate_entity", "general"]


@dataclass(frozen=True)
class BaseRateEntityAssessment:
    income_year: str
    eligible_on_supplied_figures: bool
    turnover_below_threshold: bool
    passive_income_ratio_within_limit: bool
    passive_income_ratio: Decimal
    turnover_threshold: Decimal
    passive_income_ratio_limit: Decimal


@dataclass(frozen=True)
class CompanyTaxResult:
    income_year: str
    rate_category: RateCategory
    tax_rate: Decimal
    taxable_income: Decimal
    gross_tax: Decimal
    non_refundable_offsets: Decimal
    indicative_tax_payable: Decimal
    source_url: str


def assess_base_rate_entity(
    income_year: str | int,
    *,
    aggregated_turnover: Decimal | str | int | float,
    total_assessable_income: Decimal | str | int | float,
    base_rate_entity_passive_income: Decimal | str | int | float,
) -> BaseRateEntityAssessment:
    """Assess only the two numeric base-rate-entity tests using supplied facts."""

    year = normalise_income_year(income_year)
    turnover = require_non_negative(aggregated_turnover, "aggregated_turnover")
    assessable = require_non_negative(total_assessable_income, "total_assessable_income")
    passive = require_non_negative(
        base_rate_entity_passive_income,
        "base_rate_entity_passive_income",
    )
    if passive > assessable:
        raise CalculatorError(
            "base_rate_entity_passive_income cannot exceed total_assessable_income"
        )

    turnover_threshold = get_decimal_rule(
        year,
        "company_tax",
        "base_rate_entity_turnover_threshold",
    )
    passive_limit = get_decimal_rule(
        year,
        "company_tax",
        "passive_income_max_ratio",
    )
    passive_ratio = Decimal("0") if assessable == 0 else passive / assessable
    turnover_ok = turnover < turnover_threshold
    passive_ok = passive_ratio <= passive_limit
    return BaseRateEntityAssessment(
        income_year=year,
        eligible_on_supplied_figures=turnover_ok and passive_ok,
        turnover_below_threshold=turnover_ok,
        passive_income_ratio_within_limit=passive_ok,
        passive_income_ratio=passive_ratio,
        turnover_threshold=turnover_threshold,
        passive_income_ratio_limit=passive_limit,
    )


def calculate_company_tax(
    income_year: str | int,
    *,
    taxable_income: Decimal | str | int | float,
    rate_category: RateCategory,
    base_rate_eligibility_confirmed: bool = False,
    non_refundable_offsets: Decimal | str | int | float = 0,
) -> CompanyTaxResult:
    """Calculate indicative company tax after an explicit rate-category decision."""

    year = normalise_income_year(income_year)
    if rate_category not in {"base_rate_entity", "general"}:
        raise CalculatorError("rate_category must be 'base_rate_entity' or 'general'")
    if rate_category == "base_rate_entity":
        require_confirmation(
            base_rate_eligibility_confirmed,
            "Base rate entity eligibility must be confirmed before applying the 25% rate",
        )

    taxable = require_non_negative(taxable_income, "taxable_income")
    offsets = require_non_negative(non_refundable_offsets, "non_refundable_offsets")
    rate_key = "base_rate_entity_rate" if rate_category == "base_rate_entity" else "general_rate"
    rate = get_decimal_rule(year, "company_tax", rate_key)
    gross_tax = quantize_money(taxable * rate)
    payable = quantize_money(max(gross_tax - offsets, Decimal("0")))
    section = get_rule_section(year, "company_tax")
    return CompanyTaxResult(
        income_year=year,
        rate_category=rate_category,
        tax_rate=rate,
        taxable_income=quantize_money(taxable),
        gross_tax=gross_tax,
        non_refundable_offsets=quantize_money(offsets),
        indicative_tax_payable=payable,
        source_url=section["source_url"],
    )
