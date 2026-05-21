# v1/itr_metadata.py
"""Static ATO / Company tax return metadata.

This file should be reviewed annually as part of the Yun Wei operations
ATO update process.

Keep here:
- tax rates
- thresholds
- Item 7 label metadata
- worksheet reconciliation label mapping
- Items 8-25 return template metadata

Do NOT put Xero account-name matching logic here.
"""

from __future__ import annotations


# ---------------------------------------------------------------------------
# A. Tax rates and thresholds
# ---------------------------------------------------------------------------

TAX_RATES = {
    "base_rate_entity": 0.25,
    "general": 0.30,
}

RD_OFFSET_RATES = {
    "refundable": 0.435,
    "non_refundable": 0.385,
}

SMALL_BUSINESS_THRESHOLDS = {
    "aggregated_turnover": 10_000_000,
    "base_rate_entity_turnover": 50_000_000,
    "rd_refundable_turnover": 20_000_000,
    "instant_asset_writeoff": 20_000,
}


# ---------------------------------------------------------------------------
# B. Item 7 tax reconciliation labels
# ---------------------------------------------------------------------------
# name           = human-readable return label description
# direction      = base / add / subtract
# active         = whether this label is currently allowed
# auto_supported = whether automation can populate this safely
# removed_in     = income year removed, if not active

ITEM_7_LABELS = {
    "7T": {
        "name": "Total profit or loss",
        "direction": "base",
        "active": True,
        "auto_supported": True,
    },

    # Add-back / assessable items
    "7A": {
        "name": "Net capital gain",
        "direction": "add",
        "active": True,
        "auto_supported": False,
    },
    "7B": {
        "name": "Other assessable income",
        "direction": "add",
        "active": True,
        "auto_supported": True,
    },
    "7C": {
        "name": "Section 46FA deductions",
        "direction": "add",
        "active": True,
        "auto_supported": False,
    },
    "7D": {
        "name": "R&D expenditure in accounts",
        "direction": "add",
        "active": True,
        "auto_supported": True,
    },
    "7E": {
        "name": "Australian franking credits from a New Zealand franking company",
        "direction": "add",
        "active": True,
        "auto_supported": False,
    },
    "7U": {
        "name": "Add back other items",
        "direction": "add",
        "active": True,
        "auto_supported": False,
    },
    "7W": {
        "name": "Non-deductible expenses",
        "direction": "add",
        "active": True,
        "auto_supported": True,
    },
    "7Y": {
        "name": "Build-to-rent capital works deduction at 4%",
        "direction": "add",
        "active": True,
        "auto_supported": False,
        "review_required": True,
    },

    # Subtraction / deduction items
    "7F": {
        "name": "Deduction for decline in value",
        "direction": "subtract",
        "active": True,
        "auto_supported": True,
    },
    "7H": {
        "name": "Deduction for project pool",
        "direction": "subtract",
        "active": True,
        "auto_supported": False,
    },
    "7I": {
        "name": "Capital works deductions",
        "direction": "subtract",
        "active": True,
        "auto_supported": True,
    },
    "7N": {
        "name": "Landcare operations and deduction for decline in value of water facility",
        "direction": "subtract",
        "active": True,
        "auto_supported": False,
    },
    "7O": {
        "name": "Deduction for environmental protection expenses",
        "direction": "subtract",
        "active": True,
        "auto_supported": False,
    },
    "7Q": {
        "name": "Non-assessable income",
        "direction": "subtract",
        "active": True,
        "auto_supported": True,
    },
    "7R": {
        "name": "Tax losses deducted",
        "direction": "subtract",
        "active": True,
        "auto_supported": True,
    },
    "7S": {
        "name": "Tax losses transferred in",
        "direction": "subtract",
        "active": True,
        "auto_supported": False,
    },
    "7V": {
        "name": "Exempt income",
        "direction": "subtract",
        "active": True,
        "auto_supported": False,
    },
    "7X": {
        "name": "Other deductible expenses",
        "direction": "subtract",
        "active": True,
        "auto_supported": True,
    },
    "7Z": {
        "name": "Section 40-880 deduction",
        "direction": "subtract",
        "active": True,
        "auto_supported": True,
    },

    # Template/special labels from pasted ITR layout.
    # Keep as active template rows, but do not auto-populate until accountant-reviewed.
    "7C46": {
        "name": "Section 46 deductions / special disclosure item",
        "direction": "add",
        "active": True,
        "auto_supported": False,
    },
    "7U-F": {
        "name": "Special Item 7U disclosure field",
        "direction": "subtract",
        "active": True,
        "auto_supported": False,
    },
    "7E-i": {
        "name": "Special Item 7E information field",
        "direction": "add",
        "active": True,
        "auto_supported": False,
    },
    "7W-T": {
        "name": "Special Item 7W total / information field",
        "direction": "add",
        "active": True,
        "auto_supported": False,
    },

    # Removed labels
    "7J": {
        "name": "Small business skills and training boost",
        "active": False,
        "removed_in": "2025",
        "auto_supported": False,
    },
    "7K": {
        "name": "Small business energy incentive",
        "active": False,
        "removed_in": "2025",
        "auto_supported": False,
    },
}


