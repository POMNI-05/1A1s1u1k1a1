# v1_selenium/itr_rules.py
#
# ATO Company Tax Return — ITR label definitions and reconciliation rules
# Source: https://www.ato.gov.au/forms-and-instructions/company-tax-return-2025-instructions
#
# This file defines the STRUCTURE of the tax return.
# Client-specific adjustment values are configured in config.py via .env
# Update this file when the ATO publishes a new year's ITR instructions.
#
# Current: Company Tax Return 2025 (income year 2024-25), published 29 May 2025


# ── Item 7 Label Definitions ──────────────────────────────────────────────────
# Full label map for Item 7: Reconciliation to taxable income or loss
# "active" = currently on the 2025 ITR form
# "removed_in" = the year this label was removed (if applicable)

# update this dictionary when the ATO publishes new ITR instructions each year: 
    # Only touch itr_rules.py — update ITEM_7_LABELS, 
        # add new entries to WORKSHEET_2, 
        # flip active flags. config.py, reconciler.py, and 
        # everything else stays untouched.


ITEM_7_LABELS = {
    "7T": {
        "name":        "Total profit or loss",
        "direction":   "base",
        "description": "Accounting profit/loss before tax — starting point for reconciliation",
        "active":      True,
    },
    "7A": {
        "name":        "Net capital gain",
        "direction":   "add",
        "description": "Net capital gains not included in accounting profit",
        "active":      True,
    },
    "7B": {
        "name":        "Other assessable income",
        "direction":   "add",
        "description": "Assessable income not shown in accounts (forex gains, grants, etc.)",
        "active":      True,
    },
    "7D": {
        "name":        "R&D expenditure in accounts subject to R&D tax incentive",
        "direction":   "add",
        "description": "R&D costs expensed in accounts — added back here, claimed via R&D schedule",
        "active":      True,
    },
    "7W": {
        "name":        "Non-deductible expenses",
        "direction":   "add",
        "description": "Expenses in accounts not deductible for tax (accrued super, provisions, amortisation, etc.)",
        "active":      True,
    },
    "7F": {
        "name":        "Deduction for decline in value of depreciating assets",
        "direction":   "subtract",
        "description": "Tax depreciation — UCA/Division 40 deductions",
        "active":      True,
    },
    "7Q": {
        "name":        "Other income not included in assessable income",
        "direction":   "subtract",
        "description": "Income in accounts that is NOT assessable (unrealised gains, exempt income)",
        "active":      True,
    },
    "7X": {
        "name":        "Other deductible expenses",
        "direction":   "subtract",
        "description": "Tax deductions not in accounting expenses (prior year provisions paid, allowable super, etc.)",
        "active":      True,
    },
    "7Z": {
        "name":        "Section 40-880 deduction",
        "direction":   "subtract",
        "description": "Business establishment/formation costs — 5yr straight-line deduction",
        "active":      True,
    },
    "7I": {
        "name":        "Capital works deductions",
        "direction":   "subtract",
        "description": "Division 43 capital works deductions",
        "active":      True,
    },
    "7Y": {
        "name":        "Build to rent capital works deduction at 4%",
        "direction":   "subtract",
        "description": "NEW 2024-25: Accelerated 4% deduction for eligible build-to-rent developments. "
                       "Also included at 7I — do NOT double-count in taxable income calculation.",
        "active":      True,
        "added_in":    "2025",
    },
    "7R": {
        "name":        "Tax losses deducted",
        "direction":   "subtract",
        "description": "Prior year carry-forward losses applied this year",
        "active":      True,
    },

    # ── Removed labels — kept for historical reference ────────────────────────
    "7J": {
        "name":        "Small business skills and training boost",
        "direction":   "subtract",
        "description": "20% bonus deduction on eligible training expenditure — REMOVED in 2025 ITR",
        "active":      False,
        "removed_in":  "2025",
    },
    "7K": {
        "name":        "Small business energy incentive",
        "direction":   "subtract",
        "description": "20% bonus deduction on eligible energy-efficient assets — REMOVED in 2025 ITR",
        "active":      False,
        "removed_in":  "2025",
    },
}


# ── Tax Rates (Company Tax Return 2025) ───────────────────────────────────────
TAX_RATES = {
    "base_rate_entity":     0.25,   # aggregated turnover < $50M, passive income <= 80%
    "general":              0.30,   # all other companies
}

# ── R&D Tax Incentive Offset Rates ───────────────────────────────────────────
RD_OFFSET_RATES = {
    "refundable":     0.435,   # aggregated turnover < $20M
    "non_refundable": 0.385,   # aggregated turnover >= $20M
}

