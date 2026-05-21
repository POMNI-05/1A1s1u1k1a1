# v1/itr_rules.py
"""Account-name matching and ITR labelling logic.

Static ATO / ITR metadata lives in itr_metadata.py.

This file should answer:
- Given a Xero/accounting row name, what ITR label is the best match?
- Is that match high/medium/low confidence?
- Is it label-only, review-only, support-only, or tax-reconciliation relevant?

This file should NOT contain:
- tax rates
- ATO thresholds
- Item 7 master metadata
- Items 8-25 return templates
- worksheet layout metadata
"""

from __future__ import annotations

import re
from typing import Iterable


# ---------------------------------------------------------------------------
# A. Financial label rules
# ---------------------------------------------------------------------------
# Tuple format:
# (
#     patterns,
#     itr_ref,
#     itr_label,
#     treatment,
#     confidence,
#     review_note,
#     reason,
#     recon_itr_ref,
# )
#
# treatment:
# - financial_label_only = useful return label, but does not change taxable income
# - review_only          = accountant should review before using
# - support_only         = support/check row only, not a return label
#
# recon_itr_ref:
# - blank means do not include in tax reconciliation
# - non-blank means this P&L account may feed the tax reconciliation
# - only use non-blank where the rule is conservative enough for review workflow

FINANCIAL_LABEL_RULES = {
    "profit_and_loss": [
        # ------------------------------------------------------------------
        # Income
        # ------------------------------------------------------------------
        (
            [r"^sales$", r"\bsales\b", r"revenue", r"consulting income", r"trading income"],
            "6C",
            "Business income",
            "financial_label_only",
            "high",
            "",
            "Matched income account.",
            "",
        ),
        (
            [r"interest income", r"interest received"],
            "6G",
            "Interest income",
            "financial_label_only",
            "high",
            "Separate interest?",
            "Matched interest income.",
            "",
        ),
        (
            [r"gain.*disposal", r"profit.*disposal", r"gain.*sale.*asset"],
            "6F",
            "Disposal of assets",
            "review_only",
            "medium",
            "Confirm capital/revenue treatment.",
            "Matched gain on disposal of assets.",
            "",
        ),
        (
            [r"other income"],
            "6R",
            "Other gross income",
            "review_only",
            "medium",
            "Assessable? Review if non-assessable income should be 7Q.",
            "Matched other income.",
            "",
        ),

        # ------------------------------------------------------------------
        # Cost of sales
        # ------------------------------------------------------------------
        (
            [
                r"\bcogs\b",
                r"cost of sales",
                r"cost of goods sold",
                r"purchases",
                r"freight in", # a what ?? 
                r"freight out",
                r"packaging",
                r"stamp duty on acquisition",
            ],
            "6A",
            "Cost of sales",
            "financial_label_only",
            "high",
            "Stock review?",
            "Matched cost of sales / COGS account.",
            "",
        ),

        # ------------------------------------------------------------------
        # Payroll / employee costs
        # ------------------------------------------------------------------
        (
            [r"wages", r"salaries", r"payroll", r"staff salaries"],
            "8D-sw",
            "Total salary and wage expenses",
            "financial_label_only",
            "high",
            "PAYG/super ok?",
            "Matched payroll expense.",
            "",
        ),
        (
            [r"superannuation", r"\bsuper\b"],
            "6D / 7W",
            "Superannuation",
            "review_only",
            "medium",
            "Check paid date before auto add-back.",
            "Super is deductible only if paid on time.",
            "",
        ),
        (
            [r"annual leave", r"long service leave", r"provision"],
            "6S / 7W / 7X",
            "Leave/provision",
            "review_only",
            "medium",
            "Check movement before posting.",
            "Provision timing may need add-back or deduction.",
            "",
        ),

        # ------------------------------------------------------------------
        # Specific expenses
        # ------------------------------------------------------------------
        (
            [r"rent", r"lease"],
            "6H",
            "Rent/lease",
            "financial_label_only",
            "medium",
            "Private/capital?",
            "Matched rent/lease.",
            "",
        ),
        (
            [r"interest expense", r"loan interest", r"finance interest"],
            "6J / 8Q",
            "Interest expense",
            "review_only",
            "medium",
            "Confirm debt deduction disclosure.",
            "Matched interest expense.",
            "",
        ),
        (
            [r"depreciation", r"amortisation", r"amortization"],
            "6X / 7W",
            "Book depreciation/amortisation",
            "review_only",
            "medium",
            "Auto add-back; need tax depreciation schedule.",
            "Book depreciation/amortisation is usually added back.",
            "7W",
        ),
        (
            [r"r&d", r"research and development", r"research & development"],
            "7D",
            "R&D",
            "review_only",
            "medium",
            "Auto add-back; need R&D schedule.",
            "R&D expenditure in accounts is added back at 7D.",
            "7D",
        ),
        (
            [r"entertainment", r"meal", r"refreshment"],
            "7W",
            "Entertainment",
            "review_only",
            "medium",
            "Auto add-back; review if deductible.",
            "Entertainment is commonly non-deductible.",
            "7W",
        ),
        (
            [r"legal"],
            "8R / 7W",
            "Legal",
            "review_only",
            "medium",
            "Confirm deductible nature.",
            "Legal costs may be deductible, capital or non-deductible.",
            "",
        ),
        (
            [r"bank fee", r"merchant fee"],
            "8R",
            "Other deductible",
            "financial_label_only",
            "medium",
            "",
            "Matched bank/merchant fee.",
            "",
        ),
        (
            [r"accounting", r"bookkeeping", r"consulting", r"professional fee"],
            "8R",
            "Professional fees",
            "financial_label_only",
            "medium",
            "Capital/private?",
            "Matched professional fees.",
            "",
        ),
        (
            [r"advertising", r"marketing"],
            "6S",
            "Other expenses",
            "financial_label_only",
            "medium",
            "",
            "Matched marketing/advertising expense.",
            "",
        ),
        (
            [r"motor vehicle", r"vehicle", r"fuel"],
            "6Y",
            "Motor vehicle expenses",
            "review_only",
            "medium",
            "Private use?",
            "Vehicle costs may need private-use adjustment.",
            "",
        ),
        (
            [r"travel", r"accommodation"],
            "8R",
            "Travel",
            "review_only",
            "medium",
            "Substantiation?",
            "Travel costs may need support/private review.",
            "",
        ),
        (
            [r"telephone", r"internet", r"mobile"],
            "6S",
            "Other expenses",
            "financial_label_only",
            "medium",
            "Private use?",
            "Matched communication costs.",
            "",
        ),
        (
            [r"forex", r"foreign exchange", r"\bfx\b"],
            "7B / 7Q / 7X",
            "Forex",
            "review_only",
            "medium",
            "Review tax treatment.",
            "Forex can be assessable or deductible depending on nature.",
            "",
        ),
    ],

    "balance_sheet": [
        # ------------------------------------------------------------------
        # Company tax return Item 8 direct mappings
        # ------------------------------------------------------------------
        (
            [r"^total current assets$", r"^current assets$"],
            "8D",
            "All current assets",
            "financial_label_only",
            "high",
            "",
            "Mapped to Company tax return Item 8D All current assets.",
            "",
        ),
        (
            [r"^total assets$", r"^assets$"],
            "8E",
            "Total assets",
            "financial_label_only",
            "high",
            "",
            "Mapped to Company tax return Item 8E Total assets.",
            "",
        ),
        (
            [r"^total current liabilities$", r"^current liabilities$"],
            "8G",
            "All current liabilities",
            "financial_label_only",
            "high",
            "",
            "Mapped to Company tax return Item 8G All current liabilities.",
            "",
        ),
        (
            [r"^total liabilities$", r"^liabilities$"],
            "8H",
            "Total liabilities",
            "financial_label_only",
            "high",
            "",
            "Mapped to Company tax return Item 8H Total liabilities.",
            "",
        ),
        (
            [r"^trade debtors$", r"^debtors$", r"accounts receivable", r"trade receivable"],
            "8C",
            "Trade debtors",
            "financial_label_only",
            "medium",
            "Confirm debtor balance at year end.",
            "Mapped to Company tax return Item 8C Trade debtors.",
            "",
        ),
        (
            [r"^trade creditors$", r"^creditors$", r"accounts payable", r"trade payable"],
            "8F",
            "Trade creditors",
            "financial_label_only",
            "medium",
            "Confirm creditor balance at year end.",
            "Mapped to Company tax return Item 8F Trade creditors.",
            "",
        ),
        (
            [r"^total debt$", r"borrowings", r"loan", r"finance liability", r"chattel mortgage"],
            "8J",
            "Total debt",
            "financial_label_only",
            "medium",
            "Confirm whether this should be included in Item 8J Total debt.",
            "Mapped/reviewed for Company tax return Item 8J Total debt.",
            "",
        ),

        # ------------------------------------------------------------------
        # Support-only detail accounts
        # ------------------------------------------------------------------
        (
            [r"bank", r"cash"],
            "",
            "Cash / bank support",
            "support_only",
            "medium",
            "Supports current assets.",
            "BS detail account; no direct Company tax return label assigned.",
            "",
        ),
        (
            [r"gst", r"bas"],
            "",
            "GST / BAS support",
            "review_only",
            "medium",
            "Agree BAS.",
            "GST/BAS balance may support liabilities/assets but is not a direct income tax label.",
            "",
        ),
        (
            [r"payg", r"superannuation payable", r"super payable"],
            "",
            "Payroll liability support",
            "review_only",
            "medium",
            "Check paid date and timing treatment.",
            "Payroll liabilities can affect timing adjustments but are not direct Item 8 labels by themselves.",
            "",
        ),
        (
            [r"annual leave", r"long service leave", r"provision"],
            "7W / 7X",
            "Provision",
            "review_only",
            "medium",
            "Check movement.",
            "Provision balances may support timing adjustments.",
            "",
        ),
        (
            [r"retained earnings", r"current year earnings", r"equity"],
            "",
            "Equity support",
            "support_only",
            "medium",
            "",
            "Equity account supports BS checks; no direct Item 8 label assigned unless using a total equity check internally.",
            "",
        ),

        # common tax recinciliation relevant labels - these may be review-only but should be included in reconciliation if matched
                (
            [r"income tax expense", r"company tax", r"tax expense", r"tax provision"],
            "7W",
            "Income tax expense",
            "review_only",
            "medium",
            "Add back income tax expense; confirm this is company income tax and not payroll/GST.",
            "Income tax expense is generally non-deductible and usually added back.",
            "7W",
        ),
        (
            [r"deferred tax", r"deferred income tax", r"deferred tax expense", r"deferred tax benefit"],
            "7W / 7X",
            "Deferred tax",
            "review_only",
            "medium",
            "Remove accounting deferred tax effect from taxable income calculation.",
            "Deferred tax is an accounting entry and does not directly determine taxable income.",
            "",
        ),
        (
            [r"fine", r"penalty", r"speeding", r"traffic infringement", r"parking fine"],
            "7W",
            "Fines and penalties",
            "review_only",
            "medium",
            "Add back non-deductible fines and penalties.",
            "Fines and penalties are commonly non-deductible.",
            "7W",
        ),
        (
            [r"doubtful debt", r"bad debt provision", r"provision for doubtful debts", r"impairment.*receivable"],
            "7W / 7X",
            "Bad debts / doubtful debts",
            "review_only",
            "medium",
            "Add back general provisions; deduct only specific bad debts written off if tax requirements are met.",
            "Accounting doubtful debt provisions often differ from tax bad debt deductions.",
            "",
        ),
        (
            [r"prepaid", r"prepayment"],
            "7W / 7X",
            "Prepaid expenses",
            "review_only",
            "medium",
            "Check whether tax spreading/prepayment rules apply.",
            "Prepaid expenses may be deductible over a different period for tax.",
            "",
        ),
        (
            [r"capital expense", r"capitalised", r"capitalized", r"establishment cost", r"acquisition cost"],
            "7W / 7Z",
            "Capital expenses expensed",
            "review_only",
            "medium",
            "Review whether accounting expense is capital and should be added back or deducted over time.",
            "Capital expenses expensed in accounts may not be immediately deductible.",
            "",
        ),
        (
            [r"project pool", r"blackhole", r"black hole", r"section 40 880", r"s40 880"],
            "7Z",
            "Section 40-880 / project expenditure",
            "review_only",
            "medium",
            "Confirm eligibility and deduction period.",
            "Business capital expenditure may be deductible over time under specific provisions.",
            "7Z",
        ),
        (
            [r"repair", r"repairs", r"maintenance", r"improvement", r"fitout", r"fit out"],
            "6S / 7W / 7X",
            "Repairs and improvements",
            "review_only",
            "medium",
            "Confirm repair versus capital improvement treatment.",
            "Repairs may be deductible, while capital improvements may need add-back/capital allowance treatment.",
            "",
        ),
        (
            [r"make good", r"make-good", r"lease incentive", r"right of use", r"rou asset", r"aasb 16"],
            "7W / 7X",
            "Lease accounting differences",
            "review_only",
            "medium",
            "Review tax timing versus accounting lease treatment.",
            "Lease accounting entries may not match tax deductions.",
            "",
        ),
        (
            [r"non assessable", r"non-assessable", r"exempt income", r"nane"],
            "7Q",
            "Non-assessable income",
            "review_only",
            "medium",
            "Confirm whether income is exempt or non-assessable non-exempt.",
            "Accounting income that is not assessable may need subtraction at Item 7.",
            "7Q",
        ),
        (
            [r"franked dividend", r"dividend income", r"franking credit", r"imputation credit"],
            "7B / 7Q",
            "Dividends and franking credits",
            "review_only",
            "medium",
            "Review dividend assessability, gross-up and franking credit treatment.",
            "Accounting treatment of dividends/franking credits may not match tax return treatment.",
            "",
        ),
        (
            [r"loss.*disposal", r"loss.*sale.*asset", r"asset disposal loss"],
            "7W / 7X",
            "Loss on disposal of assets",
            "review_only",
            "medium",
            "Remove accounting loss and substitute tax/CGT treatment if required.",
            "Accounting disposal losses may differ from tax capital/revenue treatment.",
            "",
        ),
        (
            [r"trading stock", r"inventory", r"stock adjustment", r"obsolete stock", r"stock write down"],
            "8N / 8B / 7W / 7X",
            "Trading stock / inventory",
            "review_only",
            "medium",
            "Check opening stock, closing stock, obsolete stock and tax valuation.",
            "Trading stock tax treatment may differ from accounting treatment.",
            "",
        ),
        (
            [r"tax loss", r"prior year loss", r"carry forward loss", r"carried forward loss"],
            "7R",
            "Prior year tax losses",
            "review_only",
            "medium",
            "Do not auto-deduct. Confirm loss availability and recoupment tests.",
            "Prior year tax losses require manual review before deduction.",
            "",
        ),
    ],
}