# ---------------------------------------------------------------------------
# C. Tax reconciliation worksheet mapping
# ---------------------------------------------------------------------------

WORKSHEET_2 = {
    "add_back_7B": {
        "label": "7B",
        "direction": "add",
        "heading": "Other assessable income",
    },
    "add_back_7D": {
        "label": "7D",
        "direction": "add",
        "heading": "R&D expenditure in accounts",
    },
    "add_back_7W": {
        "label": "7W",
        "direction": "add",
        "heading": "Non-deductible expenses",
    },
    "add_back_7Y": {
        "label": "7Y",
        "direction": "add",
        "heading": "Build-to-rent capital works deduction at 4%",
    },

    "subtract_7F": {
        "label": "7F",
        "direction": "subtract",
        "heading": "Deduction for decline in value",
    },
    "subtract_7I": {
        "label": "7I",
        "direction": "subtract",
        "heading": "Capital works deductions",
    },
    "subtract_7Q": {
        "label": "7Q",
        "direction": "subtract",
        "heading": "Non-assessable income",
    },
    "subtract_7R": {
        "label": "7R",
        "direction": "subtract",
        "heading": "Tax losses deducted",
    },
    "subtract_7X": {
        "label": "7X",
        "direction": "subtract",
        "heading": "Other deductible expenses",
    },
    "subtract_7Z": {
        "label": "7Z",
        "direction": "subtract",
        "heading": "Section 40-880 deduction",
    },
}


# ---------------------------------------------------------------------------
# D. Items 8-25 template metadata
# ---------------------------------------------------------------------------
# This is deliberately metadata-only.
# It is for printing / validating the company tax return workpaper layout.
# It should not create tax adjustments by itself.
# ---------------------------------------------------------------------------
# D. Item 8 - Financial and other information metadata
# ---------------------------------------------------------------------------
# Metadata only.
# This file says what the return labels are and whether automation may populate them.
# It does not decide how Xero account names map to labels.

ITEM8_AUTOMATION_POLICY = {
    "auto_safe": {
        "description": "Can usually be populated from clear P&L/BS accounts or total rows.",
        "highlight_default": False,
    },
    "review": {
        "description": "Can be detected, but should be highlighted for accountant review.",
        "highlight_default": True,
    },
    "manual": {
        "description": "Template-only unless a later schedule/calculation module is built.",
        "highlight_default": True,
    },
    "support_only": {
        "description": "Useful workpaper support row, but not a return label amount by itself.",
        "highlight_default": False,
    },
}

