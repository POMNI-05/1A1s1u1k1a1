"""Deterministic Australian tax calculation primitives.

This package intentionally does not call AI services or mutate workbooks.  Callers
must collect and approve the relevant facts before invoking a calculator.
"""

from .company_tax import (
    BaseRateEntityAssessment,
    CompanyTaxResult,
    assess_base_rate_entity,
    calculate_company_tax,
)
from .depreciation import (
    DepreciationResult,
    InstantAssetWriteOffAssessment,
    assess_instant_asset_writeoff,
    calculate_decline_in_value,
)
from .division7a import Division7ARepaymentResult, calculate_minimum_yearly_repayment
from .reconciliation import Adjustment, ReconciliationResult, calculate_reconciliation
from .registry import SUPPORTED_YEARS, get_year_source
from .tax_losses import TaxLossResult, calculate_tax_loss_utilisation
from .validation import CalculatorError, ReviewRequiredError

__all__ = [
    "Adjustment",
    "BaseRateEntityAssessment",
    "CalculatorError",
    "CompanyTaxResult",
    "DepreciationResult",
    "Division7ARepaymentResult",
    "InstantAssetWriteOffAssessment",
    "ReconciliationResult",
    "ReviewRequiredError",
    "SUPPORTED_YEARS",
    "TaxLossResult",
    "assess_base_rate_entity",
    "assess_instant_asset_writeoff",
    "calculate_company_tax",
    "calculate_decline_in_value",
    "calculate_minimum_yearly_repayment",
    "calculate_reconciliation",
    "calculate_tax_loss_utilisation",
    "get_year_source",
]
