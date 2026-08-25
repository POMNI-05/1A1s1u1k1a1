# v1/itr_rules_2026.py
"""ATO-aware account-name matching and ITR labelling logic for 2026.

This module uses the 2025 itr_rules.py as a structural base and applies
2026-specific policy/risk overrides that have official support.

Why import from the 2025 base?
- The published Company tax return 2026 confirms the Item 6, Item 7 and Item 8
  labels used here, but this remains preparation software rather than a lodgment
  engine.
- Confirm client facts and applicable schedules before lodgment. Current review
  overlays include:
  - GIC/SIC non-deductibility from income years starting on/after 1 July 2025.
  - 2025-26 instant asset write-off eligibility confirmation.
  - Gambling/tobacco R&D eligibility confirmation.
  - PSI / alienation arrangement review under current ATO guidance.
  - JMEI current-year eligibility confirmation.

Keep full metadata, thresholds and form labels in itr_metadata.py /
itr_year_overrides.py. This file should only change matching behaviour.
"""

from __future__ import annotations

from typing import Iterable

try:
    # Package import when running as v1 package.
    from .itr_rules import (
        LabelRule,
        R,
        PL_RULES as PL_RULES_2025,
        BS_TOTAL_RULES,
        BS_DETAIL_RULES,
        SECTION_FALLBACKS,
        _normalise_rule_text,
        _match_rules,
        _section_only_review,
        _with_section_reason,
        _unmapped,
        _normalise_report_type,
        should_highlight_mapping,
        is_tax_reconciliation_item,
        get_reconciliation_key,
        get_reconciliation_ref,
        get_reconciliation_direction,
        is_item8_support_item,
        get_support_key,
        is_auto_safe_mapping,
        match_account_to_itr,
    )
except ImportError:
    # Direct script import fallback.
    from itr_rules import (
        LabelRule,
        R,
        PL_RULES as PL_RULES_2025,
        BS_TOTAL_RULES,
        BS_DETAIL_RULES,
        SECTION_FALLBACKS,
        _normalise_rule_text,
        _match_rules,
        _section_only_review,
        _with_section_reason,
        _unmapped,
        _normalise_report_type,
        should_highlight_mapping,
        is_tax_reconciliation_item,
        get_reconciliation_key,
        get_reconciliation_ref,
        get_reconciliation_direction,
        is_item8_support_item,
        get_support_key,
        is_auto_safe_mapping,
        match_account_to_itr,
    )


INCOME_YEAR = 2026


# ---------------------------------------------------------------------------
# A. 2026-specific P&L rules
# ---------------------------------------------------------------------------
# These are prepended before the 2025 base rules.
# This matters because:
# - GIC/SIC should not fall into ordinary domestic interest 6V.
# - R&D gambling/tobacco should not be treated as normal generic R&D only.
# - PSI / associated-person indicators should be highlighted before generic
#   salary, contractor, management fee or 6S fallback.
# ---------------------------------------------------------------------------

