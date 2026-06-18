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

from itr_metadata import TAX_RATES, RD_OFFSET_RATES, SMALL_BUSINESS_THRESHOLDS

# ---------------------------------------------------------------------------
# 1. Base paths
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
INPUT_DIR = DATA_DIR
PROCESSED_DIR = DATA_DIR / "processed"
OUTPUT_DIR = BASE_DIR / "output"
LOG_DIR = BASE_DIR / "logs"

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

OUTPUT_PATH = OUTPUT_DIR / "5_ZHI_output.xlsx"

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

SELECTED_INCOME_YEAR = os.getenv("SELECTED_INCOME_YEAR", "2026")

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

BASE_RATE_ENTITY = os.getenv("BASE_RATE_ENTITY", "true").lower() == "true"
TAX_RATE = TAX_RATES["base_rate_entity"] if BASE_RATE_ENTITY else TAX_RATES["general"]

SMALL_BUSINESS_ENTITY = os.getenv("SMALL_BUSINESS_ENTITY", "false").lower() == "true"
INSTANT_ASSET_WRITEOFF_LIMIT = SMALL_BUSINESS_THRESHOLDS["instant_asset_writeoff"]

RD_ELIGIBLE = os.getenv("RD_ELIGIBLE", "false").lower() == "true"
RD_REFUNDABLE = os.getenv("RD_REFUNDABLE", "true").lower() == "true"
RD_OFFSET_RATE = RD_OFFSET_RATES["refundable"] if RD_REFUNDABLE else RD_OFFSET_RATES["non_refundable"]

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