ITEM_8_LABELS = {
    # ------------------------------------------------------------------
    # Stock / trading
    # ------------------------------------------------------------------
    "8N": {
        "item": 8,
        "label": "N",
        "description": "Opening stock",
        "entry_type": "amount",
        "source": "Prior year closing stock / stock schedule",
        "automation_status": "manual",
        "auto_supported": False,
        "review_note": "Use prior year closing stock or stock schedule. Do not infer from current-year P&L only.",
    },
    "8S": {
        "item": 8,
        "label": "S",
        "description": "Purchases and other costs",
        "entry_type": "amount",
        "source": "P&L cost of sales / purchases / direct costs",
        "automation_status": "review",
        "auto_supported": False,
        "review_note": "Review COGS composition. Include purchases/direct costs only where appropriate.",
    },
    "8B": {
        "item": 8,
        "label": "B",
        "description": "Closing stock",
        "entry_type": "amount",
        "source": "Balance Sheet stock / inventory / stock schedule",
        "automation_status": "review",
        "auto_supported": False,
        "review_note": "Check stock valuation method, obsolete stock and tax treatment.",
    },

    # ------------------------------------------------------------------
    # Balance Sheet totals and control accounts
    # ------------------------------------------------------------------
    "8C": {
        "item": 8,
        "label": "C",
        "description": "Trade debtors",
        "entry_type": "amount",
        "source": "Balance Sheet accounts receivable / debtors",
        "automation_status": "auto_safe",
        "auto_supported": True,
        "review_note": "Confirm debtor balance at year end if unusual.",
    },
    "8D": {
        "item": 8,
        "label": "D",
        "description": "All current assets",
        "entry_type": "amount",
        "source": "Balance Sheet total current assets",
        "automation_status": "auto_safe",
        "auto_supported": True,
        "review_note": "",
    },
    "8E": {
        "item": 8,
        "label": "E",
        "description": "Total assets",
        "entry_type": "amount",
        "source": "Balance Sheet total assets",
        "automation_status": "auto_safe",
        "auto_supported": True,
        "review_note": "",
    },
    "8F": {
        "item": 8,
        "label": "F",
        "description": "Trade creditors",
        "entry_type": "amount",
        "source": "Balance Sheet accounts payable / creditors",
        "automation_status": "auto_safe",
        "auto_supported": True,
        "review_note": "Confirm creditor balance at year end if unusual.",
    },
    "8G": {
        "item": 8,
        "label": "G",
        "description": "All current liabilities",
        "entry_type": "amount",
        "source": "Balance Sheet total current liabilities",
        "automation_status": "auto_safe",
        "auto_supported": True,
        "review_note": "",
    },
    "8H": {
        "item": 8,
        "label": "H",
        "description": "Total liabilities",
        "entry_type": "amount",
        "source": "Balance Sheet total liabilities",
        "automation_status": "auto_safe",
        "auto_supported": True,
        "review_note": "",
    },
    "8J": {
        "item": 8,
        "label": "J",
        "description": "Total debt",
        "entry_type": "amount",
        "source": "Balance Sheet loans / borrowings / finance liabilities / debt schedule",
        "automation_status": "review",
        "auto_supported": False,
        "review_note": "Confirm whether loans, HP, chattel mortgage, leases and related-party debts should be included.",
    },

    # ------------------------------------------------------------------
    # Dividends / franking / associated persons / foreign income
    # ------------------------------------------------------------------
    "8K": {
        "item": 8,
        "label": "K",
        "description": "Commercial debt forgiveness",
        "entry_type": "amount",
        "source": "Manual tax schedule",
        "automation_status": "manual",
        "auto_supported": False,
        "review_note": "Manual review required.",
    },
    "8J-F": {
        "item": 8,
        "label": "J-F",
        "description": "Franked dividends paid",
        "entry_type": "amount",
        "source": "Dividend / franking schedule",
        "automation_status": "manual",
        "auto_supported": False,
        "review_note": "Use dividend/franking schedule.",
    },
    "8K-U": {
        "item": 8,
        "label": "K-U",
        "description": "Unfranked dividends paid",
        "entry_type": "amount",
        "source": "Dividend schedule",
        "automation_status": "manual",
        "auto_supported": False,
        "review_note": "Use dividend schedule.",
    },
    "8P": {
        "item": 8,
        "label": "P",
        "description": "Opening franking account balance",
        "entry_type": "amount",
        "source": "Franking account reconciliation",
        "automation_status": "manual",
        "auto_supported": False,
        "review_note": "Use franking account reconciliation.",
    },
    "8M": {
        "item": 8,
        "label": "M",
        "description": "Closing franking account balance",
        "entry_type": "amount",
        "source": "Franking account reconciliation",
        "automation_status": "manual",
        "auto_supported": False,
        "review_note": "Use franking account reconciliation.",
    },
    "8X": {
        "item": 8,
        "label": "X",
        "description": "Aggregated turnover range",
        "entry_type": "code",
        "source": "Aggregated turnover calculation",
        "automation_status": "manual",
        "auto_supported": False,
        "valid_codes": {
            "A": "< $2M",
            "B": "$2M to < $10M",
            "C": "$10M to < $50M",
            "D": "$50M to < $250M",
            "E": "$250M to < $1B",
            "F": "$1B or more",
        },
        "review_note": "Requires aggregated turnover calculation, including connected/affiliate entities where relevant.",
    },
    "8Y": {
        "item": 8,
        "label": "Y",
        "description": "Aggregated turnover actual figure",
        "entry_type": "amount",
        "source": "Aggregated turnover calculation",
        "automation_status": "manual",
        "auto_supported": False,
        "review_note": "Do not use ordinary sales alone unless aggregated turnover has been reviewed.",
    },
    "8H-e": {
        "item": 8,
        "label": "H-e",
        "description": "Excess franking offsets",
        "entry_type": "amount",
        "source": "Calculation statement / tax offset workpaper",
        "automation_status": "manual",
        "auto_supported": False,
        "review_note": "Transfer from calculation statement if applicable.",
    },
    "8D-sw": {
        "item": 8,
        "label": "D-sw",
        "description": "Total salary and wage expenses",
        "entry_type": "amount",
        "source": "P&L payroll / wages / salaries accounts",
        "automation_status": "auto_safe",
        "auto_supported": True,
        "review_note": "Check PAYG and super where relevant.",
    },
    "8Q": {
        "item": 8,
        "label": "Q",
        "description": "Payments to associated persons",
        "entry_type": "amount",
        "source": "Related-party / associated-persons review",
        "automation_status": "review",
        "auto_supported": False,
        "review_note": "Requires related-party review. Do not infer from ordinary wages or contractor accounts alone.",
    },
    "8G-fi": {
        "item": 8,
        "label": "G-fi",
        "description": "Gross foreign income",
        "entry_type": "amount",
        "source": "Foreign income schedule",
        "automation_status": "manual",
        "auto_supported": False,
        "review_note": "Manual foreign income review required.",
    },
    "8R": {
        "item": 8,
        "label": "R",
        "description": "Net foreign income",
        "entry_type": "amount",
        "source": "Foreign income schedule",
        "automation_status": "manual",
        "auto_supported": False,
        "review_note": "Manual foreign income review required.",
    },
}


# ---------------------------------------------------------------------------
# E. Metadata helpers
# ---------------------------------------------------------------------------

def validate_adjustment_label(label: str, description: str = "") -> None:
    info = ITEM_7_LABELS.get(label)

    if info is None:
        raise ValueError(f"Unknown ITR label {label!r} in adjustment {description!r}.")

    if not info.get("active", False):
        raise ValueError(
            f"ITR label {label!r} was removed in "
            f"{info.get('removed_in', 'unknown year')}."
        )


def get_item7_direction(label: str) -> str:
    validate_adjustment_label(label)
    return ITEM_7_LABELS[label].get("direction", "")