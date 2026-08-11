# v1/config.py
"""
Central configuration for the uploaded-file workpaper pipeline.

Design rule:
- Raw P&L and Balance Sheet files are source evidence.
- cleaner.py parses/chunks those reports into structured rows.
- itr_metadata.py contains static ATO/ITR metadata.
- itr_rules.py contains account-name matching and labelling logic.
- TAX_ADJUSTMENTS contains reviewed tax reconciliation amounts only.
- AI/API features are optional helpers, not final decision makers.
"""

from __future__ import annotations

import os
from pathlib import Path

from tax_calculators.company_tax import assess_base_rate_entity
from tax_calculators.validation import CalculatorError, to_decimal

try:
    from .ato_policy import get_policy_for_year
    from .job_config import load_job_config
except ImportError:  # Direct-script compatibility.
    from ato_policy import get_policy_for_year
    from job_config import load_job_config

# ---------------------------------------------------------------------------
# 1. Base paths
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent
JOB_WORK_DIR = Path(os.getenv("TAX_JOB_WORK_DIR", str(BASE_DIR)))
DATA_DIR = Path(os.getenv("TAX_DATA_DIR", str(JOB_WORK_DIR / "data")))
INPUT_DIR = DATA_DIR
PROCESSED_DIR = DATA_DIR / "processed"
OUTPUT_DIR = Path(os.getenv("TAX_OUTPUT_DIR", str(JOB_WORK_DIR / "output")))
LOG_DIR = Path(os.getenv("TAX_LOG_DIR", str(JOB_WORK_DIR / "logs")))

# Backward-compatible separate-file names.
PL_RAW_PATH = DATA_DIR / "profit_and_loss_raw.xlsx"
BS_RAW_PATH = DATA_DIR / "balance_sheet_raw.xlsx"

# Flexible combined-workbook input.
INPUT_WORKBOOK_PATH = Path(
    os.getenv("INPUT_WORKBOOK_PATH", str(DATA_DIR / "xero_reports.xlsx"))
)

ALLOW_COMBINED_WORKBOOK = os.getenv("ALLOW_COMBINED_WORKBOOK", "true").lower() == "true"

# Optional support schedule paths.
TAX_DEPRECIATION_PATH = os.getenv("TAX_DEPRECIATION_PATH", "")

# Optional sheet-name overrides.
PL_SHEET_NAME = os.getenv("PL_SHEET_NAME", "")
BS_SHEET_NAME = os.getenv("BS_SHEET_NAME", "")
TAX_DEPRECIATION_SHEET_NAME = os.getenv("TAX_DEPRECIATION_SHEET_NAME", "")

# ---------------------------------------------------------------------------
# 2. Output settings
# ---------------------------------------------------------------------------

OUTPUT_PATH = Path(
    os.getenv("TAX_OUTPUT_PATH", str(OUTPUT_DIR / "tax_workpaper.xlsx"))
)

SHEET_PL_RAW = "Profit and Loss"
SHEET_BS_RAW = "Balance Sheet"
SHEET_RECONCILIATION = "Tax Reconciliation"

# ---------------------------------------------------------------------------
# 3. Report type constants
# ---------------------------------------------------------------------------

REPORT_TYPE_PL = "profit_and_loss"
REPORT_TYPE_BS = "balance_sheet"
REPORT_TYPE_TAX_DEPRECIATION = "tax_depreciation"
REPORT_TYPE_UNKNOWN = "unknown"

# ---------------------------------------------------------------------------
# 4. Job options / frontend checkbox defaults
# ---------------------------------------------------------------------------

SELECTED_INCOME_YEAR = os.getenv(
    "SELECTED_INCOME_YEAR",
    os.getenv("ATO_POLICY_YEAR", "2026"),
)

INCLUDE_RD_TABLE = os.getenv("INCLUDE_RD_TABLE", "true").lower() == "true"
INCLUDE_CARRY_LOSS_TABLE = os.getenv("INCLUDE_CARRY_LOSS_TABLE", "true").lower() == "true"
INCLUDE_TAX_DEPRECIATION_REVIEW = (
    os.getenv("INCLUDE_TAX_DEPRECIATION_REVIEW", "true").lower() == "true"
)

# API placeholder: keep this false until OAuth/API workflow exists.
ENABLE_XERO_API = os.getenv("ENABLE_XERO_API", "false").lower() == "true"
XERO_API_CLIENT_ID = os.getenv("XERO_API_CLIENT_ID", "")
XERO_API_TENANT_ID = os.getenv("XERO_API_TENANT_ID", "")

# AI reviewer placeholder.
ENABLE_GEMINI_REVIEW = os.getenv("ENABLE_GEMINI_REVIEW", "false").lower() == "true"
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_REVIEW_CONFIDENCE_THRESHOLD = os.getenv(
    "GEMINI_REVIEW_CONFIDENCE_THRESHOLD",
    "low",
)

# ---------------------------------------------------------------------------
# 5. Tax settings
# ---------------------------------------------------------------------------

COMPANY_TAX_RATE_CATEGORY = os.getenv(
    "COMPANY_TAX_RATE_CATEGORY",
    "review_required",
).strip().lower()

