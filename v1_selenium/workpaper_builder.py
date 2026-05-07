# v1_selenium/workpaper_builder.py

from __future__ import annotations
from config import TAX_RATE, TAX_ADJUSTMENTS, RD_OFFSET_AMOUNT

from dataclasses import dataclass
import logging
from typing import Any

import pandas as pd

from cleaner import load_clean_reports, clean_amount
from config import TAX_RATE, TAX_ADJUSTMENTS
from itr_rules import WORKSHEET_2, validate_adjustment_label
from labeller import label_report, extract_account_entries, extract_review_items

logger = logging.getLogger(__name__)


@dataclass
class Workpaper:
    labelled_pl: pd.DataFrame
    labelled_bs: pd.DataFrame
    tax_reconciliation: pd.DataFrame
    carry_forward_losses: pd.DataFrame
    rd_breakdown: pd.DataFrame


def _get_account_col(df: pd.DataFrame) -> str:
    for col in df.columns:
        if str(col).strip().lower() in {"account", "description", "account name"}:
            return col
    return df.columns[0]


def _detect_amount_cols(df: pd.DataFrame) -> list:
    helper_cols = {
        "row type",
        "report section",
        "itr ref",
        "itr label",
        "treatment",
        "confidence",
        "review note",
        "label reason",
    }

    amount_cols = []

    for col in df.columns:
        lower = str(col).strip().lower()

        if lower in helper_cols:
            continue

        if lower in {"account", "description", "account name"}:
            continue

        if "variance" in lower or "%" in lower:
            continue

        # Common Xero period columns
        if (
            str(col).strip().isdigit()
            or lower.startswith("30 jun")
            or lower.startswith("30 june")
            or "20" in lower
        ):
            amount_cols.append(col)

    return amount_cols


def _extract_net_profit_by_period(clean_pl_df: pd.DataFrame) -> dict[str, float]:
    """
    Extract Net Profit from original P&L total row.

    Important:
    We do NOT recalculate it.
    We trust the original Xero report total row.
    """
    account_col = _get_account_col(clean_pl_df)
    amount_cols = _detect_amount_cols(clean_pl_df)

    if "Row Type" in clean_pl_df.columns:
        candidates = clean_pl_df[
            clean_pl_df["Row Type"].astype(str).str.lower().eq("total")
        ].copy()
    else:
        candidates = clean_pl_df.copy()

    names = candidates[account_col].astype(str).str.strip().str.lower()

    net_profit_rows = candidates[
        names.str.fullmatch(r"net profit|net loss|net profit / loss|net profit/\(loss\)", na=False)
        | names.str.contains(r"\bnet profit\b|\bnet loss\b", regex=True, na=False)
    ]

    if net_profit_rows.empty:
        logger.warning("Could not find Net Profit total row. Falling back to last total row.")
        total_rows = candidates
        if "Row Type" in total_rows.columns:
            total_rows = total_rows[
                total_rows["Row Type"].astype(str).str.lower().eq("total")
            ]

        if total_rows.empty:
            raise ValueError("Could not extract Net Profit from P&L: no total rows found.")

        net_profit_row = total_rows.iloc[-1]
    else:
        net_profit_row = net_profit_rows.iloc[-1]

    result = {}

    for col in amount_cols:
        result[str(col)] = clean_amount(net_profit_row[col])

    return result


def _get_adjustment_amount(adj: dict[str, Any], period: str) -> float:
    """
    Supports:
        {"amount": 100}
    and:
        {"amounts": {"2026": 100, "2025": 50}}
    """
    if "amounts" in adj:
        return float(adj.get("amounts", {}).get(period, 0.0))

    return float(adj.get("amount", 0.0))


def _build_financial_data(labelled_pl: pd.DataFrame, labelled_bs: pd.DataFrame) -> pd.DataFrame:
    """
    Build left-side Tax Return Financial Data.

    Only actual accounting entries are included.
    Yellow headings and total/subtotal rows are excluded.
    """
    rows = []

    def append_entries(labelled_df: pd.DataFrame, source: str):
        if labelled_df is None or labelled_df.empty:
            return

        entries = extract_account_entries(labelled_df)

        if entries.empty:
            return

        account_col = _get_account_col(entries)
        amount_cols = _detect_amount_cols(entries)

        for _, row in entries.iterrows():
            out = {
                "Source": source,
                "Section": row.get("Report Section", ""),
                "Account": row.get(account_col, ""),
            }

            for col in amount_cols:
                out[str(col)] = row.get(col, 0.0)

            out["ITR Ref"] = row.get("ITR Ref", "")
            out["ITR Label"] = row.get("ITR Label", "")
            out["Treatment"] = row.get("Treatment", "")
            out["Confidence"] = row.get("Confidence", "")
            out["Review Note"] = row.get("Review Note", "")

            rows.append(out)

    append_entries(labelled_pl, "P&L")
    append_entries(labelled_bs, "BS")

    return pd.DataFrame(rows)


