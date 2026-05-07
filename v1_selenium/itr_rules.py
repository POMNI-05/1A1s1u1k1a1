# v1_selenium/itr_rules.py
"""
ATO company tax return and workpaper mapping rules.

Important separation:
1. FINANCIAL_LABEL_RULES:
   Used only for labelling P&L / BS accounting entries in the workpaper.
   These labels do NOT automatically change taxable income.

2. WORKSHEET_2:
   Used for actual tax reconciliation adjustments.
   Only amounts in TAX_ADJUSTMENTS are included in taxable income calculation.
"""

from __future__ import annotations

import re


# ---------------------------------------------------------------------------
# Tax rates and thresholds
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
# Item 7 labels
# ---------------------------------------------------------------------------

ITEM_7_LABELS = {
    "7T": {
        "name": "Total profit or loss",
        "direction": "base",
        "description": "Accounting profit/loss before tax - starting point for reconciliation.",
        "active": True,
    },
    "7A": {
        "name": "Net capital gain",
        "direction": "add",
        "description": "Net capital gains not included in accounting profit.",
        "active": True,
    },
    "7B": {
        "name": "Other assessable income",
        "direction": "add",
        "description": "Assessable income not shown in accounts.",
        "active": True,
    },
    "7D": {
        "name": "R&D expenditure in accounts subject to R&D tax incentive",
        "direction": "add",
        "description": "Accounting expenditure subject to R&D tax incentive.",
        "active": True,
    },
    "7W": {
        "name": "Non-deductible expenses",
        "direction": "add",
        "description": "Expenses in accounts that are not deductible for tax.",
        "active": True,
    },
    "7F": {
        "name": "Deduction for decline in value of depreciating assets",
        "direction": "subtract",
        "description": "Tax depreciation / UCA deduction.",
        "active": True,
    },
    "7I": {
        "name": "Capital works deductions",
        "direction": "subtract",
        "description": "Division 43 capital works deduction.",
        "active": True,
    },
    "7Q": {
        "name": "Other income not included in assessable income",
        "direction": "subtract",
        "description": "Income in accounts that is not assessable.",
        "active": True,
    },
    "7X": {
        "name": "Other deductible expenses",
        "direction": "subtract",
        "description": "Tax deductions not recorded as accounting expenses.",
        "active": True,
    },
    "7Y": {
        "name": "Build to rent capital works deduction at 4%",
        "direction": "subtract",
        "description": "Accelerated build-to-rent capital works deduction.",
        "active": True,
    },
    "7Z": {
        "name": "Section 40-880 deduction",
        "direction": "subtract",
        "description": "Business-related capital expenditure deductible over five years.",
        "active": True,
    },
    "7R": {
        "name": "Tax losses deducted",
        "direction": "subtract",
        "description": "Prior year tax losses applied against current year taxable income.",
        "active": True,
    },

    # Historical / inactive labels kept so old files fail clearly.
    "7J": {
        "name": "Small business skills and training boost",
        "direction": "subtract",
        "description": "Removed label retained for historical files.",
        "active": False,
        "removed_in": "2025",
    },
    "7K": {
        "name": "Small business energy incentive",
        "direction": "subtract",
        "description": "Removed label retained for historical files.",
        "active": False,
        "removed_in": "2025",
    },
}


# ---------------------------------------------------------------------------
# Worksheet 2 categories
# These control actual add/subtract direction in tax reconciliation.
# ---------------------------------------------------------------------------

