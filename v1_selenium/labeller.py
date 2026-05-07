# v1_selenium/labeller.py

from __future__ import annotations

import pandas as pd

from itr_rules import match_financial_label


def _get_account_col(df: pd.DataFrame) -> str:
    for col in df.columns:
        if str(col).strip().lower() in {"account", "description", "account name"}:
            return col
    return df.columns[0]


def label_report(df: pd.DataFrame, report_type: str) -> pd.DataFrame:
    out = df.copy()
    account_col = _get_account_col(out)

    label_rows = []

    for _, row in out.iterrows():
        row_type = str(row.get("Row Type", "")).lower()
        account_name = row.get(account_col, "")

        if row_type == "account":
            label_rows.append(match_financial_label(account_name, report_type))
            continue

        # Net Profit total row can get 7T because it is used as recon base.
        if row_type == "total" and "net profit" in str(account_name).lower():
            label_rows.append({
                "ITR Ref": "7T",
                "ITR Label": "Accounting profit/loss before tax",
                "Treatment": "base_for_tax_reconciliation",
                "Confidence": "high",
                "Review Note": "",
                "Label Reason": "Net profit total row used as tax reconciliation starting point.",
            })
            continue

        label_rows.append({
            "ITR Ref": "",
            "ITR Label": "",
            "Treatment": "structure_or_check_only",
            "Confidence": "",
            "Review Note": "",
            "Label Reason": "",
        })

    return pd.concat(
        [out.reset_index(drop=True), pd.DataFrame(label_rows).reset_index(drop=True)],
        axis=1,
    )


def rows_requiring_highlight(labelled_df: pd.DataFrame) -> pd.DataFrame:
    """
    Only medium / low confidence rows should be highlighted,
    and only the ITR Ref / Review note side cells, not the whole row.
    """
    if labelled_df is None or labelled_df.empty:
        return pd.DataFrame()

    return labelled_df[
        labelled_df["Confidence"].astype(str).str.lower().isin(["medium", "low"])
    ].copy()

def extract_account_entries(labelled_df: pd.DataFrame) -> pd.DataFrame:
    """
    Return only real accounting entry rows.

    Headings are used for section context only.
    Total/subtotal rows are check/base rows only.
    """
    if labelled_df is None or labelled_df.empty:
        return pd.DataFrame()

    if "Row Type" not in labelled_df.columns:
        return labelled_df.copy()

    return labelled_df[
        labelled_df["Row Type"].astype(str).str.lower().eq("account")
    ].copy()


def extract_review_items(labelled_df: pd.DataFrame, source: str = "") -> pd.DataFrame:
    """
    Return only rows that need manual review.

    This is for review listing only. It must not feed tax reconciliation
    calculations automatically.
    """
    if labelled_df is None or labelled_df.empty:
        return pd.DataFrame()

    review_rows = labelled_df[
        labelled_df["Confidence"].astype(str).str.lower().isin(["medium", "low"])
    ].copy()

    if review_rows.empty:
        return pd.DataFrame()

    account_col = _get_account_col(review_rows)

    return pd.DataFrame({
        "Source": source,
        "Section": review_rows.get("Report Section", ""),
        "Account": review_rows[account_col],
        "ITR Ref": review_rows.get("ITR Ref", ""),
        "ITR Label": review_rows.get("ITR Label", ""),
        "Treatment": review_rows.get("Treatment", ""),
        "Review Note": review_rows.get("Review Note", ""),
        "Reason": review_rows.get("Label Reason", ""),
    })