def _build_tax_reconciliation(clean_pl_df: pd.DataFrame) -> pd.DataFrame:
    """
    Build middle Tax Reconciliation block.

    Only:
    - original P&L Net Profit total row
    - configured TAX_ADJUSTMENTS

    affect taxable income.
    """
    net_profit_by_period = _extract_net_profit_by_period(clean_pl_df)
    periods = list(net_profit_by_period.keys())

    taxable_income = dict(net_profit_by_period)

    rows = []

    base_row = {
        "Section": "Base",
        "Description": "Accounting Profit / (Loss) Before Tax",
        "ITR Ref": "7T",
        "Direction": "base",
        "Source": "Original Xero P&L Net Profit row",
    }

    for period in periods:
        base_row[period] = net_profit_by_period[period]

    rows.append(base_row)

    for category, adjustments in TAX_ADJUSTMENTS.items():
        if not adjustments:
            continue

        rule = WORKSHEET_2.get(category)

        if rule is None:
            logger.warning("Unknown tax adjustment category skipped: %s", category)
            continue

        itr_label = rule["label"]
        direction = rule["direction"]
        heading = rule["heading"]

        validate_adjustment_label(itr_label, heading)

        for adj in adjustments:
            description = adj.get("description", heading)
            source = adj.get("source", "Manual adjustment")

            row_amounts = {}
            has_amount = False

            for period in periods:
                amount = _get_adjustment_amount(adj, period)
                row_amounts[period] = amount

                if amount != 0:
                    has_amount = True

            if not has_amount:
                continue

            row = {
                "Section": "Add back" if direction == "add" else "Subtract",
                "Description": description,
                "ITR Ref": itr_label,
                "Direction": direction,
                "Source": source,
            }

            for period in periods:
                amount = row_amounts[period]
                row[period] = amount

                if direction == "add":
                    taxable_income[period] += amount
                elif direction == "subtract":
                    taxable_income[period] -= amount

            rows.append(row)

    taxable_row = {
        "Section": "Result",
        "Description": "Taxable Income / (Loss)",
        "ITR Ref": "",
        "Direction": "calculated",
        "Source": "Accounting profit plus add-backs less deductions",
    }

    for period in periods:
        taxable_row[period] = taxable_income[period]

    rows.append(taxable_row)

    tax_row = {
        "Section": "Result",
        "Description": f"Estimated Tax Payable at {TAX_RATE:.0%}",
        "ITR Ref": "",
        "Direction": "calculated",
        "Source": "Tax rate from config.py",
    }

    for period in periods:
        tax_row[period] = max(taxable_income[period], 0.0) * TAX_RATE

    rows.append(tax_row)

    return pd.DataFrame(rows)