WORKSHEET_2 = {
    "add_back_7W": {
        "label": "7W",
        "direction": "add",
        "heading": "Non-deductible expenses",
        "examples": [
            "Non-deductible entertainment",
            "Penalties and fines",
            "Non-deductible legal costs",
            "Accounting depreciation if tax depreciation is claimed separately",
            "Accrued super not paid by the due date",
        ],
    },
    "add_back_7D": {
        "label": "7D",
        "direction": "add",
        "heading": "R&D expenditure in accounts",
        "examples": [
            "R&D expenditure charged to accounts and claimed under R&D tax incentive",
        ],
    },
    "add_back_7B": {
        "label": "7B",
        "direction": "add",
        "heading": "Other assessable income not in accounts",
        "examples": [
            "Assessable grants not in accounts",
            "Taxable forex gains not in accounts",
        ],
    },

    "subtract_7X": {
        "label": "7X",
        "direction": "subtract",
        "heading": "Other deductible expenses",
        "examples": [
            "Deductible expenses not recorded in accounts",
            "Prior year provisions paid this year",
            "Allowable superannuation fund payments",
        ],
    },
    "subtract_7F": {
        "label": "7F",
        "direction": "subtract",
        "heading": "Decline in value of depreciating assets",
        "examples": [
            "Tax depreciation per fixed asset schedule",
        ],
    },
    "subtract_7Z": {
        "label": "7Z",
        "direction": "subtract",
        "heading": "Section 40-880 deduction",
        "examples": [
            "Business establishment costs deductible over five years",
        ],
    },
    "subtract_7I": {
        "label": "7I",
        "direction": "subtract",
        "heading": "Capital works deductions",
        "examples": [
            "Division 43 capital works deduction",
        ],
    },
    "subtract_7Y": {
        "label": "7Y",
        "direction": "subtract",
        "heading": "Build to rent capital works deduction at 4%",
        "examples": [
            "Eligible build-to-rent capital works deduction",
        ],
    },
    "subtract_7Q": {
        "label": "7Q",
        "direction": "subtract",
        "heading": "Other income not included in assessable income",
        "examples": [
            "Exempt income",
            "Accounting gain not assessable",
            "Unrealised gains on fair value revaluation",
        ],
    },
    "subtract_7R": {
        "label": "7R",
        "direction": "subtract",
        "heading": "Tax losses deducted",
        "examples": [
            "Prior year tax losses applied",
        ],
    },
}


# ---------------------------------------------------------------------------
# Financial Data labelling rules
# These are guidance only. They do not affect taxable income calculation.
# ---------------------------------------------------------------------------

