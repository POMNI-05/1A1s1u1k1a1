# v1_selenium/itr_rules.py
"""Account labelling and Item 7 tax-workpaper rule metadata."""

from __future__ import annotations

import re
from typing import Iterable


TAX_RATES = {"base_rate_entity": 0.25, "general": 0.30}

RD_OFFSET_RATES = {"refundable": 0.435, "non_refundable": 0.385}

SMALL_BUSINESS_THRESHOLDS = {
    "aggregated_turnover": 10_000_000,
    "base_rate_entity_turnover": 50_000_000,
    "rd_refundable_turnover": 20_000_000,
    "instant_asset_writeoff": 20_000,
}


ITEM_7_LABELS = {
    "7T": {"name": "Total profit or loss", "direction": "base", "active": True},
    "7A": {"name": "Net capital gain", "direction": "add", "active": True},
    "7B": {"name": "Other assessable income", "direction": "add", "active": True},
    "7D": {"name": "R&D expenditure in accounts", "direction": "add", "active": True},
    "7W": {"name": "Non-deductible expenses", "direction": "add", "active": True},
    "7F": {"name": "Decline in value", "direction": "subtract", "active": True},
    "7I": {"name": "Capital works", "direction": "subtract", "active": True},
    "7Q": {"name": "Non-assessable income", "direction": "subtract", "active": True},
    "7R": {"name": "Tax losses deducted", "direction": "subtract", "active": True},
    "7X": {"name": "Other deductible expenses", "direction": "subtract", "active": True},
    "7Y": {"name": "Build-to-rent 4% capital works", "direction": "subtract", "active": True},
    "7Z": {"name": "Section 40-880 deduction", "direction": "subtract", "active": True},
    "7J": {"name": "Small business skills/training boost", "active": False, "removed_in": "2025"},
    "7K": {"name": "Small business energy incentive", "active": False, "removed_in": "2025"},
}


WORKSHEET_2 = {
    "add_back_7B": {"label": "7B", "direction": "add", "heading": "Other assessable income"},
    "add_back_7D": {"label": "7D", "direction": "add", "heading": "R&D expenditure in accounts"},
    "add_back_7W": {"label": "7W", "direction": "add", "heading": "Non-deductible expenses"},
    "subtract_7F": {"label": "7F", "direction": "subtract", "heading": "Decline in value"},
    "subtract_7I": {"label": "7I", "direction": "subtract", "heading": "Capital works"},
    "subtract_7Q": {"label": "7Q", "direction": "subtract", "heading": "Non-assessable income"},
    "subtract_7R": {"label": "7R", "direction": "subtract", "heading": "Tax losses deducted"},
    "subtract_7X": {"label": "7X", "direction": "subtract", "heading": "Other deductible expenses"},
    "subtract_7Y": {"label": "7Y", "direction": "subtract", "heading": "Build-to-rent capital works"},
    "subtract_7Z": {"label": "7Z", "direction": "subtract", "heading": "Section 40-880 deduction"},
}