PL_RULES_2026_PRE: list[LabelRule] = [
    # ------------------------------------------------------------------
    # 1. ATO interest charges: GIC / SIC
    # ------------------------------------------------------------------
    R(
        [
            r"\bgic\b",
            r"\bgeneral interest charge\b",
            r"\bsic\b",
            r"\bshortfall interest charge\b",
            r"\bato interest\b",
            r"\btax office interest\b",
            r"\binterest.*ato\b",
            r"\binterest.*tax office\b",
        ],
        "Exp - 6S",
        "All other expenses - ATO GIC/SIC interest review",
        "review_only",
        "high",
        (
            "2026 rule: GIC/SIC incurred on or after 1 July 2025 is generally "
            "not deductible and should be reviewed for add-back at Item 7W. "
            "Check substituted accounting period and incurred date."
        ),
        "Mapped ATO GIC/SIC interest to Item 6S and 2026 Item 7W review.",
        "7W",
        "7W_non_deductible_expenses",
        "7W",
        "add",
    ),

    # ------------------------------------------------------------------
    # 2. R&D gambling / tobacco eligibility review
    # ------------------------------------------------------------------
    # Do not infer eligibility or exclusion from an account name. We only force
    # review and keep the normal accounting R&D add-back direction.
    R(
        [
            r"\br\s*and\s*d.*gambling\b",
            r"\br&d.*gambling\b",
            r"\bresearch and development.*gambling\b",
            r"\br\s*and\s*d.*casino\b",
            r"\br&d.*casino\b",
            r"\bresearch and development.*casino\b",
            r"\br\s*and\s*d.*betting\b",
            r"\br&d.*betting\b",
            r"\bresearch and development.*betting\b",
            r"\br\s*and\s*d.*wagering\b",
            r"\br&d.*wagering\b",
            r"\bresearch and development.*wagering\b",
            r"\br\s*and\s*d.*tobacco\b",
            r"\br&d.*tobacco\b",
            r"\bresearch and development.*tobacco\b",
            r"\br\s*and\s*d.*vape\b",
            r"\br&d.*vape\b",
            r"\bresearch and development.*vape\b",
            r"\br\s*and\s*d.*nicotine\b",
            r"\br&d.*nicotine\b",
            r"\bresearch and development.*nicotine\b",
        ],
        "Exp - 6S",
        "All other expenses - R&D gambling/tobacco review",
        "review_only",
        "high",
        (
            "2026 review: confirm the enacted R&D rules and registered activity "
            "eligibility for gambling or tobacco-related work. Do not auto-deny "
            "or auto-claim from the account name; review the R&D schedule."
        ),
        "Mapped gambling/tobacco R&D account to 2026 high-risk R&D review.",
        "7D",
        "7D_rd_accounting_expenditure",
        "7D",
        "add",
    ),

    # Broader gambling/tobacco R&D signals, even where word order is reversed.
    R(
        [
            r"\bgambling.*r\s*and\s*d\b",
            r"\bgambling.*r&d\b",
            r"\bgambling.*research and development\b",
            r"\bcasino.*r\s*and\s*d\b",
            r"\bcasino.*r&d\b",
            r"\bcasino.*research and development\b",
            r"\bbetting.*r\s*and\s*d\b",
            r"\bbetting.*r&d\b",
            r"\bbetting.*research and development\b",
            r"\btobacco.*r\s*and\s*d\b",
            r"\btobacco.*r&d\b",
            r"\btobacco.*research and development\b",
            r"\bvape.*r\s*and\s*d\b",
            r"\bvape.*r&d\b",
            r"\bvape.*research and development\b",
            r"\bnicotine.*r\s*and\s*d\b",
            r"\bnicotine.*r&d\b",
            r"\bnicotine.*research and development\b",
        ],
        "Exp - 6S",
        "All other expenses - R&D gambling/tobacco review",
        "review_only",
        "high",
        (
            "2026 review: account suggests R&D connected with gambling, casino, "
            "betting, tobacco, vape or nicotine. Confirm current enacted rules, "
            "registration and expenditure eligibility before any claim."
        ),
        "Mapped R&D-sensitive industry account to 2026 high-risk R&D review.",
        "7D",
        "7D_rd_accounting_expenditure",
        "7D",
        "add",
    ),

    # ------------------------------------------------------------------
    # 3. PSI / associated-person review
    # ------------------------------------------------------------------
    R(
        [
            r"\bpersonal services income\b",
            r"\bpsi\b",
            r"\bpersonal services entity\b",
            r"\bpse\b",
            r"\balienation\b",
            r"\bincome splitting\b",
            r"\bretention of profits\b",
            r"\bcontractor.*director\b",
            r"\bdirector.*contractor\b",
            r"\bdirector fees?\b",
            r"\bdirectors? wages?\b",
            r"\bdirectors? salar(y|ies)\b",
            r"\bshareholder wages?\b",
            r"\bshareholder salar(y|ies)\b",
            r"\bfamily member wages?\b",
            r"\bassociated persons?\b",
            r"\bassociate payments?\b",
            r"\brelated party contractor\b",
            r"\brelated party management fee\b",
            r"\bmanagement fee.*related party\b",
        ],
        "Exp - 6S",
        "All other expenses - PSI / associated person review",
        "review_only",
        "high",
        (
            "2026 review: apply current ATO PSI/PSB guidance (including "
            "TR 2022/3) and review alienation, retention of profits and income "
            "splitting risks. Review Item 8Q, Item 14 PSI, Division 7A and "
            "Part IVA where relevant. Do not auto-populate 8Q from an account "
            "name alone."
        ),
        "Mapped PSI/associated-person indicator to 2026 high-risk review.",
        support_key="8Q_payments_to_associated_persons",
        support_display_ref="8Q",
        support_label="Payments to associated persons",
    ),

    # ------------------------------------------------------------------
    # 4. Junior Mineral Exploration Incentive
    # ------------------------------------------------------------------
    R(
        [
            r"\bjunior mineral exploration incentive\b",
            r"\bjmei\b",
            r"\bexploration credits?\b",
            r"\bmineral exploration credits?\b",
        ],
        "Review",
        "Junior Mineral Exploration Incentive - current-year eligibility review",
        "review_only",
        "high",
        (
            "2026 review: confirm whether the exploration credit relates to a "
            "valid entitlement and income year under current enacted rules and "
            "ATO guidance. Do not auto-claim from the account name."
        ),
        "Mapped JMEI/exploration credit account to 2026 manual review.",
    ),

    # ------------------------------------------------------------------
    # 5. Debt deduction creation / thin capitalisation review
    # ------------------------------------------------------------------
    R(
        [
            r"\bdebt deduction creation\b",
            r"\bddcr\b",
            r"\bthin capitalisation\b",
            r"\bthin cap\b",
            r"\brelated party debt\b",
            r"\bassociate entity debt\b",
            r"\brelated party interest\b",
            r"\bintercompany interest\b",
            r"\brelated party loan interest\b",
        ],
        "Exp - 6V",
        "Interest expenses within Australia - thin cap / DDCR review",
        "review_only",
        "high",
        (
            "2026 review: check thin capitalisation and debt deduction creation "
            "rules. If applicable, International dealings schedule may be needed "
            "and disallowed debt deductions may require Item 7W add-back."
        ),
        "Mapped debt deduction creation/thin cap indicator to interest and 7W review.",
        "7W",
        "7W_non_deductible_expenses",
        "7W",
        "add",
    ),

    # ------------------------------------------------------------------
    # 6. Instant asset write-off / SBE simplified depreciation
    # ------------------------------------------------------------------
    # This does not create a different Item 6 label, but it forces better
    # review wording for 2026.
    R(
        [
            r"\binstant asset write.?off\b",
            r"\binstant write.?off\b",
            r"\b20,?000 asset\b",
            r"\bsmall business pool\b",
            r"\bsimplified depreciation\b",
            r"\bimmediate asset deduction\b",
            r"\bimmediate deduction.*asset\b",
        ],
        "Exp - 6X",
        "Depreciation expenses - 2026 SBE simplified depreciation review",
        "review_only",
        "high",
        (
            "2026: the enacted instant asset write-off threshold is $20,000 for "
            "eligible small business entities. Confirm asset and entity eligibility, "
            "taxable-use timing and cost, then check Item 10A/10B and whether "
            "Item 6X should use tax rather than book depreciation."
        ),
        "Mapped instant asset write-off / simplified depreciation account to 2026 6X and Item 10 review.",
        "",
        "10A_sbe_deduction_for_certain_assets",
        "10A",
        "schedule_review",
    ),
]


