# v1_selenium/itr_rules.py
"""
ATO company tax return and workpaper mapping rules.

Two separate ideas are kept separate:
1. ACCOUNT_ITR_REFERENCE_MAP: account-name guidance for review only.
2. WORKSHEET_2: actual tax reconciliation adjustment labels and directions.

The annotated P&L/BS sheets should not automatically change taxable income.
Only configured TAX_ADJUSTMENTS affect taxable income.
"""

from __future__ import annotations

import re
from typing import Dict, List

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
ITEM_7_LABELS: Dict[str, dict] = {
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
        "description": "R&D expenses in accounts added back and claimed through R&D workflow.",
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
        "description": "Division 43 capital works deductions.",
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
        "description": "Accelerated 4% deduction for eligible build-to-rent developments.",
        "active": True,
        "added_in": "2025",
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
# Worksheet 2 categories - these control actual add/subtract direction
# ---------------------------------------------------------------------------
WORKSHEET_2: Dict[str, dict] = {
    "add_back_7W": {
        "label": "7W",
        "direction": "add",
        "heading": "Non-deductible expenses (Item 7W)",
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
        "heading": "R&D expenditure in accounts (Item 7D)",
        "examples": ["R&D expenses charged to accounts and claimed under the R&D schedule"],
    },
    "add_back_7B": {
        "label": "7B",
        "direction": "add",
        "heading": "Other assessable income not in accounts (Item 7B)",
        "examples": ["Assessable grants not in accounts", "Taxable forex gain not in accounts"],
    },
    "subtract_7X": {
        "label": "7X",
        "direction": "subtract",
        "heading": "Other deductible expenses (Item 7X)",
        "examples": ["Deductible expense not recorded in accounts", "Prior year provision paid this year"],
    },
    "subtract_7F": {
        "label": "7F",
        "direction": "subtract",
        "heading": "Decline in value - depreciating assets (Item 7F)",
        "examples": ["Tax depreciation per fixed asset schedule"],
    },
    "subtract_7Z": {
        "label": "7Z",
        "direction": "subtract",
        "heading": "Section 40-880 deduction (Item 7Z)",
        "examples": ["Business establishment costs deductible over five years"],
    },
    "subtract_7I": {
        "label": "7I",
        "direction": "subtract",
        "heading": "Capital works deductions (Item 7I)",
        "examples": ["Division 43 capital works deduction"],
    },
    "subtract_7Y": {
        "label": "7Y",
        "direction": "subtract",
        "heading": "Build to rent capital works - 4% (Item 7Y)",
        "examples": ["Eligible build-to-rent capital works deduction"],
    },
    "subtract_7Q": {
        "label": "7Q",
        "direction": "subtract",
        "heading": "Income in accounts not assessable (Item 7Q)",
        "examples": ["Exempt income", "Accounting gain not assessable"],
    },
    "subtract_7R": {
        "label": "7R",
        "direction": "subtract",
        "heading": "Tax losses deducted (Item 7R)",
        "examples": ["Prior year tax losses applied"],
    },
}

# ---------------------------------------------------------------------------
# Account mapping - review guidance only, not calculation logic
# ---------------------------------------------------------------------------
ACCOUNT_ITR_REFERENCE_MAP: Dict[str, List[dict]] = {
    "profit_and_loss": [
        {
            "patterns": [r"^sales$", r"^revenue$", r"^trading income$", r"^income$"],
            "itr_ref": "6B",
            "category": "Gross income",
            "review_note": "Usually included in accounting profit. Review ITR income disclosure.",
            "decision_logic": "Matched as income account by name. Guidance only; no tax adjustment created.",
        },
        {
            "patterns": [r"^interest income$", r"interest received"],
            "itr_ref": "6G",
            "category": "Interest income",
            "review_note": "Review whether separately disclosed as interest income.",
            "decision_logic": "Matched as interest income. Included in profit unless accountant adjusts.",
        },
        {
            "patterns": [r"^purchases$", r"^cost of sales$", r"^cost of goods sold$"],
            "itr_ref": "6A",
            "category": "Cost of sales",
            "review_note": "Review trading stock / cost of sales treatment.",
            "decision_logic": "Matched as cost of sales. Already included in accounting profit.",
        },
        {
            "patterns": [r"wages", r"salaries", r"payroll"],
            "itr_ref": "8D",
            "category": "Labour costs",
            "review_note": "Review PAYG, super, contractor split and unpaid super issues.",
            "decision_logic": "Matched as labour cost. Usually deductible but no automatic tax adjustment.",
        },
        {
            "patterns": [r"^rent$", r"lease"],
            "itr_ref": "8H",
            "category": "Rent / lease expense",
            "review_note": "Review lease/rent deductibility and private use if relevant.",
            "decision_logic": "Matched as expense account. Already included in accounting profit.",
        },
        {
            "patterns": [r"advertising", r"marketing"],
            "itr_ref": "8R",
            "category": "Advertising",
            "review_note": "Generally deductible, subject to review.",
            "decision_logic": "Matched as ordinary expense. No automatic add-back or deduction.",
        },
        {
            "patterns": [r"bank fee", r"merchant fee"],
            "itr_ref": "8R",
            "category": "Bank fees",
            "review_note": "Generally deductible, subject to review.",
            "decision_logic": "Matched as ordinary expense. No automatic add-back or deduction.",
        },
        {
            "patterns": [r"consult", r"accounting", r"bookkeeping", r"professional fee"],
            "itr_ref": "8R",
            "category": "Professional fees",
            "review_note": "Review capital/private/non-deductible portion if applicable.",
            "decision_logic": "Matched as professional fee. Review only; manual 7W if non-deductible.",
        },
        {
            "patterns": [r"legal"],
            "itr_ref": "8R / 7W",
            "category": "Legal expenses",
            "review_note": "Review whether deductible, capital, private, or non-deductible.",
            "decision_logic": "Flagged for accountant review. Manual 7W add-back only if needed.",
        },
        {
            "patterns": [r"entertainment"],
            "itr_ref": "7W review",
            "category": "Entertainment",
            "review_note": "Often partly or fully non-deductible. Review for add-back.",
            "decision_logic": "Flagged only. Add to add_back_7W manually if non-deductible.",
        },
        {
            "patterns": [r"depreciation", r"amortisation", r"amortization"],
            "itr_ref": "7W / 7F",
            "category": "Depreciation / amortisation",
            "review_note": "Usually add back accounting depreciation/amortisation and claim tax depreciation separately.",
            "decision_logic": "Requires fixed asset workpaper. No automatic adjustment from P&L alone.",
        },
        {
            "patterns": [r"motor vehicle", r"vehicle", r"fuel"],
            "itr_ref": "8R",
            "category": "Motor vehicle expenses",
            "review_note": "Review private-use adjustment and substantiation.",
            "decision_logic": "Matched as vehicle expense. Manual adjustment if private/non-deductible portion exists.",
        },
        {
            "patterns": [r"telephone", r"internet", r"mobile"],
            "itr_ref": "8R",
            "category": "Telephone and internet",
            "review_note": "Review private-use adjustment if relevant.",
            "decision_logic": "Matched as ordinary expense. No automatic tax adjustment.",
        },
        {
            "patterns": [r"travel", r"accommodation", r"freight", r"courier"],
            "itr_ref": "8R",
            "category": "Travel / freight",
            "review_note": "Review substantiation and private component if applicable.",
            "decision_logic": "Matched as expense account. Manual adjustment only if required.",
        },
        {
            "patterns": [r"^net profit", r"profit.*loss", r"total profit", r"current year earnings"],
            "itr_ref": "7T",
            "category": "Accounting profit/loss",
            "review_note": "Starting point for Item 7 reconciliation.",
            "decision_logic": "Used as base accounting profit where identified.",
        },
        {
            "patterns": [r"^total ", r"^gross profit$"],
            "itr_ref": "Check",
            "category": "Subtotal / total row",
            "review_note": "Subtotal rows are for checking and should not be manually mapped as accounts.",
            "decision_logic": "Detected as subtotal/total. Review only.",
        },
    ],
    "balance_sheet": [
        {
            "patterns": [r"bank", r"cash"],
            "itr_ref": "Assets",
            "category": "Cash assets",
            "review_note": "Balance sheet disclosure only, not Item 7 taxable income.",
            "decision_logic": "Matched as BS asset. Does not affect taxable income calculation.",
        },
        {
            "patterns": [r"receivable", r"debtor"],
            "itr_ref": "Assets",
            "category": "Receivables",
            "review_note": "Review collectability and GST/tax timing if relevant.",
            "decision_logic": "Matched as BS asset. Review only.",
        },
        {
            "patterns": [r"inventory", r"stock"],
            "itr_ref": "Assets",
            "category": "Trading stock",
            "review_note": "Review opening/closing trading stock treatment.",
            "decision_logic": "Matched as stock. May inform tax review but no automatic Item 7 adjustment.",
        },
        {
            "patterns": [r"payable", r"creditor"],
            "itr_ref": "Liabilities",
            "category": "Payables",
            "review_note": "Review unpaid accruals/provisions if material.",
            "decision_logic": "Matched as liability. Review only.",
        },
        {
            "patterns": [r"gst", r"bas"],
            "itr_ref": "Liabilities / Assets",
            "category": "GST balance",
            "review_note": "GST should not be treated as income tax payable.",
            "decision_logic": "Matched as GST. Review only.",
        },
        {
            "patterns": [r"payg", r"superannuation", r"super payable"],
            "itr_ref": "Liabilities / 7W review",
            "category": "Payroll liabilities",
            "review_note": "Unpaid super may require add-back at 7W.",
            "decision_logic": "Flagged for review. Manual 7W only if tax rule requires.",
        },
        {
            "patterns": [r"loan", r"borrow", r"finance"],
            "itr_ref": "Liabilities",
            "category": "Loans / borrowings",
            "review_note": "Review related party balances and interest deductibility if relevant.",
            "decision_logic": "Matched as liability. Review only.",
        },
        {
            "patterns": [r"retained earnings", r"current year earnings", r"equity"],
            "itr_ref": "Equity",
            "category": "Equity",
            "review_note": "Balance sheet check only.",
            "decision_logic": "Matched as equity. Does not directly affect taxable income calculation.",
        },
        {
            "patterns": [r"^total assets$", r"^total liabilities$", r"^total equity$", r"^net assets$"],
            "itr_ref": "BS Check",
            "category": "Balance sheet check",
            "review_note": "Used for review/checking, not directly Item 7.",
            "decision_logic": "Detected as BS total/check row.",
        },
    ],
}


def get_active_labels() -> List[str]:
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


def match_account_to_itr(account_name: str, report_type: str) -> dict:
    text = str(account_name or "").strip().lower()

    for rule in ACCOUNT_ITR_REFERENCE_MAP.get(report_type, []):
        for pattern in rule.get("patterns", []):
            if re.search(pattern, text):
                return {
                    "itr_ref": rule.get("itr_ref", ""),
                    "category": rule.get("category", ""),
                    "review_note": rule.get("review_note", ""),
                    "decision_logic": rule.get("decision_logic", "Matched by configured account-name rule."),
                }

    return {
        "itr_ref": "",
        "category": "Unmapped",
        "review_note": "Review and map manually if material.",
        "decision_logic": "No account-name rule matched. Left unmapped for accountant review.",
    }