BS_DIRECT_TOTAL_RULES = [
    (
        [r"^total current assets$", r"^current assets$"],
        "8D",
        "All current assets",
        "financial_label_only",
        "high",
        "",
        "Matched Balance Sheet total current assets to Item 8D.",
        "",
    ),
    (
        [r"^total assets$", r"^assets$"],
        "8E",
        "Total assets",
        "financial_label_only",
        "high",
        "",
        "Matched Balance Sheet total assets to Item 8E.",
        "",
    ),
    (
        [r"^total current liabilities$", r"^current liabilities$"],
        "8G",
        "All current liabilities",
        "financial_label_only",
        "high",
        "",
        "Matched Balance Sheet total current liabilities to Item 8G.",
        "",
    ),
    (
        [r"^total liabilities$", r"^liabilities$"],
        "8H",
        "Total liabilities",
        "financial_label_only",
        "high",
        "",
        "Matched Balance Sheet total liabilities to Item 8H.",
        "",
    ),
]

BS_SUPPORT_RULES = [
    # Cash / bank / current asset support
    (
        [
            r"\bbank\b",
            r"\bcash\b",
            r"cheque account",
            r"business saver",
            r"investment account",
            r"paypal",
            r"airwallex",
            r"stripe",
            r"undeposited funds",
            r"unreconciled deposits",
            r"amazon deposits",
            r"float exchange",
            r"petty cash",
            r"amex account",
        ],
        "8D-support",
        "Cash/bank support for current assets",
        "support_only",
        "high",
        "",
        "Cash/bank account supports Item 8D but should not replace Total Current Assets.",
        "",
    ),

    # Trade debtors
    (
        [
            r"accounts? receivable",
            r"account receivable",
            r"trade receivable",
            r"\bdebtors?\b",
            r"unbilled ar",
            r"receivable fx",
            r"receivable reconciliation",
        ],
        "8C",
        "Trade debtors",
        "financial_label_only",
        "high",
        "Confirm debtor balance at year end if unusual.",
        "Matched receivable/debtor account to Item 8C.",
        "",
    ),

    # Tax refund is current asset support, not trade debtor
    (
        [r"tax refund due", r"income tax refund", r"ato receivable"],
        "8D-support",
        "Tax receivable support for current assets",
        "support_only",
        "medium",
        "Check tax refund receivable balance.",
        "Tax receivable supports Item 8D current assets, not trade debtors.",
        "",
    ),

    # Inventory / stock
    (
        [
            r"\bstock\b",
            r"\binventory\b",
            r"stock on hand",
            r"trading stock",
            r"inventory in transit",
            r"consignment inventory",
            r"in-transit",
        ],
        "8B",
        "Closing stock",
        "review_only",
        "medium",
        "Check closing stock valuation, obsolete stock and tax treatment.",
        "Matched stock/inventory account to Item 8B review.",
        "",
    ),

    # Prepayments / deposits
    (
        [
            r"prepayment",
            r"prepaid",
            r"supplier prepayments",
            r"\bdeposit\b",
            r"deposits paid",
            r"bond",
            r"bank g'?tee",
            r"guarantee",
        ],
        "8D-support",
        "Prepayment/deposit support for current assets",
        "review_only",
        "medium",
        "Check whether tax spreading/prepayment adjustment is required.",
        "Matched prepayment/deposit account. Supports 8D but may require tax timing review.",
        "",
    ),

    # Capitalised inventory/freight/duty/materials
    (
        [
            r"freight to be capitalised",
            r"duty to be capitalised",
            r"materials? to be capitalised",
            r"capitalised",
            r"capitalized",
        ],
        "8D-support",
        "Capitalised cost support for current assets",
        "review_only",
        "medium",
        "Review whether capitalised cost affects stock/current assets and tax timing.",
        "Matched capitalised cost account.",
        "",
    ),

    # Fixed assets / non-current assets
    (
        [
            r"property, plant",
            r"\bppe\b",
            r"plant",
            r"equipment",
            r"computer",
            r"it equipment",
            r"vehicle",
            r"motor vehicle",
            r"furniture",
            r"fittings",
            r"leasehold improvement",
            r"right of use asset",
        ],
        "8E-support",
        "Fixed asset support for total assets",
        "support_only",
        "medium",
        "",
        "Fixed asset account supports Item 8E total assets.",
        "",
    ),

    # Intangibles
    (
        [
            r"patent",
            r"trademark",
            r"trade mark",
            r"goodwill",
            r"intangible",
            r"web dev",
            r"systems",
            r"certificates",
        ],
        "8E-support",
        "Intangible asset support for total assets",
        "support_only",
        "medium",
        "",
        "Intangible asset account supports Item 8E total assets.",
        "",
    ),

    # Accumulated depreciation / amortisation
    (
        [
            r"accum dep",
            r"acc dep",
            r"accumulated depreciation",
            r"depn",
            r"amortize",
            r"amortisation",
            r"amortization",
        ],
        "8E-support",
        "Accumulated depreciation/amortisation support",
        "support_only",
        "medium",
        "",
        "Contra asset account supports net total assets but is not a separate Item 8 label.",
        "",
    ),

    # Trade creditors
    (
        [
            r"accounts? payable",
            r"account payable",
            r"trade payable",
            r"\bcreditors?\b",
            r"payable fx",
        ],
        "8F",
        "Trade creditors",
        "financial_label_only",
        "high",
        "Confirm creditor balance at year end if unusual.",
        "Matched payable/creditor account to Item 8F.",
        "",
    ),

    # Credit cards and payables support
    (
        [
            r"credit card",
            r"amex",
            r"qantas business card",
            r"altitude",
        ],
        "8G-support",
        "Current liability support",
        "support_only",
        "medium",
        "Confirm current liability classification.",
        "Credit card/payable account supports Item 8G.",
        "",
    ),

    # GST/BAS/PAYG/tax liabilities
    (
        [
            r"\bgst\b",
            r"\bbas\b",
            r"payg",
            r"withholding",
            r"ato payable",
            r"tax payable",
            r"input tax",
            r"output tax",
            r"vat",
            r"sales tax",
        ],
        "8G-support",
        "Tax payable support for current liabilities",
        "support_only",
        "medium",
        "Agree BAS/GST/PAYG balance to lodgements where relevant.",
        "Tax payable account supports Item 8G current liabilities.",
        "",
    ),

    # Payroll liabilities
    (
        [
            r"superannuation payable",
            r"super payable",
            r"workers compensation payable",
            r"payroll clearing",
            r"payroll payable",
            r"wages payable",
            r"provision for holiday leave",
            r"provision for ls leave",
        ],
        "8G-support",
        "Payroll liability support for current liabilities",
        "review_only",
        "medium",
        "Check paid date and timing treatment where relevant.",
        "Payroll liability account supports Item 8G and may require timing review.",
        "",
    ),

    # Provisions / accruals
    (
        [
            r"provision",
            r"accrual",
            r"accrued",
            r"audit fee accrual",
            r"general accruals",
        ],
        "8G-support",
        "Provision/accrual support for current liabilities",
        "review_only",
        "medium",
        "Check deductibility and timing treatment.",
        "Provision/accrual supports Item 8G and may require tax timing review.",
        "",
    ),

    # Debt / finance
    (
        [
            r"\bloan\b",
            r"borrowings?",
            r"finance",
            r"trade finance",
            r"export finance",
            r"working capital",
            r"wayflyer",
            r"hire purchase",
            r"chattel mortgage",
            r"lease liability",
            r"lease liabilities",
            r"intercompany",
            r"owed to",
            r"accumulated interest",
        ],
        "8J",
        "Total debt",
        "review_only",
        "medium",
        "Confirm whether this should be included in Item 8J Total debt.",
        "Matched debt/finance account to Item 8J review.",
        "",
    ),

    # Equity
    (
        [
            r"retained earnings",
            r"current year earnings",
            r"ytd net income",
            r"share capital",
            r"owner.*equity",
            r"shareholder",
            r"drawings",
            r"reserves",
        ],
        "",
        "Equity support",
        "support_only",
        "medium",
        "",
        "Equity account is not an Item 8 financial label.",
        "",
    ),
]
# ---------------------------------------------------------------------------
# B. Rule helpers
# ---------------------------------------------------------------------------