# 2026 full P&L rule set = 2026-specific rules first, then 2025 base.
PL_RULES: list[LabelRule] = [
    *PL_RULES_2026_PRE,
    *PL_RULES_2025,
]


# ---------------------------------------------------------------------------
# B. Post-processing helpers
# ---------------------------------------------------------------------------

def _append_note(mapping: dict[str, str], extra_note: str, extra_reason: str = "") -> dict[str, str]:
    """Return a copy of mapping with extra 2026 review note/reason appended."""
    result = dict(mapping)

    old_note = str(result.get("Review Note", "") or "").strip()
    if old_note:
        result["Review Note"] = f"{old_note} {extra_note}"
    else:
        result["Review Note"] = extra_note

    if extra_reason:
        old_reason = str(result.get("Label Reason", "") or "").strip()
        result["Label Reason"] = f"{old_reason} {extra_reason}".strip()

    return result


def _force_review(
    mapping: dict[str, str],
    note: str,
    reason: str,
    confidence: str = "high",
) -> dict[str, str]:
    """Return mapping converted to review-only with appended note."""
    result = _append_note(mapping, note, reason)
    result["Treatment"] = "review_only"
    result["Confidence"] = confidence
    return result


def _has_any(text: str, terms: Iterable[str]) -> bool:
    return any(term in text for term in terms)