FINANCIAL_LABEL_RULES = {
    "profit_and_loss": [
        {
            "patterns": [r"sales", r"revenue", r"consulting income", r"trading income"],
            "itr_ref": "6C",
            "itr_label": "Gross income / business income",
            "treatment": "financial_label_only",
            "confidence": "high",
            "review_note": "",
            "reason": "Matched income/revenue account name.",
        },
        {
            "patterns": [r"interest income", r"interest received"],
            "itr_ref": "6G",
            "itr_label": "Interest income",
            "treatment": "financial_label_only",
            "confidence": "high",
            "review_note": "Check whether interest is separately disclosed.",
            "reason": "Matched interest income account.",
        },
        {
            "patterns": [r"purchases", r"cost of sales", r"cost of goods sold"],
            "itr_ref": "6A",
            "itr_label": "Cost of sales",
            "treatment": "financial_label_only",
            "confidence": "high",
            "review_note": "Review trading stock / cost of sales treatment if relevant.",
            "reason": "Matched cost of sales account.",
        },
        {
            "patterns": [r"wages", r"salaries", r"payroll"],
            "itr_ref": "8D",
            "itr_label": "Salary and wage expenses",
            "treatment": "financial_label_only",
            "confidence": "high",
            "review_note": "Review PAYG, super, contractor split if relevant.",
            "reason": "Matched wages/salary account.",
        },
        {
            "patterns": [r"superannuation", r"\bsuper\b"],
            "itr_ref": "8D / 7W review",
            "itr_label": "Superannuation expense",
            "treatment": "review_only",
            "confidence": "medium",
            "review_note": "Unpaid super may require add-back. Check payment timing.",
            "reason": "Superannuation may need timing review.",
        },
        {
            "patterns": [r"annual leave", r"long service leave", r"provision"],
            "itr_ref": "7W / 7X review",
            "itr_label": "Leave provision / accrual",
            "treatment": "review_only",
            "confidence": "medium",
            "review_note": "Provision movements may require tax reconciliation adjustment.",
            "reason": "Leave/provision accounts are timing-sensitive.",
        },
        {
            "patterns": [r"rent", r"lease"],
            "itr_ref": "8H",
            "itr_label": "Rent / lease expense",
            "treatment": "financial_label_only",
            "confidence": "medium",
            "review_note": "Review private or capital component if relevant.",
            "reason": "Matched rent/lease account.",
        },
        {
            "patterns": [r"advertising", r"marketing"],
            "itr_ref": "8R",
            "itr_label": "Other deductible expense",
            "treatment": "financial_label_only",
            "confidence": "medium",
            "review_note": "",
            "reason": "Matched ordinary operating expense.",
        },
        {
            "patterns": [r"bank fee", r"merchant fee"],
            "itr_ref": "8R",
            "itr_label": "Other deductible expense",
            "treatment": "financial_label_only",
            "confidence": "medium",
            "review_note": "",
            "reason": "Matched bank/merchant fee account.",
        },
        {
            "patterns": [r"accounting", r"bookkeeping", r"consulting", r"professional fee"],
            "itr_ref": "8R",
            "itr_label": "Professional fees",
            "treatment": "financial_label_only",
            "confidence": "medium",
            "review_note": "Review capital/private/non-deductible portion if relevant.",
            "reason": "Matched professional fee account.",
        },
        {
            "patterns": [r"legal"],
            "itr_ref": "8R / 7W review",
            "itr_label": "Legal expenses",
            "treatment": "review_only",
            "confidence": "medium",
            "review_note": "Legal costs may be deductible, capital, private, or non-deductible. Review required.",
            "reason": "Legal expenses depend on nature of cost.",
        },
        {
            "patterns": [r"entertainment", r"meal", r"refreshment"],
            "itr_ref": "7W review",
            "itr_label": "Potential non-deductible entertainment",
            "treatment": "review_only",
            "confidence": "medium",
            "review_note": "Entertainment may be partly or fully non-deductible. Manual add-back only if confirmed.",
            "reason": "Entertainment often requires deductibility review.",
        },
        {
            "patterns": [r"depreciation", r"amortisation", r"amortization"],
            "itr_ref": "7W / 7F review",
            "itr_label": "Book depreciation / amortisation",
            "treatment": "review_only",
            "confidence": "medium",
            "review_note": "Accounting depreciation may be added back; tax depreciation comes from fixed asset schedule.",
            "reason": "Book depreciation and tax depreciation are different calculations.",
        },
        {
            "patterns": [r"r&d", r"research and development", r"research & development"],
            "itr_ref": "7D review",
            "itr_label": "R&D expenditure",
            "treatment": "review_only",
            "confidence": "medium",
            "review_note": "R&D expenditure may need separate R&D schedule and Item 7D add-back.",
            "reason": "R&D accounts require separate tax incentive review.",
        },
        {
            "patterns": [r"forex", r"foreign exchange", r"fx"],
            "itr_ref": "7B / 7Q / 7X review",
            "itr_label": "Foreign exchange gain/loss",
            "treatment": "review_only",
            "confidence": "medium",
            "review_note": "Forex treatment may differ between accounting and tax.",
            "reason": "Forex accounts can require tax reconciliation treatment.",
        },
        {
            "patterns": [r"motor vehicle", r"vehicle", r"fuel"],
            "itr_ref": "8R review",
            "itr_label": "Motor vehicle expenses",
            "treatment": "review_only",
            "confidence": "medium",
            "review_note": "Review private-use adjustment and substantiation.",
            "reason": "Vehicle expenses may have private-use component.",
        },
        {
            "patterns": [r"travel", r"accommodation"],
            "itr_ref": "8R review",
            "itr_label": "Travel expenses",
            "treatment": "review_only",
            "confidence": "medium",
            "review_note": "Review substantiation/private component.",
            "reason": "Travel accounts can require review.",
        },
        {
            "patterns": [r"telephone", r"internet", r"mobile"],
            "itr_ref": "8R review",
            "itr_label": "Telephone and internet",
            "treatment": "financial_label_only",
            "confidence": "medium",
            "review_note": "Review private-use adjustment if relevant.",
            "reason": "Matched phone/internet account.",
        },
    ],

    "balance_sheet": [
        {
            "patterns": [r"bank", r"cash"],
            "itr_ref": "BS",
            "itr_label": "Cash assets",
            "treatment": "financial_label_only",
            "confidence": "high",
            "review_note": "",
            "reason": "Matched bank/cash account.",
        },
        {
            "patterns": [r"receivable", r"debtor"],
            "itr_ref": "BS",
            "itr_label": "Receivables",
            "treatment": "financial_label_only",
            "confidence": "medium",
            "review_note": "Review bad debts / collectability if material.",
            "reason": "Matched receivable/debtor account.",
        },
        {
            "patterns": [r"gst", r"bas"],
            "itr_ref": "BS review",
            "itr_label": "GST balance",
            "treatment": "review_only",
            "confidence": "medium",
            "review_note": "GST should not be treated as income tax payable.",
            "reason": "Matched GST/BAS balance.",
        },
        {
            "patterns": [r"payg", r"superannuation payable", r"super payable"],
            "itr_ref": "7W review",
            "itr_label": "Payroll liability",
            "treatment": "review_only",
            "confidence": "medium",
            "review_note": "Unpaid super may require add-back. Check payment timing.",
            "reason": "Payroll liabilities may affect tax adjustment review.",
        },
        {
            "patterns": [r"annual leave", r"long service leave", r"provision"],
            "itr_ref": "7W / 7X review",
            "itr_label": "Provision / leave liability",
            "treatment": "review_only",
            "confidence": "medium",
            "review_note": "Provision movement may require tax reconciliation adjustment.",
            "reason": "Provision balances may not be deductible until paid/incurred for tax.",
        },
        {
            "patterns": [r"loan", r"borrow", r"finance"],
            "itr_ref": "BS review",
            "itr_label": "Loans / borrowings",
            "treatment": "financial_label_only",
            "confidence": "medium",
            "review_note": "Review related-party balances and interest treatment if relevant.",
            "reason": "Matched loan/borrowing account.",
        },
        {
            "patterns": [r"retained earnings", r"current year earnings", r"equity"],
            "itr_ref": "BS",
            "itr_label": "Equity",
            "treatment": "financial_label_only",
            "confidence": "medium",
            "review_note": "",
            "reason": "Matched equity account.",
        },
    ],
}


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def get_active_labels() -> list[str]:
    return [label for label, info in ITEM_7_LABELS.items() if info.get("active")]