def _normalise_rule_text(value: str) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"&", " and ", text)
    text = re.sub(r"[/\-]+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text


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


# ---------------------------------------------------------------------------
# C. Public matching function
# ---------------------------------------------------------------------------

def match_financial_label(
    account_name: str,
    report_type: str,
    report_section: str = "",
) -> dict:
    text = _normalise_rule_text(account_name)
    section = _normalise_rule_text(report_section)

    matched = _match_rules(text, FINANCIAL_LABEL_RULES.get(report_type, []))

    if matched:
        return matched

    if report_type == "profit_and_loss":
        section_map = {
            "trading income": ("6C", "Business income", "Income review."),
            "income": ("6C", "Business income", "Income review."),
            "revenue": ("6C", "Business income", "Income review."),

            "less cost of sales": ("6A", "Cost of sales", "Stock review."),
            "cost of sales": ("6A", "Cost of sales", "Stock review."),
            "cost of goods sold": ("6A", "Cost of sales", "Stock review."),
            "total cost of sales": ("6A", "Cost of sales", "Stock review."),

            "plus other income": (
                "6R",
                "Other gross income",
                "Assessable? Review if non-assessable income should be 7Q.",
            ),
            "other income": (
                "6R",
                "Other gross income",
                "Assessable? Review if non-assessable income should be 7Q.",
            ),

            "less operating expenses": (
                "6S",
                "All other expenses",
                "Review deductibility / specific labels.",
            ),
            "operating expenses": (
                "6S",
                "All other expenses",
                "Review deductibility / specific labels.",
            ),
            "expenses": (
                "6S",
                "All other expenses",
                "Review deductibility / specific labels.",
            ),
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
        # 1. Direct total rows first.
        direct_total_match = _match_rules(text, BS_DIRECT_TOTAL_RULES)
        if direct_total_match:
            return direct_total_match

        # 2. Specific BS account rules.
        bs_support_match = _match_rules(text, BS_SUPPORT_RULES)
        if bs_support_match:
            return bs_support_match

        # 3. Section fallback.
        # This prevents obvious Balance Sheet rows from becoming useless Review rows.

        if "cash" in section or "bank" in section:
            return {
                "ITR Ref": "8D-support",
                "ITR Label": "Cash/bank support for current assets",
                "Treatment": "support_only",
                "Confidence": "high",
                "Review Note": "",
                "Label Reason": f"Mapped from Balance Sheet section {report_section!r} as Item 8D support.",
                "Recon ITR Ref": "",
            }

        if "receivable" in section or "debtor" in section:
            return {
                "ITR Ref": "8C",
                "ITR Label": "Trade debtors",
                "Treatment": "financial_label_only",
                "Confidence": "high",
                "Review Note": "Confirm debtor balance at year end if unusual.",
                "Label Reason": f"Mapped from Balance Sheet section {report_section!r} as Item 8C.",
                "Recon ITR Ref": "",
            }

        if "inventory" in section or "stock" in section:
            return {
                "ITR Ref": "8B",
                "ITR Label": "Closing stock",
                "Treatment": "review_only",
                "Confidence": "medium",
                "Review Note": "Check closing stock valuation, obsolete stock and tax treatment.",
                "Label Reason": f"Mapped from Balance Sheet section {report_section!r} as Item 8B review.",
                "Recon ITR Ref": "",
            }

        if "current asset" in section or "other current asset" in section:
            return {
                "ITR Ref": "8D-support",
                "ITR Label": "Current asset support",
                "Treatment": "support_only",
                "Confidence": "medium",
                "Review Note": "",
                "Label Reason": f"Mapped from Balance Sheet section {report_section!r} as Item 8D support.",
                "Recon ITR Ref": "",
            }

        if (
            "fixed asset" in section
            or "non-current asset" in section
            or "non current asset" in section
            or "intangible" in section
            or "patent" in section
            or "trademark" in section
        ):
            return {
                "ITR Ref": "8E-support",
                "ITR Label": "Asset support for total assets",
                "Treatment": "support_only",
                "Confidence": "medium",
                "Review Note": "",
                "Label Reason": f"Mapped from Balance Sheet section {report_section!r} as Item 8E support.",
                "Recon ITR Ref": "",
            }

        if "payable" in section or "creditor" in section:
            return {
                "ITR Ref": "8F",
                "ITR Label": "Trade creditors",
                "Treatment": "financial_label_only",
                "Confidence": "high",
                "Review Note": "Confirm creditor balance at year end if unusual.",
                "Label Reason": f"Mapped from Balance Sheet section {report_section!r} as Item 8F.",
                "Recon ITR Ref": "",
            }

        if "payroll liabilit" in section or "tax liabilit" in section:
            return {
                "ITR Ref": "8G-support",
                "ITR Label": "Current liability support",
                "Treatment": "support_only",
                "Confidence": "medium",
                "Review Note": "Check paid date, BAS/PAYG/GST reconciliation or timing treatment where relevant.",
                "Label Reason": f"Mapped from Balance Sheet section {report_section!r} as Item 8G support.",
                "Recon ITR Ref": "",
            }

        if "current liabilit" in section or "provision" in section:
            return {
                "ITR Ref": "8G-support",
                "ITR Label": "Current liability support",
                "Treatment": "support_only",
                "Confidence": "medium",
                "Review Note": "",
                "Label Reason": f"Mapped from Balance Sheet section {report_section!r} as Item 8G support.",
                "Recon ITR Ref": "",
            }

        if "non-current liabilit" in section or "non current liabilit" in section:
            return {
                "ITR Ref": "8H-support",
                "ITR Label": "Non-current liability support",
                "Treatment": "support_only",
                "Confidence": "medium",
                "Review Note": "",
                "Label Reason": f"Mapped from Balance Sheet section {report_section!r} as Item 8H support.",
                "Recon ITR Ref": "",
            }

        if "equity" in section:
            return {
                "ITR Ref": "",
                "ITR Label": "Equity support",
                "Treatment": "support_only",
                "Confidence": "medium",
                "Review Note": "",
                "Label Reason": f"Mapped from Balance Sheet section {report_section!r} as support only.",
                "Recon ITR Ref": "",
            }
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
    """Backward-compatible wrapper for older scripts."""

    result = match_financial_label(account_name, report_type)

    return {
        "itr_ref": result.get("ITR Ref", ""),
        "category": result.get("ITR Label", ""),
        "review_note": result.get("Review Note", ""),
        "decision_logic": result.get("Label Reason", ""),
    }