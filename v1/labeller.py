# v1/labeller.py
"""Label accounting rows with direct ITR codes.

Design:
- Headings/blanks stay structural.
- P&L account rows get direct ITR Ref codes where rules can map them.
- BS account/total rows get direct ITR Ref codes where rules can map them.
- User/custom overrides are applied after base rule matching.
- The workbook side column displays ITR Ref directly: 6C, 6A, 8D, etc.
"""

from __future__ import annotations

from importlib import import_module

import pandas as pd

try:
    from .job_config import get_policy_year
    from .label_overrides import apply_label_override, load_overrides
except ImportError:  # Direct-script compatibility.
    from job_config import get_policy_year
    from label_overrides import apply_label_override, load_overrides


LABEL_COLUMNS = [
    "ITR Ref",
    "ITR Label",
    "Tab 3 Decision",
    "Treatment",
    "Confidence",
    "Review Note",
    "Label Reason",
    "Recon ITR Ref",
    "Recon Key",
    "Recon Display Ref",
    "Recon Direction",
    "Support Key",
    "Support Display Ref",
    "Support Label",
    "Override Applied",
    "Override Name",
    "Override Reason",
    "Rule ID",
    "Rule Pack",
    "Matched Pattern",
    "Matched Text",
    "Rule Source",
    "Auto Post",
]


# These are the only source Balance Sheet total rows for which the current
# rules packs hold direct Item 8 aggregate references.  Other totals (for
# example Net Assets and Total Equity) remain structural/check rows until a
# reviewed derived-total calculation is introduced; they must not inherit a
# weak section fallback merely because they happen to be totals.
_DIRECT_BALANCE_SHEET_TOTALS = frozenset(
    {
        "total current assets",
        "total non-current assets",
        "total non current assets",
        "total assets",
        "total current liabilities",
        "total non-current liabilities",
        "total non current liabilities",
        "total liabilities",
    }
)


def _get_matcher():
    """Return the year-specific ITR labelling function.

    File naming rule:
    - 2025 uses legacy v1/itr_rules.py
    - 2026+ can use v1/itr_rules_<year>.py, e.g. itr_rules_2026.py
    """
    year = str(get_policy_year("2026")).strip()

    package = __package__

    if year == "2025":
        module_name = f"{package}.itr_rules" if package else "itr_rules"
    else:
        module_name = f"{package}.itr_rules_{year}" if package else f"itr_rules_{year}"

    try:
        rules_module = import_module(module_name)
    except ModuleNotFoundError as exc:
        raise ValueError(
            f"No ITR rules module found for policy year {year}. "
            f"Expected backend file: v1/{module_name}.py"
        ) from exc

    if not hasattr(rules_module, "match_financial_label"):
        raise AttributeError(
            f"Rules module {module_name}.py does not define match_financial_label()."
        )

    return rules_module.match_financial_label


def get_account_col(df: pd.DataFrame) -> str:
    for wanted in ["account label", "account", "description", "account name"]:
        for col in df.columns:
            if str(col).strip().lower() == wanted:
                return col

    return df.columns[0]


def _normalise_text(value) -> str:
    text = str(value or "").strip()
    return "" if text.lower() in {"nan", "none"} else text


def _has_balance_sheet_section_conflict(account_name: object, report_section: object) -> bool:
    """Return true for a narrow cash/bank-under-liabilities contradiction."""

    account = " ".join(_normalise_text(account_name).lower().split())
    section = " ".join(_normalise_text(report_section).lower().split())
    if "liabilit" not in section:
        return False
    if any(term in account for term in ("loan", "overdraft", "facility", "borrow")):
        return False
    return any(
        term in account
        for term in ("cash", "bank account", "business bank", "cheque account", "savings account")
    )


def _apply_balance_sheet_section_conflict_review(
    mapping: dict,
    *,
    account_name: object,
    report_section: object,
) -> dict:
    """Create a review-only record; do not silently correct source evidence."""

    if not _has_balance_sheet_section_conflict(account_name, report_section):
        return mapping

    result = dict(mapping)
    existing_reason = str(result.get("Label Reason", "") or "").strip()
    result.update(
        {
            # `Review` is an explicit UI/contract sentinel, not an ITR filing
            # label.  It keeps a structural review visible and compatible with
            # existing result readers without inventing a tax classification.
            "ITR Ref": "Review",
            "ITR Label": "Balance-sheet structural conflict — review",
            "Treatment": "review_only",
            "Confidence": "high",
            "Review Note": (
                "Account name suggests cash/bank, but the source report places it under "
                "liabilities. Confirm the account nature and source report structure."
            ),
            "Label Reason": " ".join(
                part
                for part in (
                    existing_reason,
                    "Structural conflict: cash/bank-like account under a liability section.",
                )
                if part
            ),
            "Rule ID": "system-bs-section-conflict-cash-under-liability",
            "Matched Pattern": "cash/bank account under liabilities",
            "Matched Text": str(account_name or ""),
            "Rule Source": "structural_validation",
        }
    )
    return result


