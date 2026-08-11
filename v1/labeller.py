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
    "Auto Post",
]


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


def _blank_label(treatment: str = "structure_or_check_only") -> dict:
    return {
        "ITR Ref": "",
        "ITR Label": "",
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

    return clean


def _should_label_row(row_type: str, report_type: str, account_name: str) -> bool:
    row_type = row_type.lower().strip()
    account_name_lower = str(account_name or "").lower()

    if row_type == "account":
        return True

    # Balance Sheet totals are direct Item 8 candidates.
    if report_type == "balance_sheet" and row_type == "total":
        return True

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
    }


def label_report(df: pd.DataFrame, report_type: str) -> pd.DataFrame:
    out = df.copy()
    match_financial_label = _get_matcher()
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
            labels.append(_blank_label())
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