def _post_adjust_2026_mapping(
    mapping: dict[str, str],
    *,
    text: str,
    section: str,
    report: str,
) -> dict[str, str]:
    """Apply 2026 category-level adjustments after base matching.

    This lets us reuse 2025 rules while changing policy by category.
    """

    # ------------------------------------------------------------------
    # Category: ATO interest and tax charges
    # Safety net in case base 2025 rule matched it as ordinary 6V interest.
    # ------------------------------------------------------------------
    if _has_any(
        text,
        [
            "general interest charge",
            "shortfall interest charge",
            "ato interest",
            "tax office interest",
        ],
    ) or text in {"gic", "sic"}:
        result = dict(mapping)
        result.update(
            {
                "ITR Ref": "Exp - 6S",
                "ITR Label": "All other expenses - ATO GIC/SIC interest review",
                "Treatment": "review_only",
                "Confidence": "high",
                "Review Note": (
                    "2026 rule: GIC/SIC incurred on or after 1 July 2025 is "
                    "generally not deductible and should be reviewed for add-back "
                    "at Item 7W. Check SAP and incurred date."
                ),
                "Label Reason": (
                    "2026 post-adjustment: ATO GIC/SIC should not be treated as "
                    "ordinary interest expense."
                ),
                "Recon ITR Ref": "7W",
                "Recon Key": "7W_non_deductible_expenses",
                "Recon Display Ref": "7W",
                "Recon Direction": "add",
            }
        )
        return result

    # ------------------------------------------------------------------
    # Category: generic interest / debt
    # Add DDCR/thin-cap wording to all interest expense matches.
    # ------------------------------------------------------------------
    if mapping.get("ITR Ref") in {"Exp - 6V", "Exp - 6J"}:
        return _force_review(
            mapping,
            (
                "2026: also check debt deduction creation rules and thin "
                "capitalisation, especially for related-party or cross-border debt."
            ),
            "2026 post-adjustment: interest expense gets DDCR/thin-cap review note.",
            confidence="medium" if mapping.get("Confidence") != "high" else "high",
        )

    # ------------------------------------------------------------------
    # Category: R&D
    # Make 2026 R&D note stronger even where 2025 base caught generic R&D.
    # ------------------------------------------------------------------
    if _has_any(
        text,
        [
            "r and d",
            "r d",
            "r&d",
            "research and development",
            "research development",
        ],
    ):
        result = _force_review(
            mapping,
            (
                "2026: review the R&D schedule carefully and confirm current "
                "enacted rules, registration and expenditure eligibility. For "
                "gambling/tobacco-related activity, do not auto-deny or auto-claim. "
                "Check Item 7D, 7B, 7X and Item 21."
            ),
            "2026 post-adjustment: R&D gets additional 2026 review note.",
            confidence="high",
        )
        result.setdefault("Recon Key", "7D_rd_accounting_expenditure")
        if not result.get("Recon Key"):
            result["Recon Key"] = "7D_rd_accounting_expenditure"
        if not result.get("Recon Display Ref"):
            result["Recon Display Ref"] = "7D"
        if not result.get("Recon Direction"):
            result["Recon Direction"] = "add"
        if not result.get("Recon ITR Ref"):
            result["Recon ITR Ref"] = "7D"
        return result

    # ------------------------------------------------------------------
    # Category: depreciation / assets
    # Keep the label and require review of the conditions around the enacted threshold.
    # ------------------------------------------------------------------
    if mapping.get("ITR Ref") == "Exp - 6X":
        return _force_review(
            mapping,
            (
                "2026: the enacted instant asset write-off threshold is $20,000 "
                "for eligible small business entities. Confirm asset and entity "
                "eligibility, taxable-use timing and cost. "
                "Check Item 10A/10B and whether 6X should use tax rather than "
                "book depreciation."
            ),
            "2026 post-adjustment: depreciation gets 2026 instant asset write-off note.",
            confidence="medium",
        )

    # ------------------------------------------------------------------
    # Category: PSI / salary / associated persons
    # Salary/wages remain 6S, but associated-person/PSI indicators need review.
    # ------------------------------------------------------------------
    if _has_any(
        text,
        [
            "director",
            "shareholder",
            "associated person",
            "associate payment",
            "family member",
            "personal services income",
            "psi",
            "pse",
            "income splitting",
            "retention of profits",
        ],
    ):
        result = _force_review(
            mapping,
            (
                "2026: apply current ATO PSI/PSB guidance, including TR 2022/3, "
                "and review alienation/Part IVA risk, Item 8Q payments to "
                "associated persons, Item 14 PSI and Division 7A where relevant."
            ),
            "2026 post-adjustment: associated-person/PSI indicator detected.",
            confidence="high",
        )
        if not result.get("Support Key"):
            result["Support Key"] = "8Q_payments_to_associated_persons"
            result["Support Display Ref"] = "8Q"
            result["Support Label"] = "Payments to associated persons"
        return result

    # ------------------------------------------------------------------
    # Category: foreign / international indicators
    # Add IDS/foreign schedule review note.
    # ------------------------------------------------------------------
    if _has_any(
        text,
        [
            "foreign",
            "overseas",
            "non resident",
            "non-resident",
            "international",
            "cross border",
            "related party overseas",
        ],
    ):
        return _force_review(
            mapping,
            (
                "2026: foreign/overseas indicator detected. Review International "
                "dealings schedule, withholding, foreign income and source "
                "classification."
            ),
            "2026 post-adjustment: foreign/international indicator detected.",
            confidence="medium",
        )

    return mapping