def _build_tax_reconciliation(clean_pl_df: pd.DataFrame) -> pd.DataFrame:
    """
    Build middle Tax Reconciliation block.

    Only:
    - original P&L Net Profit total row
    - configured TAX_ADJUSTMENTS

    affect taxable income.
    """
    net_profit_by_period = _extract_net_profit_by_period(clean_pl_df)
    periods = list(net_profit_by_period.keys())

    taxable_income = dict(net_profit_by_period)
    rows = []

    base_row = {
        "Section": "Base",
        "Description": "Accounting Profit / (Loss) Before Tax",
        "ITR Ref": "7T",
        "Direction": "base",
        "Source": "Original Xero P&L Net Profit row",
    }

    for period in periods:
        base_row[period] = net_profit_by_period[period]

    rows.append(base_row)

    for category, adjustments in TAX_ADJUSTMENTS.items():
        if not adjustments:
            continue

        rule = WORKSHEET_2.get(category)

        if rule is None:
            logger.warning("Unknown tax adjustment category skipped: %s", category)
            continue

        itr_label = rule["label"]
        direction = rule["direction"]
        heading = rule["heading"]

        validate_adjustment_label(itr_label, heading)

        for adj in adjustments:
            description = adj.get("description", heading)
            source = adj.get("source", "Manual adjustment")

            row_amounts = {}
            has_amount = False

            for period in periods:
                amount = _get_adjustment_amount(adj, period)
                row_amounts[period] = amount

                if amount != 0:
                    has_amount = True

            if not has_amount:
                continue

            row = {
                "Section": "Add back" if direction == "add" else "Subtract",
                "Description": description,
                "ITR Ref": itr_label,
                "Direction": direction,
                "Source": source,
            }

            for period in periods:
                amount = row_amounts[period]
                row[period] = amount

                if direction == "add":
                    taxable_income[period] += amount
                elif direction == "subtract":
                    taxable_income[period] -= amount

            rows.append(row)

    taxable_row = {
        "Section": "Result",
        "Description": "Taxable Income / (Loss)",
        "ITR Ref": "",
        "Direction": "calculated",
        "Source": "Accounting profit plus add-backs less deductions",
    }

    for period in periods:
        taxable_row[period] = taxable_income[period]

    rows.append(taxable_row)

    tax_row = {
        "Section": "Result",
        "Description": f"Tax Payable at {TAX_RATE:.0%}",
        "ITR Ref": "",
        "Direction": "calculated",
        "Source": "Tax rate from config.py",
    }

    tax_payable_by_period = {}

    for period in periods:
        tax_payable = max(taxable_income[period], 0.0) * TAX_RATE
        tax_payable_by_period[period] = tax_payable
        tax_row[period] = tax_payable

    rows.append(tax_row)

    rd_offset_row = {
        "Section": "Result",
        "Description": "R&D offset",
        "ITR Ref": "",
        "Direction": "manual",
        "Source": "Manual / R&D schedule input only",
    }

    final_tax_row = {
        "Section": "Result",
        "Description": "Tax Payable / (Refund due)",
        "ITR Ref": "",
        "Direction": "calculated",
        "Source": "Tax payable less R&D offset, if provided",
    }

    for period in periods:
        tax_payable = tax_payable_by_period[period]

        if RD_OFFSET_AMOUNT is None:
            rd_offset_row[period] = None
            final_tax_row[period] = tax_payable
        else:
            rd_offset_row[period] = RD_OFFSET_AMOUNT
            final_tax_row[period] = tax_payable - RD_OFFSET_AMOUNT

    rows.append(rd_offset_row)
    rows.append(final_tax_row)

    return pd.DataFrame(rows)

def _build_review_items(labelled_pl: pd.DataFrame, labelled_bs: pd.DataFrame) -> pd.DataFrame:
    pl_review = extract_review_items(labelled_pl, "P&L")
    bs_review = extract_review_items(labelled_bs, "BS")

    frames = [df for df in [pl_review, bs_review] if df is not None and not df.empty]

    if not frames:
        return pd.DataFrame(columns=[
            "Source",
            "Section",
            "Account",
            "ITR Ref",
            "ITR Label",
            "Treatment",
            "Review Note",
            "Reason",
        ])

    return pd.concat(frames, ignore_index=True)



def build_workpaper() -> Workpaper:
    """
    Build accountant-style workpaper data blocks.

    Raw PL / BS sheets are copied directly in write_workbook.py.
    This function only prepares labels and generated schedules.
    """
    clean_pl_df, clean_bs_df = load_clean_reports()

    labelled_pl = label_report(clean_pl_df, "profit_and_loss")
    labelled_bs = label_report(clean_bs_df, "balance_sheet")

    tax_reconciliation = _build_tax_reconciliation(clean_pl_df)

    carry_forward_losses = pd.DataFrame(CARRY_FORWARD_LOSSES_TEMPLATE)
    rd_breakdown = pd.DataFrame(RD_BREAKDOWN_TEMPLATE)

    return Workpaper(
        labelled_pl=labelled_pl,
        labelled_bs=labelled_bs,
        tax_reconciliation=tax_reconciliation,
        carry_forward_losses=carry_forward_losses,
        rd_breakdown=rd_breakdown,
    )

from config import (
    TAX_RATE,
    TAX_ADJUSTMENTS,
    CARRY_FORWARD_LOSSES_TEMPLATE,
    RD_BREAKDOWN_TEMPLATE,
    RD_OFFSET_AMOUNT,
)