# ── Small Business Thresholds (2024-25) ──────────────────────────────────────
SMALL_BUSINESS_THRESHOLDS = {
    "aggregated_turnover":        10_000_000,   # < $10M for SBE concessions
    "base_rate_entity_turnover":  50_000_000,   # < $50M for 25% rate
    "rd_refundable_turnover":     20_000_000,   # < $20M for refundable R&D offset
    "instant_asset_writeoff":     20_000,       # extended to 2024-25
}

# ── Worksheet 2 Categories ────────────────────────────────────────────────────
# Maps each adjustment category to its ITR label and direction
# Used by reconciler.py to build the working paper in correct ITR order

WORKSHEET_2 = {
    "add_back_7W": {
        "label":       "7W",
        "direction":   "add",
        "heading":     "Non-deductible expenses (Item 7W)",
        "examples":    [
            "Amortisation as per accounts (including goodwill)",
            "Superannuation charged in accounts (accrued, not yet paid)",
            "Net increase in provisions (annual leave, long service leave)",
            "Entertainment expenses — non-deductible portion",
            "Legal expenses — non-deductible portion",
            "Penalties and fines",
            "Unrealised losses on revaluation of assets",
            "Depreciation as per accounts (if not using SBE rules)",
        ],
    },
    "add_back_7D": {
        "label":       "7D",
        "direction":   "add",
        "heading":     "R&D expenditure in accounts (Item 7D)",
        "examples":    [
            "R&D costs expensed in accounts — gross amount",
            "Note: claimed separately via R&D Tax Incentive Schedule",
        ],
    },
    "add_back_7B": {
        "label":       "7B",
        "direction":   "add",
        "heading":     "Other assessable income not in accounts (Item 7B)",
        "examples":    [
            "Forex taxable gains",
            "Grants received not included in accounts",
            "Bad debts recovered not in accounts",
        ],
    },
    "subtract_7X": {
        "label":       "7X",
        "direction":   "subtract",
        "heading":     "Other deductible expenses (Item 7X)",
        "examples":    [
            "Allowable superannuation fund payments (prior year accruals now paid)",
            "Net decrease in provisions",
            "Tax deductible borrowing costs",
            "Forex taxable losses",
        ],
    },
    "subtract_7F": {
        "label":       "7F",
        "direction":   "subtract",
        "heading":     "Decline in value — depreciating assets (Item 7F)",
        "examples":    [
            "UCA tax depreciation — Division 40",
            "Software development pool",
            "Low-value pool deduction",
        ],
    },
    "subtract_7Z": {
        "label":       "7Z",
        "direction":   "subtract",
        "heading":     "Section 40-880 deduction (Item 7Z)",
        "examples":    [
            "Business establishment/formation costs — 5yr straight-line",
        ],
    },
    "subtract_7Y": {
        "label":       "7Y",
        "direction":   "subtract",
        "heading":     "Build to rent capital works — 4% (Item 7Y) [NEW 2024-25]",
        "examples":    [
            "Eligible build-to-rent development — accelerated 4% capital works deduction",
            "IMPORTANT: Also at 7I. Do not include in taxable income total.",
        ],
    },
    "subtract_7Q": {
        "label":       "7Q",
        "direction":   "subtract",
        "heading":     "Income in accounts not assessable (Item 7Q)",
        "examples":    [
            "Unrealised gains on revaluation of assets to fair value",
            "Exempt income",
            "Forex accounting profits (if not taxable)",
        ],
    },
    "subtract_7R": {
        "label":       "7R",
        "direction":   "subtract",
        "heading":     "Tax losses deducted (Item 7R)",
        "examples":    [
            "Prior year carry-forward losses applied against current year taxable income",
        ],
    },
}


def get_active_labels() -> list:
    """Return only labels currently active on the ITR form."""
    return [k for k, v in ITEM_7_LABELS.items() if v["active"]]


def get_label_info(label: str) -> dict:
    """Look up a label's metadata. Raises KeyError if not found."""
    if label not in ITEM_7_LABELS:
        raise KeyError(f"ITR label '{label}' not found. Check ITEM_7_LABELS.")
    return ITEM_7_LABELS[label]


def validate_adjustment(adjustment: dict):
    """
    Called by reconciler.py to validate each entry in TAX_ADJUSTMENTS
    before building the working paper.
    Raises ValueError if label is inactive or unknown.
    """
    label = adjustment.get("itr_label", "")
    if label not in ITEM_7_LABELS:
        raise ValueError(f"Unknown ITR label '{label}' in adjustment: {adjustment['description']}")
    if not ITEM_7_LABELS[label]["active"]:
        removed = ITEM_7_LABELS[label].get("removed_in", "unknown year")
        raise ValueError(
            f"ITR label '{label}' ({ITEM_7_LABELS[label]['name']}) was removed in {removed}. "
            f"Update adjustment: '{adjustment['description']}'"
        )