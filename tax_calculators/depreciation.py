"""Deterministic decline-in-value and instant-write-off eligibility calculations."""

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
    require_positive,
    require_ratio,
)

DepreciationMethod = Literal["prime_cost", "diminishing_value"]


@dataclass(frozen=True)
class DepreciationResult:
    income_year: str
    method: DepreciationMethod
    opening_value: Decimal
    decline_in_value: Decimal
    taxable_use_ratio: Decimal
    deductible_decline: Decimal
    closing_value: Decimal
    source_url: str


@dataclass(frozen=True)
class InstantAssetWriteOffAssessment:
    income_year: str
    eligible_on_supplied_figures: bool
    asset_cost_below_threshold: bool
    turnover_below_threshold: bool
    asset_cost_threshold: Decimal
    turnover_threshold: Decimal
    source_url: str


def calculate_decline_in_value(
    income_year: str | int,
    *,
    method: DepreciationMethod,
    opening_value: Decimal | str | int | float,
    effective_life_years: Decimal | str | int | float,
    days_held: int,
    taxable_use_ratio: Decimal | str | int | float = 1,
) -> DepreciationResult:
    """Calculate prime-cost or post-9-May-2006 diminishing-value depreciation.

    For prime cost, ``opening_value`` must be the asset's cost. For diminishing
    value, it must be the base value at the start of the calculation period.
    """

    year = normalise_income_year(income_year)
    if method not in {"prime_cost", "diminishing_value"}:
        raise CalculatorError("method must be 'prime_cost' or 'diminishing_value'")
    value = require_non_negative(opening_value, "opening_value")
    effective_life = require_positive(effective_life_years, "effective_life_years")
    use_ratio = require_ratio(taxable_use_ratio, "taxable_use_ratio")
    if isinstance(days_held, bool) or not isinstance(days_held, int):
        raise CalculatorError("days_held must be a whole number")
    if days_held < 0 or days_held > 366:
        raise CalculatorError("days_held must be between 0 and 366")

    factor_key = "prime_cost_factor" if method == "prime_cost" else "diminishing_value_factor"
    factor = get_decimal_rule(year, "depreciation", factor_key)
    day_denominator = get_decimal_rule(year, "depreciation", "day_denominator")
    unrounded_decline = (
        value * Decimal(days_held) / day_denominator * factor / effective_life
    )
    decline = min(unrounded_decline, value)
    deductible = decline * use_ratio
    section = get_rule_section(year, "depreciation")
    return DepreciationResult(
        income_year=year,
        method=method,
        opening_value=quantize_money(value),
        decline_in_value=quantize_money(decline),
        taxable_use_ratio=use_ratio,
        deductible_decline=quantize_money(deductible),
        closing_value=quantize_money(value - decline),
        source_url=section["source_url"],
    )


def assess_instant_asset_writeoff(
    income_year: str | int,
    *,
    asset_cost: Decimal | str | int | float,
    aggregated_turnover: Decimal | str | int | float,
    eligibility_confirmed: bool = False,
) -> InstantAssetWriteOffAssessment:
    """Assess numeric thresholds after the caller confirms all non-numeric conditions."""

    year = normalise_income_year(income_year)
    require_confirmation(
        eligibility_confirmed,
        "Instant asset write-off conditions must be reviewed before eligibility is calculated",
    )
    cost = require_non_negative(asset_cost, "asset_cost")
    turnover = require_non_negative(aggregated_turnover, "aggregated_turnover")
    cost_threshold = get_decimal_rule(year, "instant_asset_writeoff", "threshold")
    turnover_threshold = get_decimal_rule(
        year,
        "instant_asset_writeoff",
        "aggregated_turnover_threshold",
    )
    section = get_rule_section(year, "instant_asset_writeoff")
    cost_ok = cost < cost_threshold
    turnover_ok = turnover < turnover_threshold
    return InstantAssetWriteOffAssessment(
        income_year=year,
        eligible_on_supplied_figures=cost_ok and turnover_ok,
        asset_cost_below_threshold=cost_ok,
        turnover_below_threshold=turnover_ok,
        asset_cost_threshold=cost_threshold,
        turnover_threshold=turnover_threshold,
        source_url=section["source_url"],
    )
