"""Fail-closed tax-loss utilisation arithmetic."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .registry import normalise_income_year
from .validation import quantize_money, require_confirmation, require_non_negative


@dataclass(frozen=True)
class TaxLossResult:
    income_year: str
    taxable_income_before_losses: Decimal
    available_losses: Decimal
    requested_utilisation: Decimal
    losses_utilised: Decimal
    remaining_losses: Decimal
    taxable_income_after_losses: Decimal
    scope_note: str


def calculate_tax_loss_utilisation(
    income_year: str | int,
    *,
    taxable_income_before_losses: Decimal | str | int | float,
    available_losses: Decimal | str | int | float,
    requested_utilisation: Decimal | str | int | float | None = None,
    eligibility_confirmed: bool = False,
) -> TaxLossResult:
    """Calculate utilisation only after continuity/same-business eligibility review."""

    year = normalise_income_year(income_year)
    require_confirmation(
        eligibility_confirmed,
        "Tax-loss deduction eligibility must be confirmed before utilisation",
    )
    taxable = require_non_negative(
        taxable_income_before_losses,
        "taxable_income_before_losses",
    )
    available = require_non_negative(available_losses, "available_losses")
    requested = (
        available
        if requested_utilisation is None
        else require_non_negative(requested_utilisation, "requested_utilisation")
    )
    utilised = min(taxable, available, requested)
    return TaxLossResult(
        income_year=year,
        taxable_income_before_losses=quantize_money(taxable),
        available_losses=quantize_money(available),
        requested_utilisation=quantize_money(requested),
        losses_utilised=quantize_money(utilised),
        remaining_losses=quantize_money(available - utilised),
        taxable_income_after_losses=quantize_money(taxable - utilised),
        scope_note=(
            "Arithmetic only; eligibility, loss-year ordering, available fraction, "
            "business continuity, and integrity rules require accountant review."
        ),
    )