# Tuple format:
# patterns, itr_ref, itr_label, treatment, confidence, review_note, reason, recon_itr_ref
#
# recon_itr_ref controls whether the P&L account auto-appears in the tax reconciliation table.
# Blank recon_itr_ref means: label it only; do not calculate tax adjustment from it.
FINANCIAL_LABEL_RULES = {
    "profit_and_loss": [
        ([r"sales", r"revenue", r"consulting income", r"trading income"], "6C", "Business income", "financial_label_only", "high", "", "Matched income account.", ""),
        ([r"interest income", r"interest received"], "6G", "Interest", "financial_label_only", "high", "Separate interest?", "Matched interest income.", ""),
        ([r"purchases", r"cost of sales", r"cost of goods sold"], "6A", "Cost of sales", "financial_label_only", "high", "Stock review?", "Matched cost of sales.", ""),
        ([r"wages", r"salaries", r"payroll"], "8D", "Wages", "financial_label_only", "high", "PAYG/super ok?", "Matched payroll expense.", ""),

        ([r"superannuation", r"\bsuper\b"], "8D / 7W", "Super", "review_only", "medium", "Check paid date before auto add-back.", "Super is deductible only if paid on time.", ""),
        ([r"annual leave", r"long service leave", r"provision"], "7W / 7X", "Provision", "review_only", "medium", "Check movement before posting.", "Provision timing may need add-back or deduction.", ""),

        ([r"rent", r"lease"], "8H", "Rent/lease", "financial_label_only", "medium", "Private/capital?", "Matched rent/lease.", ""),
        ([r"advertising", r"marketing"], "8R", "Other deductible", "financial_label_only", "medium", "", "Matched marketing expense.", ""),
        ([r"bank fee", r"merchant fee"], "8R", "Other deductible", "financial_label_only", "medium", "", "Matched bank/merchant fee.", ""),
        ([r"accounting", r"bookkeeping", r"consulting", r"professional fee"], "8R", "Professional fees", "financial_label_only", "medium", "Capital/private?", "Matched professional fees.", ""),

        ([r"legal"], "8R / 7W", "Legal", "review_only", "medium", "Confirm deductible nature.", "Legal costs may be deductible, capital or non-deductible.", ""),
        ([r"entertainment", r"meal", r"refreshment"], "7W", "Entertainment", "review_only", "medium", "Auto add-back; review if deductible.", "Entertainment is commonly non-deductible.", "7W"),
        ([r"depreciation", r"amortisation", r"amortization"], "7W", "Book depreciation/amortisation", "review_only", "medium", "Auto add-back; need tax depreciation schedule.", "Book depreciation/amortisation is usually added back.", "7W"),
        ([r"r&d", r"research and development", r"research & development"], "7D", "R&D", "review_only", "medium", "Auto add-back; need R&D schedule.", "R&D expenditure in accounts is added back at 7D.", "7D"),
        ([r"forex", r"foreign exchange", r"fx"], "7B / 7Q / 7X", "Forex", "review_only", "medium", "Review tax treatment.", "Forex can be assessable or deductible depending on nature.", ""),

        ([r"motor vehicle", r"vehicle", r"fuel"], "8R", "Motor vehicle", "review_only", "medium", "Private use?", "Vehicle costs may need private-use adjustment.", ""),
        ([r"travel", r"accommodation"], "8R", "Travel", "review_only", "medium", "Substantiation?", "Travel costs may need support/private review.", ""),
        ([r"telephone", r"internet", r"mobile"], "8R", "Phone/internet", "financial_label_only", "medium", "Private use?", "Matched communication costs.", ""),
    ],

    "balance_sheet": [
        ([r"bank", r"cash"], "BS", "Cash", "financial_label_only", "high", "", "Matched bank/cash.", ""),
        ([r"receivable", r"debtor"], "BS", "Receivables", "financial_label_only", "medium", "Bad debts?", "Matched receivable/debtor.", ""),
        ([r"gst", r"bas"], "BS", "GST", "review_only", "medium", "Agree BAS.", "GST/BAS should not be income tax payable.", ""),
        ([r"payg", r"superannuation payable", r"super payable"], "7W", "Payroll liability", "review_only", "medium", "Check paid date.", "Payroll liabilities can affect timing adjustments.", ""),
        ([r"annual leave", r"long service leave", r"provision"], "7W / 7X", "Provision", "review_only", "medium", "Check movement.", "Provision balances may support timing adjustments.", ""),
        ([r"loan", r"borrow", r"finance"], "BS", "Loans", "financial_label_only", "medium", "Related party?", "Matched loan/borrowing.", ""),
        ([r"retained earnings", r"current year earnings", r"equity"], "BS", "Equity", "financial_label_only", "medium", "", "Matched equity.", ""),
    ],
}


