"""Conservative 2024 overlay for company-return account labelling.

ATO's 2024 non-individual form-change summary records Item 7 label K for
the small business energy incentive and the removal of the former offshore
banking unit label P. The temporary training/energy incentives require a
separate eligibility and bonus-deduction calculation, so account-name matches
are review proposals only and never automatic tax adjustments.
"""

from __future__ import annotations

try:
    from .itr_rules import match_financial_label as _match_2025_base
    from .itr_rules import _normalise_rule_text
except ImportError:  # Direct-script compatibility.
    from itr_rules import match_financial_label as _match_2025_base
    from itr_rules import _normalise_rule_text


INCOME_YEAR = 2024


def _manual_incentive_review(
    mapping: dict[str, str],
    *,
    display_ref: str,
    name: str,
) -> dict[str, str]:
    result = dict(mapping)
    result.update(
        {
            "Treatment": "review_only",
            "Confidence": "medium",
            "Review Note": (
                f"2024 {name}: confirm eligibility and calculate the bonus "
                "deduction separately. The ledger amount is not the tax adjustment."
            ),
            "Label Reason": f"2024 account-name indicator for {name}.",
            "Recon ITR Ref": "",
            "Recon Key": f"2024_{display_ref.lower()}_manual_incentive",
            "Recon Display Ref": display_ref,
            "Recon Direction": "manual_calculation",
            "Auto Post": "No",
        }
    )
    return result


def match_financial_label(
    account_name: str,
    report_type: str,
    report_section: str = "",
) -> dict[str, str]:
    mapping = _match_2025_base(account_name, report_type, report_section)
    text = _normalise_rule_text(account_name)

    if report_type == "profit_and_loss":
        if any(term in text for term in ("staff training", "employee training", "skills training")):
            return _manual_incentive_review(
                mapping,
                display_ref="7J",
                name="small business skills and training boost",
            )

        if any(term in text for term in ("energy efficiency", "energy saving", "electrification")):
            return _manual_incentive_review(
                mapping,
                display_ref="7K",
                name="small business energy incentive",
            )

        if "build to rent" in text or text == "btr":
            result = dict(mapping)
            result.update(
                {
                    "Treatment": "review_only",
                    "Confidence": "high",
                    "Review Note": (
                        "Item 7Y was introduced for the 2025 company return and "
                        "must not be used on the 2024 return. Review ordinary capital-works treatment."
                    ),
                    "Recon ITR Ref": "",
                    "Recon Key": "",
                    "Recon Display Ref": "",
                    "Recon Direction": "",
                    "Auto Post": "No",
                }
            )
            return result

    mapping["Auto Post"] = "No"
    return mapping


def match_account_to_itr(account_name: str, report_type: str) -> dict[str, str]:
    result = match_financial_label(account_name, report_type)
    return {
        "itr_ref": result.get("ITR Ref", ""),
        "category": result.get("ITR Label", ""),
        "review_note": result.get("Review Note", ""),
        "decision_logic": result.get("Label Reason", ""),
    }
