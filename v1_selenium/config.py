# v1_selenium/config.py
"""
Central configuration for the Xero automation pipeline.

Important design rule:
- Selenium/download settings live here.
- Tax/accounting rules live in itr_rules.py.
- Client-specific tax adjustments live in TAX_ADJUSTMENTS.
"""

import os
from itr_rules import TAX_RATES, RD_OFFSET_RATES, SMALL_BUSINESS_THRESHOLDS

# ---------------------------------------------------------------------------
# Base paths
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
DOWNLOAD_DIR = DATA_DIR
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
LOG_DIR = os.path.join(BASE_DIR, "logs")

PL_RAW_PATH = os.path.join(DATA_DIR, "profit_and_loss_raw.xlsx")
BS_RAW_PATH = os.path.join(DATA_DIR, "balance_sheet_raw.xlsx")
OUTPUT_PATH = os.path.join(OUTPUT_DIR, "xero_workpaper.xlsx")

SHEET_PL_RAW = "Xero PL Raw"
SHEET_BS_RAW = "Xero BS Raw"
SHEET_TAX_FINANCIAL_PL = "Tax Financial PL"
SHEET_TAX_FINANCIAL_BS = "Tax Financial BS"
SHEET_RECONCILIATION = "Tax Reconciliation"
SHEET_CHECKS = "Checks"

# ---------------------------------------------------------------------------
# Selenium settings
# ---------------------------------------------------------------------------
USE_SELENIUM = os.getenv("USE_SELENIUM", "false").lower() == "true"
HEADLESS = os.getenv("HEADLESS", "false").lower() == "true"
DOWNLOAD_WAIT = int(os.getenv("DOWNLOAD_WAIT", "60"))

XERO_EMAIL = os.getenv("XERO_EMAIL", "")
XERO_PASSWORD = os.getenv("XERO_PASSWORD", "")

REPORT_END_DATE = os.getenv("REPORT_END_DATE", "30 Jun 2025")
COMPARE_WITH = os.getenv("COMPARE_WITH", "1 year")
REPORT_FILTER = os.getenv("REPORT_FILTER", "")

# ---------------------------------------------------------------------------
# Tax settings
# ---------------------------------------------------------------------------
BASE_RATE_ENTITY = os.getenv("BASE_RATE_ENTITY", "true").lower() == "true"
TAX_RATE = TAX_RATES["base_rate_entity"] if BASE_RATE_ENTITY else TAX_RATES["general"]

SMALL_BUSINESS_ENTITY = os.getenv("SMALL_BUSINESS_ENTITY", "false").lower() == "true"
INSTANT_ASSET_WRITEOFF_LIMIT = SMALL_BUSINESS_THRESHOLDS["instant_asset_writeoff"]

RD_ELIGIBLE = os.getenv("RD_ELIGIBLE", "false").lower() == "true"
RD_REFUNDABLE = os.getenv("RD_REFUNDABLE", "true").lower() == "true"
RD_OFFSET_RATE = RD_OFFSET_RATES["refundable"] if RD_REFUNDABLE else RD_OFFSET_RATES["non_refundable"]

# ---------------------------------------------------------------------------
# Manual tax adjustments
# ---------------------------------------------------------------------------
# These amounts are NOT automatically taken from the P&L. The P&L mapping only
# gives review guidance. Actual add-back/deduction amounts should be added here
# after accountant review.
#
# Example:
# TAX_ADJUSTMENTS = {
#     "add_back_7W": [
#         {
#             "description": "Non-deductible entertainment",
#             "amount": 277.20,
#             "source": "Reviewed from P&L Entertainment account",
#         },
#     ],
#     "subtract_7F": [
#         {
#             "description": "Tax depreciation per fixed asset schedule",
#             "amount": 1500.00,
#             "source": "Fixed asset workpaper",
#         },
#     ],
# }

TAX_ADJUSTMENTS = {
    "add_back_7W": [],
    "add_back_7D": [],
    "add_back_7B": [],
    "subtract_7X": [],
    "subtract_7F": [],
    "subtract_7Z": [],
    "subtract_7I": [],
    "subtract_7Y": [],
    "subtract_7Q": [],
    "subtract_7R": [],
}