_JOB_CONFIG = load_job_config()
BASE_RATE_ENTITY_ASSESSMENT = _JOB_CONFIG.get("base_rate_entity_assessment") or {}


def _base_rate_assessment_is_valid() -> bool:
    if BASE_RATE_ENTITY_ASSESSMENT.get("reviewer_confirmed") is not True:
        return False
    try:
        if to_decimal(
            BASE_RATE_ENTITY_ASSESSMENT.get("total_assessable_income"),
            "total_assessable_income",
        ) <= 0:
            return False
        assessment = assess_base_rate_entity(
            SELECTED_INCOME_YEAR,
            aggregated_turnover=BASE_RATE_ENTITY_ASSESSMENT.get(
                "aggregated_turnover"
            ),
            total_assessable_income=BASE_RATE_ENTITY_ASSESSMENT.get(
                "total_assessable_income"
            ),
            base_rate_entity_passive_income=BASE_RATE_ENTITY_ASSESSMENT.get(
                "base_rate_entity_passive_income"
            ),
        )
    except (CalculatorError, TypeError, ValueError):
        return False
    return assessment.eligible_on_supplied_figures


if COMPANY_TAX_RATE_CATEGORY == "base_rate_entity" and not _base_rate_assessment_is_valid():
    # A bare environment variable or stale UI choice is not sufficient evidence.
    COMPANY_TAX_RATE_CATEGORY = "review_required"

SELECTED_ATO_POLICY = get_policy_for_year(SELECTED_INCOME_YEAR)
SELECTED_TAX_RATES = SELECTED_ATO_POLICY["tax_rates"]

if COMPANY_TAX_RATE_CATEGORY == "base_rate_entity":
    TAX_RATE = SELECTED_TAX_RATES["base_rate_entity"]
elif COMPANY_TAX_RATE_CATEGORY == "general":
    TAX_RATE = SELECTED_TAX_RATES["general"]
else:
    # A rate must never be guessed from the client's generic company profile.
    TAX_RATE = None

SMALL_BUSINESS_ENTITY = os.getenv("SMALL_BUSINESS_ENTITY", "false").lower() == "true"
INSTANT_ASSET_WRITEOFF_LIMIT = SELECTED_ATO_POLICY[
    "small_business_thresholds"
]["instant_asset_writeoff"]

RD_ELIGIBLE = os.getenv("RD_ELIGIBLE", "false").lower() == "true"
RD_REFUNDABLE = os.getenv("RD_REFUNDABLE", "true").lower() == "true"
RD_PREMIUMS = SELECTED_ATO_POLICY["rd_offset_rates"]
# A refundable R&D rate is the selected company rate plus 18.5 percentage
# points. A non-refundable claim is intensity-tiered, so no single safe rate
# exists without additional inputs.
RD_OFFSET_RATE = (
    TAX_RATE + RD_PREMIUMS["refundable_premium"]
    if RD_ELIGIBLE and RD_REFUNDABLE and TAX_RATE is not None
    else None
)

# ---------------------------------------------------------------------------
# 6. Reviewed tax reconciliation inputs
# ---------------------------------------------------------------------------
# These are the ONLY manual/reviewed amounts that change taxable income,
# apart from base accounting profit.
#
# Supports:
#   {"description": "...", "amount": 100.00, "source": "Manual review"}
# or multi-period:
#   {"description": "...", "amounts": {"2026": 100.00, "2025": 50.00}}

TAX_ADJUSTMENTS = {
    "add_back_7B": [],
    "add_back_7W": [],
    "add_back_7D": [],
    "add_back_7Y": [],
    "subtract_7Q": [],
    "subtract_7X": [],
    "subtract_7F": [],
    "subtract_7I": [],
    "subtract_7Z": [],
    "subtract_7R": [],
}

# ---------------------------------------------------------------------------
# 7. Support table templates
# ---------------------------------------------------------------------------

CARRY_FORWARD_LOSSES_TEMPLATE = [
    {"Description": "30-Jun-21", "Amount": None},
    {"Description": "30-Jun-22", "Amount": None},
    {"Description": "30-Jun-23", "Amount": None},
    {"Description": "30-Jun-24", "Amount": None},
    {"Description": "30-Jun-25", "Amount": None},
    {"Description": "Total Losses", "Amount": None},
]

RD_BREAKDOWN_TEMPLATE = [
    {"Description": "Eligible Spend", "Amount": None},
    {"Description": "", "Amount": None},
    {"Description": "Expensed", "Amount": None},
    {"Description": "Capitalised", "Amount": None},
    {"Description": "", "Amount": None},
    {"Description": "Add Back Expense at Label 7D", "Amount": None},
    {"Description": "Reduction in Software Development Pool", "Amount": None},
]

RD_OFFSET_AMOUNT = None

# ---------------------------------------------------------------------------
# 8. Safe tax depreciation handling
# ---------------------------------------------------------------------------
# Default:
# - extract tax depreciation total as support;
# - do not automatically post it to taxable income unless reviewed/enabled.

AUTO_POST_TAX_DEPRECIATION_TO_7F = (
    os.getenv("AUTO_POST_TAX_DEPRECIATION_TO_7F", "false").lower() == "true"
)
