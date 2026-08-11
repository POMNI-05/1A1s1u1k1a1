"""Approval-aware accounting-profit to taxable-income reconciliation."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal, Sequence

from .validation import CalculatorError, quantize_money, to_decimal

AdjustmentDirection = Literal["add", "subtract"]
ApprovalStatus = Literal["proposed", "approved", "rejected"]


@dataclass(frozen=True)
class Adjustment:
    description: str
    amount: Decimal | str | int | float
    direction: AdjustmentDirection
    approval_status: ApprovalStatus = "proposed"
    source_reference: str = ""


@dataclass(frozen=True)
class ReconciliationResult:
    accounting_profit: Decimal
    approved_additions: Decimal
    approved_subtractions: Decimal
    taxable_income: Decimal
    included_adjustments: tuple[Adjustment, ...]
    excluded_adjustments: tuple[Adjustment, ...]


def _validate_adjustment(adjustment: Adjustment) -> Decimal:
    if not adjustment.description.strip():
        raise CalculatorError("adjustment description must not be blank")
    if adjustment.direction not in {"add", "subtract"}:
        raise CalculatorError("adjustment direction must be 'add' or 'subtract'")
    if adjustment.approval_status not in {"proposed", "approved", "rejected"}:
        raise CalculatorError(
            "adjustment approval_status must be 'proposed', 'approved', or 'rejected'"
        )
    return to_decimal(adjustment.amount, f"adjustment {adjustment.description!r} amount")


def calculate_reconciliation(
    accounting_profit: Decimal | str | int | float,
    adjustments: Sequence[Adjustment],
) -> ReconciliationResult:
    """Post approved adjustments only, while preserving signed input amounts."""

    profit = to_decimal(accounting_profit, "accounting_profit")
    additions = Decimal("0")
    subtractions = Decimal("0")
    included: list[Adjustment] = []
    excluded: list[Adjustment] = []

    for adjustment in adjustments:
        amount = _validate_adjustment(adjustment)
        if adjustment.approval_status != "approved":
            excluded.append(adjustment)
            continue
        included.append(adjustment)
        if adjustment.direction == "add":
            additions += amount
        else:
            subtractions += amount

    taxable_income = profit + additions - subtractions
    return ReconciliationResult(
        accounting_profit=quantize_money(profit),
        approved_additions=quantize_money(additions),
        approved_subtractions=quantize_money(subtractions),
        taxable_income=quantize_money(taxable_income),
        included_adjustments=tuple(included),
        excluded_adjustments=tuple(excluded),
    )
