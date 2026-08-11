"""Shared validation and decimal helpers for calculator modules."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

MONEY_QUANTUM = Decimal("0.01")


class CalculatorError(ValueError):
    """Raised when calculator input is invalid."""


class ReviewRequiredError(CalculatorError):
    """Raised when a calculation cannot safely proceed without human review."""


def to_decimal(value: Any, field: str) -> Decimal:
    """Convert a numeric input to a finite Decimal without binary-float arithmetic."""

    if isinstance(value, bool) or value is None:
        raise CalculatorError(f"{field} must be a number")

    try:
        decimal_value = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise CalculatorError(f"{field} must be a number") from exc

    if not decimal_value.is_finite():
        raise CalculatorError(f"{field} must be finite")
    return decimal_value


def require_non_negative(value: Any, field: str) -> Decimal:
    decimal_value = to_decimal(value, field)
    if decimal_value < 0:
        raise CalculatorError(f"{field} must be non-negative")
    return decimal_value


def require_positive(value: Any, field: str) -> Decimal:
    decimal_value = to_decimal(value, field)
    if decimal_value <= 0:
        raise CalculatorError(f"{field} must be greater than zero")
    return decimal_value


def require_ratio(value: Any, field: str) -> Decimal:
    decimal_value = to_decimal(value, field)
    if decimal_value < 0 or decimal_value > 1:
        raise CalculatorError(f"{field} must be between 0 and 1")
    return decimal_value


def require_confirmation(confirmed: bool, message: str) -> None:
    if confirmed is not True:
        raise ReviewRequiredError(message)


def quantize_money(value: Decimal) -> Decimal:
    return value.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)