def validate_adjustment_label(label: str, description: str = "") -> None:
    info = ITEM_7_LABELS.get(label)
    if info is None:
        raise ValueError(f"Unknown ITR label {label!r} in adjustment {description!r}.")
    if not info.get("active", False):
        raise ValueError(f"ITR label {label!r} was removed in {info.get('removed_in', 'unknown year')}.")


def get_item7_direction(label: str) -> str:
    validate_adjustment_label(label)
    return ITEM_7_LABELS[label].get("direction", "")


def _rule_dict(rule_tuple: tuple) -> dict:
    patterns, ref, label, treatment, confidence, note, reason, recon_ref = rule_tuple
    return {
        "patterns": patterns,
        "ITR Ref": ref,
        "ITR Label": label,
        "Treatment": treatment,
        "Confidence": confidence,
        "Review Note": note,
        "Label Reason": reason,
        "Recon ITR Ref": recon_ref,
    }


def _match_rules(text: str, rules: Iterable[tuple]) -> dict | None:
    for rule_tuple in rules:
        rule = _rule_dict(rule_tuple)
        if any(re.search(pattern, text) for pattern in rule["patterns"]):
            rule.pop("patterns", None)
            return rule
    return None


def match_financial_label(account_name: str, report_type: str, report_section: str = "") -> dict:
    text = str(account_name or "").strip().lower()
    section = str(report_section or "").strip().lower()

    matched = _match_rules(text, FINANCIAL_LABEL_RULES.get(report_type, []))
    if matched:
        return matched

    if report_type == "profit_and_loss":
        section_map = {
            "trading income": ("6C", "Business income", "Income review."),
            "income": ("6C", "Business income", "Income review."),
            "revenue": ("6C", "Business income", "Income review."),
            "cost of sales": ("6A", "Cost of sales", "Stock review?"),
            "cost of goods sold": ("6A", "Cost of sales", "Stock review?"),
            "operating expenses": ("8R", "Other deductible", "Deductible?"),
            "expenses": ("8R", "Other deductible", "Deductible?"),
            "other income": ("6R / 7Q", "Other income", "Assessable?"),
        }
        if section in section_map:
            ref, label, note = section_map[section]
            return {
                "ITR Ref": ref,
                "ITR Label": label,
                "Treatment": "review_only",
                "Confidence": "medium",
                "Review Note": note,
                "Label Reason": f"No keyword match; mapped from section {report_section!r}.",
                "Recon ITR Ref": "",
            }

    if report_type == "balance_sheet":
        if "asset" in section or section in {"bank", "fixed assets"}:
            return {"ITR Ref": "BS", "ITR Label": "BS asset", "Treatment": "review_only", "Confidence": "medium", "Review Note": "Classify?", "Label Reason": "Mapped from BS asset section.", "Recon ITR Ref": ""}
        if "liabilit" in section:
            return {"ITR Ref": "BS", "ITR Label": "BS liability", "Treatment": "review_only", "Confidence": "medium", "Review Note": "Tax-sensitive?", "Label Reason": "Mapped from BS liability section.", "Recon ITR Ref": ""}
        if section == "equity":
            return {"ITR Ref": "BS", "ITR Label": "Equity", "Treatment": "financial_label_only", "Confidence": "medium", "Review Note": "", "Label Reason": "Mapped from equity section.", "Recon ITR Ref": ""}

    return {
        "ITR Ref": "Review",
        "ITR Label": "Unmapped",
        "Treatment": "review_only",
        "Confidence": "low",
        "Review Note": "Map manually.",
        "Label Reason": "No keyword or section fallback matched.",
        "Recon ITR Ref": "",
    }


def match_account_to_itr(account_name: str, report_type: str) -> dict:
    result = match_financial_label(account_name, report_type)
    return {
        "itr_ref": result.get("ITR Ref", ""),
        "category": result.get("ITR Label", ""),
        "review_note": result.get("Review Note", ""),
        "decision_logic": result.get("Label Reason", ""),
    }