def get_label_info(label: str) -> dict:
    if label not in ITEM_7_LABELS:
        raise KeyError(f"ITR label '{label}' not found.")
    return ITEM_7_LABELS[label]


def validate_adjustment_label(label: str, description: str = "") -> None:
    if label not in ITEM_7_LABELS:
        raise ValueError(f"Unknown ITR label '{label}' in adjustment '{description}'.")

    if not ITEM_7_LABELS[label].get("active", False):
        removed = ITEM_7_LABELS[label].get("removed_in", "unknown year")
        raise ValueError(
            f"ITR label '{label}' ({ITEM_7_LABELS[label]['name']}) was removed in {removed}. "
            f"Update adjustment '{description}'."
        )


def match_financial_label(account_name: str, report_type: str) -> dict:
    """
    Match an accounting entry to an ITR financial label.

    This is guidance only.
    It does not create tax reconciliation adjustments.
    """
    text = str(account_name or "").strip().lower()

    for rule in FINANCIAL_LABEL_RULES.get(report_type, []):
        for pattern in rule.get("patterns", []):
            if re.search(pattern, text):
                return {
                    "ITR Ref": rule.get("itr_ref", ""),
                    "ITR Label": rule.get("itr_label", ""),
                    "Treatment": rule.get("treatment", "financial_label_only"),
                    "Confidence": rule.get("confidence", ""),
                    "Review Note": rule.get("review_note", ""),
                    "Label Reason": rule.get("reason", "Matched by configured financial label rule."),
                }

    return {
        "ITR Ref": "",
        "ITR Label": "Unmapped",
        "Treatment": "review_only",
        "Confidence": "low",
        "Review Note": "No ITR rule matched. Review manually if material.",
        "Label Reason": "No configured financial label rule matched this account name.",
    }


# Backward-compatible alias, in case older files still import this.
def match_account_to_itr(account_name: str, report_type: str) -> dict:
    result = match_financial_label(account_name, report_type)
    return {
        "itr_ref": result.get("ITR Ref", ""),
        "category": result.get("ITR Label", ""),
        "review_note": result.get("Review Note", ""),
        "decision_logic": result.get("Label Reason", ""),
    }