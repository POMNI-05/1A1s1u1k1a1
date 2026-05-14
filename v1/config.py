# v1/config.py
"""
Central configuration for the Xero workpaper pipeline.

Design rule:
- Raw Xero P&L and BS are source documents and are not recalculated or overwritten.
- cleaner.py only parses/chunks those reports into structured rows.
- itr_rules.py contains labelling and tax-reconciliation rule metadata.
- TAX_ADJUSTMENTS contains actual tax reconciliation amounts after review.
"""
from __future__ import annotations
import os
from itr_rules import TAX_RATES, RD_OFFSET_RATES, SMALL_BUSINESS_THRESHOLDS

# ---------------------------------------------------------------------------
# Paths
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
SHEET_RECONCILIATION = "Tax Reconciliation"

# ---------------------------------------------------------------------------
# Selenium settings (if using Selenium for download)
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
# Actual tax reconciliation inputs
# ---------------------------------------------------------------------------
# These are the ONLY amounts that change taxable income, apart from base profit.
# Labelling a P&L/BS account does NOT automatically adjust taxable income.
#
# Supports either:
#   {"description": "...", "amount": 100.00, "source": "Manual review"}
# or multi-period:
#   {"description": "...", "amounts": {"2026": 100.00, "2025": 50.00}}
#
# Example:
# TAX_ADJUSTMENTS["add_back_7W"].append({
#     "description": "Non-deductible entertainment",
#     "amounts": {"2026": 277.20, "2025": 0.00},
#     "source": "Accountant review of P&L Entertainment",
# })

TAX_ADJUSTMENTS = {
    "add_back_7B": [],
    "add_back_7W": [],
    "add_back_7D": [],
    "subtract_7Q": [],
    "subtract_7X": [],
    "subtract_7F": [],
    "subtract_7I": [],
    "subtract_7Z": [],
    "subtract_7Y": [],
    "subtract_7R": [],
}

# # Optional support schedules for the right-hand side of the workpaper.
# These are display/support only unless you also put amounts into TAX_ADJUSTMENTS.
# CARRY_FORWARD_LOSSES = []
    # Example:
    # CARRY_FORWARD_LOSSES = [
    #     {"year": "30-Jun-2024", "amount": 1032617.00, "used": 0.00, "source": "Prior year return"},
    # ]

CARRY_FORWARD_LOSSES_TEMPLATE = [
    {"Description": "30-Jun-21", "Amount": None},
    {"Description": "30-Jun-22", "Amount": None},
    {"Description": "30-Jun-23", "Amount": None},
    {"Description": "30-Jun-24", "Amount": None},
    {"Description": "Total Losses", "Amount": None},
]

# RD_BREAKDOWN = {
#     "eligible_spend": 0.0,
#     "expensed": 0.0,
#     "capitalised": 0.0,
#     "source": "Not provided",
# }

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