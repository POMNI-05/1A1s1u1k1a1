"""Limited Division 7A minimum yearly repayment calculator."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .registry import get_decimal_rule, get_rule_section, normalise_income_year
from .validation import (
    CalculatorError,
    quantize_money,
    require_confirmation,
    require_non_negative,
)


@dataclass(frozen=True)
class Division7ARepaymentResult:
    income_year: str
    opening_balance: Decimal
    remaining_term_years: int
    benchmark_interest_rate: Decimal
    minimum_yearly_repayment: Decimal
    actual_repayments: Decimal
    repayment_shortfall: Decimal
    source_url: str
    scope_note: str


def calculate_minimum_yearly_repayment(
    income_year: str | int,
    *,
    opening_balance: Decimal | str | int | float,
    remaining_term_years: int,
    actual_repayments: Decimal | str | int | float = 0,
    loan_terms_reviewed: bool = False,
) -> Division7ARepaymentResult:
    """Apply the s109E(6) formula for a standard 30 June income year.

    This deliberately does not determine whether Division 7A applies, validate a
    loan agreement, handle a substituted accounting period, or calculate timed
    interest and closing balances for individual repayments.
    """

    year = normalise_income_year(income_year)
    require_confirmation(
        loan_terms_reviewed,
        "Division 7A loan terms and remaining term must be reviewed before calculation",
    )
    balance = require_non_negative(opening_balance, "opening_balance")
    repayments = require_non_negative(actual_repayments, "actual_repayments")
    if isinstance(remaining_term_years, bool) or not isinstance(remaining_term_years, int):
        raise CalculatorError("remaining_term_years must be a whole number")
    if remaining_term_years < 1 or remaining_term_years > 25:
        raise CalculatorError("remaining_term_years must be between 1 and 25")

    rate = get_decimal_rule(year, "division7a", "benchmark_interest_rate")
    denominator = Decimal("1") - (
        Decimal("1") / (Decimal("1") + rate)
    ) ** remaining_term_years
    minimum = Decimal("0") if balance == 0 else balance * rate / denominator
    minimum_money = quantize_money(minimum)
    shortfall = quantize_money(max(minimum_money - repayments, Decimal("0")))
    section = get_rule_section(year, "division7a")
    return Division7ARepaymentResult(
        income_year=year,
        opening_balance=quantize_money(balance),
        remaining_term_years=remaining_term_years,
        benchmark_interest_rate=rate,
        minimum_yearly_repayment=minimum_money,
        actual_repayments=quantize_money(repayments),
        repayment_shortfall=shortfall,
        source_url=section["source_url"],
        scope_note=(
            "Standard 30 June income year and aggregate repayments only; use the ATO "
            "Division 7A tool for dated repayments, interest, and closing balances."
        ),
    )