# ---------------------------------------------------------------------------
# C. 2026 public API
# ---------------------------------------------------------------------------

def match_financial_label(
    account_name: str,
    report_type: str,
    report_section: str = "",
) -> dict[str, str]:
    """Return conservative 2026 ITR mapping for a report row.

    This function is intentionally compatible with 2025 workbook code:
    - ITR Ref
    - ITR Label
    - Treatment
    - Confidence
    - Review Note
    - Label Reason
    - Recon ITR Ref

    It also preserves the safer 2025+ fields:
    - Recon Key
    - Recon Display Ref
    - Recon Direction
    - Support Key
    - Support Display Ref
    - Support Label
    """
    text = _normalise_rule_text(account_name)
    section = _normalise_rule_text(report_section)
    report = _normalise_report_type(report_type)

    if report == "profit_and_loss":
        matched = _match_rules(text, PL_RULES)
        if matched:
            return _post_adjust_2026_mapping(
                matched,
                text=text,
                section=section,
                report=report,
            )

        fallback = SECTION_FALLBACKS["profit_and_loss"].get(section)
        if fallback:
            mapped = _section_only_review(
                account_name,
                report_type,
                report_section,
                fallback,
            )
            return _post_adjust_2026_mapping(
                mapped,
                text=text,
                section=section,
                report=report,
            )

        return _unmapped(account_name, report_type, report_section)

    if report == "balance_sheet":
        # Balance sheet structure is same as 2025, but we add 2026 review
        # notes for debt, foreign, associated-person and tax balances.
        matched = _match_rules(text, BS_TOTAL_RULES)
        if matched:
            return _post_adjust_2026_mapping(
                matched,
                text=text,
                section=section,
                report=report,
            )

        matched = _match_rules(text, BS_DETAIL_RULES)
        if matched:
            return _post_adjust_2026_mapping(
                matched,
                text=text,
                section=section,
                report=report,
            )

        if "receivable" in section or "debtor" in section:
            mapped = _with_section_reason(
                R(
                    [],
                    "8C",
                    "Trade debtors",
                    "financial_label_only",
                    "medium",
                    "Confirm trade debtor classification.",
                    "No keyword match; labelled from Balance Sheet section.",
                    support_key="8C_trade_debtors",
                    support_display_ref="8C",
                    support_label="Trade debtors",
                ).as_mapping(),
                report_section,
            )
            return _post_adjust_2026_mapping(mapped, text=text, section=section, report=report)

        if "inventory" in section or "stock" in section:
            mapped = _with_section_reason(
                R(
                    [],
                    "8B",
                    "Closing stock",
                    "review_only",
                    "medium",
                    "Check closing stock valuation and tax treatment.",
                    "No keyword match; labelled from Balance Sheet section.",
                    support_key="8B_closing_stock",
                    support_display_ref="8B",
                    support_label="Closing stock",
                ).as_mapping(),
                report_section,
            )
            return _post_adjust_2026_mapping(mapped, text=text, section=section, report=report)

        if "payable" in section or "creditor" in section:
            mapped = _with_section_reason(
                R(
                    [],
                    "8F",
                    "Trade creditors",
                    "financial_label_only",
                    "medium",
                    "Confirm trade creditor classification.",
                    "No keyword match; labelled from Balance Sheet section.",
                    support_key="8F_trade_creditors",
                    support_display_ref="8F",
                    support_label="Trade creditors",
                ).as_mapping(),
                report_section,
            )
            return _post_adjust_2026_mapping(mapped, text=text, section=section, report=report)

        if "loan" in section or "borrow" in section or "debt" in section:
            mapped = _with_section_reason(
                R(
                    [],
                    "8J",
                    "Total debt",
                    "review_only",
                    "medium",
                    "Confirm whether this belongs in total debt. Review thin capitalisation and DDCR where relevant.",
                    "No keyword match; labelled from Balance Sheet section.",
                    support_key="8J_total_debt",
                    support_display_ref="8J",
                    support_label="Total debt",
                ).as_mapping(),
                report_section,
            )
            return _post_adjust_2026_mapping(mapped, text=text, section=section, report=report)

        for key, rule in SECTION_FALLBACKS["balance_sheet"].items():
            if key in section:
                mapped = _with_section_reason(rule.as_mapping(), report_section)
                return _post_adjust_2026_mapping(
                    mapped,
                    text=text,
                    section=section,
                    report=report,
                )

        return _unmapped(account_name, report_type, report_section)

    return _unmapped(account_name, report_type, report_section)


def match_account_to_itr(account_name: str, report_type: str) -> dict[str, str]:
    """Backward-compatible wrapper for older scripts."""
    result = match_financial_label(account_name, report_type)

    return {
        "itr_ref": result.get("ITR Ref", ""),
        "category": result.get("ITR Label", ""),
        "review_note": result.get("Review Note", ""),
        "decision_logic": result.get("Label Reason", ""),
    }
