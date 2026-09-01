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


def build_job_options(
    ato_policy_year: str = "2026",
    requested_tables: dict[str, bool] | None = None,
    reviewer_notes: str = "",
    company_profile: str = "",
    document_description: str = "",
    client_name: str = "",
    company_tax_rate_category: str = "review_required",
    base_rate_entity_assessment: dict[str, Any] | None = None,
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
        "reviewed_tax_depreciation": normalise_reviewed_tax_depreciation(
            reviewed_tax_depreciation,
            tax_depreciation_approved_for_posting,
        ),
        "retain_job_files": bool(retain_job_files),
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "source": "frontend/job_runner.py",
    }
