# v1/labeller.py
"""Label accounting rows with direct ITR codes.

Design:
- Headings/blanks stay structural.
- P&L account rows get direct ITR Ref codes where rules can map them.
- BS account/total rows get direct ITR Ref codes where rules can map them.
- The workbook side column displays ITR Ref directly: 6C, 6A, 8D, etc.
"""

from __future__ import annotations

import pandas as pd

from itr_rules import match_financial_label

LABEL_COLUMNS = [
    "ITR Ref",
    "ITR Label",
    "Treatment",
    "Confidence",
    "Review Note",
    "Label Reason",
    "Recon ITR Ref",
]


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
        "ITR Ref": "7T",
        "ITR Label": "Accounting profit/loss before tax",
        "Treatment": "base_for_tax_reconciliation",
        "Confidence": "high",
        "Review Note": "",
        "Label Reason": "Net profit/profit before tax total row used as reconciliation base.",
        "Recon ITR Ref": "",
    }


def label_report(df: pd.DataFrame, report_type: str) -> pd.DataFrame:
    out = df.copy()

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
            labels.append(_normalise_mapping(_net_profit_mapping()))
            continue

        mapping = match_financial_label(
            account_name=account_name,
            report_type=report_type,
            report_section=report_section,
        )

        labels.append(_normalise_mapping(mapping))

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

    return labelled_df[
        confidence.isin(["medium", "low"])
        | treatment.eq("review_only")
        | itr_ref.eq("Review")
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
        }
    )