def _blank_label(treatment: str = "structure_or_check_only") -> dict:
    return {
        "ITR Ref": "",
        "ITR Label": "",
        "Tab 3 Decision": "No use in Tab 3",
        "Treatment": treatment,
        "Confidence": "",
        "Review Note": "",
        "Label Reason": "",
        "Recon ITR Ref": "",
        "Recon Key": "",
        "Recon Display Ref": "",
        "Recon Direction": "",
        "Support Key": "",
        "Support Display Ref": "",
        "Support Label": "",
        "Override Applied": "",
        "Override Name": "",
        "Override Reason": "",
        "Rule ID": "",
        "Rule Pack": "",
        "Matched Pattern": "",
        "Matched Text": "",
        "Rule Source": "",
    }


def _normalise_mapping(mapping: dict) -> dict:
    clean = _blank_label(treatment=mapping.get("Treatment", ""))

    for col in LABEL_COLUMNS:
        clean[col] = mapping.get(col, "")

    # Normalise accidental compound refs.
    # The workbook side label should be one direct code where possible.
    clean["ITR Ref"] = str(clean.get("ITR Ref", "") or "").strip()
    clean["ITR Label"] = str(clean.get("ITR Label", "") or "").strip()
    clean["Recon ITR Ref"] = str(clean.get("Recon ITR Ref", "") or "").strip()
    clean["Recon Key"] = str(clean.get("Recon Key", "") or "").strip()
    clean["Recon Display Ref"] = str(clean.get("Recon Display Ref", "") or "").strip()
    clean["Recon Direction"] = str(clean.get("Recon Direction", "") or "").strip()
    clean["Support Key"] = str(clean.get("Support Key", "") or "").strip()
    clean["Support Display Ref"] = str(clean.get("Support Display Ref", "") or "").strip()
    clean["Support Label"] = str(clean.get("Support Label", "") or "").strip()
    clean["Rule ID"] = str(clean.get("Rule ID", "") or "").strip()
    clean["Rule Pack"] = str(clean.get("Rule Pack", "") or "").strip()
    clean["Matched Pattern"] = str(clean.get("Matched Pattern", "") or "").strip()
    clean["Matched Text"] = str(clean.get("Matched Text", "") or "").strip()
    clean["Rule Source"] = str(clean.get("Rule Source", "") or "").strip()

    return clean


def _tab_3_decision(mapping: dict, report_type: str) -> str:
    """Return the high-threshold source-to-Item-7 routing decision.

    A Balance Sheet line may explain an Item 8 balance or support later review,
    but it does not directly reconcile accounting profit to Item 7T.  Only a
    P&L account with an explicit Item 7 reference and add/subtract direction
    can enter the Tab 3 pre-calculation.
    """
    if report_type != "profit_and_loss":
        return "No use in Tab 3"

    recon_ref = str(mapping.get("Recon ITR Ref", "") or "").strip()
    direction = str(mapping.get("Recon Direction", "") or "").strip().lower()
    if recon_ref and direction in {"add", "subtract"}:
        return "Use in Tab 3"
    return "No use in Tab 3"


def _should_label_row(row_type: str, report_type: str, account_name: str) -> bool:
    row_type = row_type.lower().strip()
    account_name_lower = " ".join(str(account_name or "").lower().split())

    if row_type == "account":
        return True

    # Only reviewed Balance Sheet aggregate rows are direct Item 8 candidates.
    # Net Assets/Total Equity and similar validation totals must remain
    # structure-only rather than receiving a section-fallback confidence label.
    if report_type == "balance_sheet" and row_type == "total":
        return account_name_lower in _DIRECT_BALANCE_SHEET_TOTALS

    # P&L net profit/profit before tax is the tax reconciliation base.
    if (
        report_type == "profit_and_loss"
        and row_type == "total"
        and (
            "net profit" in account_name_lower
            or "net loss" in account_name_lower
            or "profit before tax" in account_name_lower
        )
    ):
        return True

    return False


def _net_profit_mapping() -> dict:
    return {
        "ITR Ref": "6T",
        "ITR Label": "Accounting profit/loss before tax",
        "Treatment": "base_for_tax_reconciliation",
        "Confidence": "high",
        "Review Note": "",
        "Label Reason": "Net profit/profit before tax total row used as reconciliation base.",
        "Recon ITR Ref": "",
        "Recon Key": "",
        "Recon Display Ref": "",
        "Recon Direction": "",
        "Support Key": "",
        "Support Display Ref": "",
        "Support Label": "",
        "Rule ID": "system-net-profit",
        "Rule Pack": "",
        "Matched Pattern": "net profit/profit before tax total",
        "Matched Text": "",
        "Rule Source": "system",
    }


