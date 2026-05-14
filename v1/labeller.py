# v1/labeller.py
"""Label only actual accounting entries; keep headings/totals as structure/check rows."""

from __future__ import annotations

import pandas as pd

from itr_rules import match_financial_label


def get_account_col(df: pd.DataFrame) -> str:
    for col in df.columns:
        if str(col).strip().lower() in {"account", "description", "account name"}:
            return col
    return df.columns[0]


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


def label_report(df: pd.DataFrame, report_type: str) -> pd.DataFrame:
    out = df.copy()
    account_col = get_account_col(out)
    labels: list[dict] = []

    for _, row in out.iterrows():
        row_type = str(row.get("Row Type", "")).lower()
        account_name = row.get(account_col, "")

        if row_type == "account":
            labels.append(match_financial_label(account_name, report_type, row.get("Report Section", "")))
            continue

        if row_type == "total" and report_type == "profit_and_loss" and "net profit" in str(account_name).lower():
            labels.append({
                "ITR Ref": "7T",
                "ITR Label": "Accounting profit/loss before tax",
                "Treatment": "base_for_tax_reconciliation",
                "Confidence": "high",
                "Review Note": "",
                "Label Reason": "Net Profit total row used as reconciliation base where reported value is available.",
                "Recon ITR Ref": "",
            })
            continue

        labels.append(_blank_label())

    return pd.concat(
        [out.reset_index(drop=True), pd.DataFrame(labels).reset_index(drop=True)],
        axis=1,
    )


def rows_requiring_highlight(labelled_df: pd.DataFrame) -> pd.DataFrame:
    if labelled_df is None or labelled_df.empty or "Confidence" not in labelled_df.columns:
        return pd.DataFrame()
    return labelled_df[
        labelled_df["Confidence"].astype(str).str.lower().isin(["medium", "low"])
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
        return pd.DataFrame()

    account_col = get_account_col(review_rows)

    return pd.DataFrame({
        "Source": source,
        "Section": review_rows.get("Report Section", ""),
        "Account": review_rows[account_col],
        "ITR Ref": review_rows.get("ITR Ref", ""),
        "Recon ITR Ref": review_rows.get("Recon ITR Ref", ""),
        "Review Note": review_rows.get("Review Note", ""),
        "Reason": review_rows.get("Label Reason", ""),
    })