"""Deterministic frontend job-option builders.

This module prepares reviewer-supplied options for the isolated backend job.
It does not read workbooks, call providers or decide tax outcomes.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from tax_calculators.company_tax import assess_base_rate_entity
from tax_calculators.registry import normalise_income_year
from tax_calculators.validation import CalculatorError, to_decimal


DEFAULT_REQUESTED_TABLES: dict[str, bool] = {
    "carry_forward_losses": False,
    "rd_tax_incentive": False,
    "div7a": False,
    "fbt_entertainment": False,
    "depreciation": False,
    "superannuation": False,
    "gst_reconciliation": False,
    "related_party_loans": False,
    "psi": False,
}


def normalise_requested_tables(
    requested_tables: dict[str, bool] | None,
) -> dict[str, bool]:
    tables = DEFAULT_REQUESTED_TABLES.copy()

    if not requested_tables:
        return tables

    for key, value in requested_tables.items():
        if key in tables:
            tables[key] = bool(value)

    return tables


def normalise_policy_year(ato_policy_year: str | None = None) -> str:
    """Validate an explicitly selected policy year; never substitute another."""

    if ato_policy_year is None:
        return "2026"
    return normalise_income_year(ato_policy_year)


def build_base_rate_entity_assessment(
    income_year: str,
    *,
    aggregated_turnover: float | int | str,
    total_assessable_income: float | int | str,
    base_rate_entity_passive_income: float | int | str,
    reviewer_confirmed: bool = False,
) -> dict[str, Any]:
    """Return a JSON-safe assessment for the frontend and job audit record."""

    assessment = assess_base_rate_entity(
        normalise_policy_year(income_year),
        aggregated_turnover=aggregated_turnover,
        total_assessable_income=total_assessable_income,
        base_rate_entity_passive_income=base_rate_entity_passive_income,
    )
    return {
        "income_year": assessment.income_year,
        "aggregated_turnover": str(aggregated_turnover),
        "total_assessable_income": str(total_assessable_income),
        "base_rate_entity_passive_income": str(base_rate_entity_passive_income),
        "passive_income_ratio": str(assessment.passive_income_ratio),
        "turnover_threshold": str(assessment.turnover_threshold),
        "passive_income_ratio_limit": str(assessment.passive_income_ratio_limit),
        "turnover_below_threshold": assessment.turnover_below_threshold,
        "passive_income_ratio_within_limit": (
            assessment.passive_income_ratio_within_limit
        ),
        "eligible_on_supplied_figures": assessment.eligible_on_supplied_figures,
        "reviewer_confirmed": reviewer_confirmed is True,
    }


def base_rate_assessment_is_confirmed(
    assessment: dict[str, Any] | None,
    income_year: str,
) -> bool:
    if not assessment or assessment.get("reviewer_confirmed") is not True:
        return False
    try:
        if to_decimal(
            assessment.get("total_assessable_income"),
            "total_assessable_income",
        ) <= 0:
            return False
        verified = build_base_rate_entity_assessment(
            income_year,
            aggregated_turnover=assessment.get("aggregated_turnover"),
            total_assessable_income=assessment.get("total_assessable_income"),
            base_rate_entity_passive_income=assessment.get(
                "base_rate_entity_passive_income"
            ),
            reviewer_confirmed=True,
        )
    except (CalculatorError, TypeError, ValueError):
        return False
    return verified["eligible_on_supplied_figures"] is True


def normalise_reviewed_tax_depreciation(
    amount: float | int | str | None,
    approved_for_posting: bool = False,
) -> dict[str, Any]:
    """Keep a supplied 7F amount explicit and separate from posting approval."""

    if amount is None or not str(amount).strip():
        return {"amount": None, "approved_for_posting": False}

    text = str(amount).strip().replace("$", "").replace(",", "")
    decimal_amount = to_decimal(text, "reviewed_tax_depreciation")
    if decimal_amount < 0:
        raise CalculatorError("reviewed_tax_depreciation must not be negative")

    return {
        "amount": str(decimal_amount),
        "approved_for_posting": approved_for_posting is True,
    }


def normalise_reviewed_tax_losses(
    opening_losses: float | int | str | None = None,
    requested_utilisation: float | int | str | None = None,
    eligibility_confirmed: bool = False,
    eligibility_basis: str = "",
    review_note: str = "",
    approved_for_posting: bool = False,
) -> dict[str, Any]:
    """Keep tax-loss calculation authority separate from posting approval."""

    note = str(review_note or "").strip()
    basis = str(eligibility_basis or "").strip()
    if opening_losses is None or not str(opening_losses).strip():
        return {
            "opening_losses": None,
            "requested_utilisation": None,
            "eligibility_confirmed": False,
            "eligibility_basis": "",
            "review_note": note,
            "approved_for_posting": False,
        }

    opening_text = str(opening_losses).strip().replace("$", "").replace(",", "")
    opening = to_decimal(opening_text, "opening_losses")
    if opening < 0:
        raise CalculatorError("opening_losses must not be negative")

    requested = None
    if requested_utilisation is not None and str(requested_utilisation).strip():
        requested_text = (
            str(requested_utilisation).strip().replace("$", "").replace(",", "")
        )
        requested = to_decimal(requested_text, "requested_utilisation")
        if requested < 0:
            raise CalculatorError("requested_utilisation must not be negative")

    eligibility_ok = eligibility_confirmed is True
    return {
        "opening_losses": str(opening),
        "requested_utilisation": str(requested) if requested is not None else None,
        "eligibility_confirmed": eligibility_ok,
        "eligibility_basis": basis,
        "review_note": note,
        "approved_for_posting": approved_for_posting is True and eligibility_ok,
    }


def _clean_optional_money(value: float | int | str | None, field: str) -> str | None:
    if value is None or not str(value).strip():
        return None
    text = str(value).strip().replace("$", "").replace(",", "")
    amount = to_decimal(text, field)
    if amount < 0:
        raise CalculatorError(f"{field} must not be negative")
    return str(amount)


def _clean_optional_int(value: int | str | None, field: str) -> int | None:
    if value is None or not str(value).strip():
        return None
    try:
        parsed = int(str(value).strip())
    except ValueError as exc:
        raise CalculatorError(f"{field} must be a whole number") from exc
    if parsed < 0:
        raise CalculatorError(f"{field} must not be negative")
    return parsed


def _clean_choice(value: Any, allowed: set[str], default: str) -> str:
    text = str(value or "").strip().lower().replace(" ", "_").replace("/", "_")
    return text if text in allowed else default


def normalise_reviewed_div7a(reviewed_div7a: dict[str, Any] | None) -> dict[str, Any]:
    """Normalise reviewed Division 7A facts without making legal conclusions."""

    raw = reviewed_div7a or {}
    private_company_status = _clean_choice(
        raw.get("private_company_status"),
        {"confirmed_private", "not_private", "review_required"},
        "review_required",
    )
    transaction_exists = _clean_choice(
        raw.get("transaction_exists"),
        {"no", "yes", "unsure"},
        "unsure",
    )
    transaction_type = _clean_choice(
        raw.get("transaction_type"),
        {
            "loan",
            "payment_private_expense",
            "debt_forgiveness",
            "trust_upe",
            "indirect_interposed",
            "other_unsure",
        },
        "",
    )
    balance_direction = _clean_choice(
        raw.get("balance_direction"),
        {
            "shareholder_director_owes_company",
            "company_owes_shareholder_director",
            "unsure",
        },
        "unsure",
    )
    shareholder_status = _clean_choice(
        raw.get("shareholder_or_associate_status"),
        {"confirmed", "no", "review_required"},
        "review_required",
    )
    fully_repaid = _clean_choice(
        raw.get("fully_repaid_before_lodgment"),
        {"yes", "no", "review_required"},
        "review_required",
    )
    complying_status = _clean_choice(
        raw.get("complying_loan_status"),
        {"confirmed", "no", "review_required"},
        "review_required",
    )

    return {
        "private_company_status": private_company_status,
        "transaction_exists": transaction_exists,
        "transaction_type": transaction_type,
        "source_account": str(raw.get("source_account") or "").strip(),
        "source_balance": _clean_optional_money(
            raw.get("source_balance"),
            "div7a_source_balance",
        ),
        "balance_direction": balance_direction,
        "shareholder_or_associate_status": shareholder_status,
        "loan_amount": _clean_optional_money(raw.get("loan_amount"), "div7a_loan_amount"),
        "opening_balance": _clean_optional_money(
            raw.get("opening_balance"),
            "div7a_opening_balance",
        ),
        "repayments_before_lodgment": _clean_optional_money(
            raw.get("repayments_before_lodgment"),
            "div7a_repayments_before_lodgment",
        ),
        "outstanding_at_lodgment": _clean_optional_money(
            raw.get("outstanding_at_lodgment"),
            "div7a_outstanding_at_lodgment",
        ),
        "fully_repaid_before_lodgment": fully_repaid,
        "repayment_integrity_reviewed": raw.get("repayment_integrity_reviewed") is True,
        "complying_loan_status": complying_status,
        "loan_start_year": _clean_optional_int(
            raw.get("loan_start_year"),
            "div7a_loan_start_year",
        ),
        "loan_term_years": _clean_optional_int(
            raw.get("loan_term_years"),
            "div7a_loan_term_years",
        ),
        "remaining_term_years": _clean_optional_int(
            raw.get("remaining_term_years"),
            "div7a_remaining_term_years",
        ),
        "eligible_repayments": _clean_optional_money(
            raw.get("eligible_repayments"),
            "div7a_eligible_repayments",
        ),
        "reviewed_distributable_surplus": _clean_optional_money(
            raw.get("reviewed_distributable_surplus"),
            "div7a_reviewed_distributable_surplus",
        ),
        "review_note": str(raw.get("review_note") or "").strip(),
        "source_note": str(raw.get("source_note") or "").strip(),
        "approved": raw.get("approved") is True,
    }


def build_job_options(
    ato_policy_year: str = "2026",
    requested_tables: dict[str, bool] | None = None,
    reviewer_notes: str = "",
    company_profile: str = "",
    document_description: str = "",
    client_name: str = "",
    company_tax_rate_category: str = "review_required",
    base_rate_entity_assessment: dict[str, Any] | None = None,
    reviewed_tax_losses: dict[str, Any] | None = None,
    reviewed_div7a: dict[str, Any] | None = None,
    reviewed_tax_depreciation: float | int | str | None = None,
    tax_depreciation_approved_for_posting: bool = False,
    retain_job_files: bool = False,
) -> dict[str, Any]:
    year = normalise_policy_year(ato_policy_year)
    rate_category = company_tax_rate_category
    if rate_category == "base_rate_entity" and not base_rate_assessment_is_confirmed(
        base_rate_entity_assessment,
        year,
    ):
        rate_category = "review_required"

    return {
        "ato_policy_year": year,
        "itr_policy_year": year,
        "requested_tables": normalise_requested_tables(requested_tables),
        "reviewer_notes": reviewer_notes or "",
        "company_profile": company_profile or "",
        "document_description": document_description or "",
        "client_name": client_name or "",
        "company_tax_rate_category": (
            rate_category
            if rate_category in {"base_rate_entity", "general"}
            else "review_required"
        ),
        "base_rate_entity_assessment": base_rate_entity_assessment or {},
        "reviewed_tax_losses": normalise_reviewed_tax_losses(
            **(reviewed_tax_losses or {})
        ),
        "reviewed_div7a": normalise_reviewed_div7a(reviewed_div7a),
        "reviewed_tax_depreciation": normalise_reviewed_tax_depreciation(
            reviewed_tax_depreciation,
            tax_depreciation_approved_for_posting,
        ),
        "retain_job_files": bool(retain_job_files),
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "source": "frontend/job_runner.py",
    }