def label_report(df: pd.DataFrame, report_type: str) -> pd.DataFrame:
    out = df.copy()
    match_financial_label = _get_matcher()
    policy_year = get_policy_year("2026")
    user_overrides = load_overrides()

    if out.empty:
        return pd.concat(
            [out.reset_index(drop=True), pd.DataFrame(columns=LABEL_COLUMNS)],
            axis=1,
        )

    account_col = get_account_col(out)
    labels: list[dict] = []

    for _, row in out.iterrows():
        row_type = _normalise_text(row.get("Row Type", "")).lower()
        account_name = row.get(account_col, "")
        report_section = row.get("Report Section", "")

        if not _should_label_row(row_type, report_type, account_name):
            blank_mapping = _blank_label()
            blank_mapping["Tab 3 Decision"] = _tab_3_decision(blank_mapping, report_type)
            labels.append(blank_mapping)
            continue

        if (
            report_type == "profit_and_loss"
            and row_type == "total"
            and (
                "net profit" in str(account_name).lower()
                or "net loss" in str(account_name).lower()
                or "profit before tax" in str(account_name).lower()
            )
        ):
            base_mapping = _net_profit_mapping()
        else:
            base_mapping = match_financial_label(
                account_name=account_name,
                report_type=report_type,
                report_section=report_section,
            )

        final_mapping = apply_label_override(
            base_mapping,
            account_name=str(account_name or ""),
            report_type=report_type,
            report_section=str(report_section or ""),
            overrides=user_overrides,
        )
        if report_type == "balance_sheet":
            final_mapping = _apply_balance_sheet_section_conflict_review(
                final_mapping,
                account_name=account_name,
                report_section=report_section,
            )
        final_mapping["Tab 3 Decision"] = _tab_3_decision(final_mapping, report_type)
        final_mapping["Rule Pack"] = f"ITR {policy_year}"
        if not final_mapping.get("Matched Text"):
            final_mapping["Matched Text"] = str(account_name or "")

        labels.append(_normalise_mapping(final_mapping))

    label_df = pd.DataFrame(labels)

    for col in LABEL_COLUMNS:
        if col not in label_df.columns:
            label_df[col] = ""

    return pd.concat(
        [out.reset_index(drop=True), label_df[LABEL_COLUMNS].reset_index(drop=True)],
        axis=1,
    )


def rows_requiring_highlight(labelled_df: pd.DataFrame) -> pd.DataFrame:
    if labelled_df is None or labelled_df.empty:
        return pd.DataFrame()

    confidence = labelled_df.get("Confidence", "").astype(str).str.lower()
    treatment = labelled_df.get("Treatment", "").astype(str).str.lower()
    itr_ref = labelled_df.get("ITR Ref", "").astype(str)
    override_applied = labelled_df.get("Override Applied", "").astype(str).str.lower()

    return labelled_df[
        confidence.isin(["medium", "low"])
        | treatment.eq("review_only")
        | itr_ref.eq("Review")
        | override_applied.eq("yes")
    ].copy()


def extract_account_entries(labelled_df: pd.DataFrame) -> pd.DataFrame:
    if labelled_df is None or labelled_df.empty:
        return pd.DataFrame()

    if "Row Type" not in labelled_df.columns:
        return labelled_df.copy()

    return labelled_df[
        labelled_df["Row Type"].astype(str).str.lower().eq("account")
    ].copy()


def extract_review_items(labelled_df: pd.DataFrame, source: str = "") -> pd.DataFrame:
    review_rows = rows_requiring_highlight(labelled_df)

    if review_rows.empty:
        return pd.DataFrame(
            columns=[
                "Source",
                "Section",
                "Account",
                "ITR Ref",
                "Recon ITR Ref",
                "Review Note",
                "Reason",
                "Override Applied",
                "Override Name",
            ]
        )

    account_col = get_account_col(review_rows)

    return pd.DataFrame(
        {
            "Source": source,
            "Section": review_rows.get("Report Section", ""),
            "Account": review_rows[account_col],
            "ITR Ref": review_rows.get("ITR Ref", ""),
            "Recon ITR Ref": review_rows.get("Recon ITR Ref", ""),
            "Review Note": review_rows.get("Review Note", ""),
            "Reason": review_rows.get("Label Reason", ""),
            "Override Applied": review_rows.get("Override Applied", ""),
            "Override Name": review_rows.get("Override Name", ""),
        }
    )
