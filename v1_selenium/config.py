# v1_selenium/config.py  (tax section only — rest stays the same)

import os
from itr_rules import TAX_RATES, RD_OFFSET_RATES, SMALL_BUSINESS_THRESHOLDS

# tested code here -------

import os

USE_SELENIUM = False

# ── Base directories ────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DATA_DIR   = os.path.join(BASE_DIR, "data")

DOWNLOAD_DIR = DATA_DIR  # Selenium downloads go here by default for easy access by utils.py

OUTPUT_DIR = os.path.join(BASE_DIR, "output")
LOG_DIR    = os.path.join(BASE_DIR, "logs")

# ── Raw input files (used by cleaner.py) ─────────────────────
PL_RAW_PATH = os.path.join(DATA_DIR, "profit_and_loss_raw.xlsx")
BS_RAW_PATH = os.path.join(DATA_DIR, "balance_sheet_raw.xlsx")

# ── Final output file ────────────────────────────────────────
OUTPUT_PATH = os.path.join(OUTPUT_DIR, "xero_workpaper.xlsx")

# ── Sheet names ─────────────────────────────────────────────
SHEET_PL = "Profit and Loss"
SHEET_BS = "Balance Sheet"
SHEET_RECONCILIATION = "Reconciliation"



# end of tested code -------



# ── Tax Settings (rates pulled from itr_rules.py) ─────────────────────────────
BASE_RATE_ENTITY      = os.getenv("BASE_RATE_ENTITY", "true").lower() == "true"
TAX_RATE              = TAX_RATES["base_rate_entity"] if BASE_RATE_ENTITY else TAX_RATES["general"]

SMALL_BUSINESS_ENTITY = os.getenv("SMALL_BUSINESS_ENTITY", "false").lower() == "true"
INSTANT_ASSET_WRITEOFF_LIMIT = SMALL_BUSINESS_THRESHOLDS["instant_asset_writeoff"]

RD_ELIGIBLE           = os.getenv("RD_ELIGIBLE", "false").lower() == "true"
RD_REFUNDABLE         = os.getenv("RD_REFUNDABLE", "true").lower() == "true"
RD_OFFSET_RATE        = RD_OFFSET_RATES["refundable"] if RD_REFUNDABLE else RD_OFFSET_RATES["non_refundable"]

# ── Tax Adjustments (client fills these in per engagement) ────────────────────
TAX_ADJUSTMENTS = {
    "add_back_7W": [],
    "add_back_7D": [],
    "add_back_7B": [],
    "subtract_7X": [],
    "subtract_7F": [],
    "subtract_7Z": [],
    "subtract_7Y": [],
    "subtract_7Q": [],
    "subtract_7R": [],
}