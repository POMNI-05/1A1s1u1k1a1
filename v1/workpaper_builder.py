# v1/workpaper_builder.py
"""Build accountant-style workpaper data blocks."""

from __future__ import annotations

from dataclasses import dataclass
import logging
import re
from typing import Any

import pandas as pd

from cleaner import CleanedReports, load_clean_report_bundle, clean_amount
from config import (
    AUTO_POST_TAX_DEPRECIATION_TO_7F,
    CARRY_FORWARD_LOSSES_TEMPLATE,
    RD_BREAKDOWN_TEMPLATE,
    RD_OFFSET_AMOUNT,
    TAX_ADJUSTMENTS,
    TAX_RATE,
)
from itr_metadata import WORKSHEET_2, validate_adjustment_label, get_item7_direction
from labeller import label_report, extract_review_items

logger = logging.getLogger(__name__)

@dataclass
class Workpaper:
    labelled_pl: pd.DataFrame
    labelled_bs: pd.DataFrame

    pl_label_summary: pd.DataFrame
    bs_label_summary: pd.DataFrame

    tax_reconciliation: pd.DataFrame
    carry_forward_losses: pd.DataFrame
    rd_breakdown: pd.DataFrame
    bs_checks: pd.DataFrame
    review_items: pd.DataFrame

def _get_account_col(df: pd.DataFrame) -> str:
    for col in df.columns:
        if str(col).strip().lower() in {"account", "description", "account name"}:
            return col
    return df.columns[0]


def _detect_amount_cols(df: pd.DataFrame) -> list[str]:
    helper_cols = {
        "source row",
        "row type",
        "report section",
        "itr ref",
        "itr label",
        "workpaper label",
        "treatment",
        "confidence",
        "review note",
        "label reason",
        "recon itr ref",
        "line type",
        "description",
        "source",
        "calculation",
        "direction",
        "check",
        "explanation",
        "source file",
        "source sheet",
        "detected report type",
    }

    amount_cols = []

    for col in df.columns:
        lower = str(col).strip().lower()

        if lower in helper_cols:
            continue

        if lower in {"account", "account name", "description"}:
            continue

        if "variance" in lower or "%" in lower:
            continue

        if (
            str(col).strip().isdigit()
            or lower.startswith("30 jun")
            or lower.startswith("30 june")
            or re.search(r"\b20\d{2}\b", lower)
        ):
            amount_cols.append(col)

    return amount_cols

def _build_label_summary(
    labelled_df: pd.DataFrame,
    report_name: str,
    include_support_only: bool = False,
) -> pd.DataFrame:
    """
    Build a review-friendly summary of labels and totals.

    This summarises by Workpaper Label, not only ITR Ref.
    That means label-only rows such as:
    - Operating expense
    - Cash / bank support
    - Current asset support
    still appear in the summary.
    """
    columns = [
        "Source",
        "Workpaper Label",
        "ITR Ref",
        "ITR Label",
        "Amount",
        "Confidence",
        "Treatment",
        "Review Note",
        "Source Rows",
    ]

    if labelled_df is None or labelled_df.empty:
        return pd.DataFrame(columns=columns)

    amount_cols = _detect_amount_cols(labelled_df)
    if not amount_cols:
        return pd.DataFrame(columns=columns)

    amount_col = amount_cols[0]
    rows = labelled_df.copy()

    if "Row Type" in rows.columns:
        rows = rows[
            rows["Row Type"].astype(str).str.lower().isin(["account", "total"])
        ].copy()

    if rows.empty:
        return pd.DataFrame(columns=columns)

    for col in [
        "Workpaper Label",
        "ITR Ref",
        "ITR Label",
        "Treatment",
        "Confidence",
        "Review Note",
    ]:
        if col not in rows.columns:
            rows[col] = ""

        rows[col] = rows[col].astype(str).str.strip()

    rows = rows[rows["Workpaper Label"].ne("")].copy()
    rows = rows[rows["ITR Ref"].ne("Review")].copy()

    if not include_support_only:
        rows = rows[~rows["Treatment"].str.lower().eq("support_only")].copy()

    if rows.empty:
        return pd.DataFrame(columns=columns)

    rows["_Amount"] = rows[amount_col].apply(clean_amount)

    grouped = (
        rows.groupby(
            ["Workpaper Label", "ITR Ref", "ITR Label", "Treatment"],
            dropna=False,
        )
        .agg(
            Amount=("_Amount", "sum"),
            Confidence=("Confidence", lambda s: _worst_confidence(s.tolist())),
            Review_Note=("Review Note", lambda s: "; ".join(sorted({x for x in s if x}))),
            Source_Rows=("Source Row", lambda s: ", ".join(str(int(x)) for x in s if pd.notna(x))),
        )
        .reset_index()
    )

    grouped.insert(0, "Source", report_name)
    grouped = grouped.rename(
        columns={
            "Review_Note": "Review Note",
            "Source_Rows": "Source Rows",
        }
    )

    return grouped[columns]

def _worst_confidence(values: list[str]) -> str:
    """
    Conservative confidence roll-up.

    If any row is low, the whole label total is low.
    If any row is medium, the whole label total is medium.
    Otherwise high.
    """
    cleaned = {str(v).strip().lower() for v in values if str(v).strip()}

    if "low" in cleaned:
        return "low"

    if "medium" in cleaned:
        return "medium"

    if "high" in cleaned:
        return "high"

    return ""

def _row_names(df: pd.DataFrame, account_col: str) -> pd.Series:
    return (
        df[account_col]
        .astype(str)
        .str.replace(r"\s+", " ", regex=True)
        .str.strip()
        .str.lower()
    )


def _extract_reported_net_profit(clean_pl_df: pd.DataFrame) -> tuple[dict[str, float], str]:
    account_col = _get_account_col(clean_pl_df)
    amount_cols = _detect_amount_cols(clean_pl_df)

    if "Row Type" in clean_pl_df.columns:
        candidates = clean_pl_df[
            clean_pl_df["Row Type"].astype(str).str.lower().eq("total")
        ].copy()
    else:
        candidates = clean_pl_df.copy()

    if candidates.empty:
        return {str(col): 0.0 for col in amount_cols}, "No total rows found"

    names = _row_names(candidates, account_col)

    net_profit_rows = candidates[
        names.str.fullmatch(
            r"net profit|net loss|net profit / loss|net profit/\(loss\)|profit before tax|accounting profit before tax",
            na=False,
        )
        | names.str.contains(
            r"\bnet profit\b|\bnet loss\b|\bprofit before tax\b|\baccounting profit\b",
            regex=True,
            na=False,
        )
    ]

    if net_profit_rows.empty:
        return {str(col): 0.0 for col in amount_cols}, "Net Profit / Profit Before Tax row not found"

    row = net_profit_rows.iloc[-1]
    return {str(col): clean_amount(row.get(col, 0.0)) for col in amount_cols}, "Reported Xero Net Profit / Profit Before Tax row"


def _calculate_net_profit_from_sections(clean_pl_df: pd.DataFrame) -> tuple[dict[str, float], str]:
    account_col = _get_account_col(clean_pl_df)
    amount_cols = _detect_amount_cols(clean_pl_df)

    if "Row Type" not in clean_pl_df.columns or "Report Section" not in clean_pl_df.columns:
        return {str(col): 0.0 for col in amount_cols}, "Fallback unavailable - missing Row Type or Report Section"

    accounts = clean_pl_df[
        clean_pl_df["Row Type"].astype(str).str.lower().eq("account")
    ].copy()

    if accounts.empty:
        return {str(col): 0.0 for col in amount_cols}, "Fallback unavailable - no account rows"

    result = {str(col): 0.0 for col in amount_cols}

    for _, row in accounts.iterrows():
        section = str(row.get("Report Section", "")).strip().lower()

        if section in {"trading income", "income", "revenue", "other income"}:
            sign = 1
        elif section in {"cost of sales", "operating expenses", "expenses"}:
            sign = -1
        else:
            continue

        for col in amount_cols:
            result[str(col)] += sign * clean_amount(row.get(col, 0.0))

    return result, "Fallback calculated from account rows by P&L section"


def _extract_net_profit_by_period(clean_pl_df: pd.DataFrame) -> tuple[dict[str, float], dict[str, str]]:
    reported, reported_method = _extract_reported_net_profit(clean_pl_df)
    fallback, fallback_method = _calculate_net_profit_from_sections(clean_pl_df)

    reported_all_zero = all(abs(v) < 0.005 for v in reported.values())
    fallback_has_values = any(abs(v) > 0.005 for v in fallback.values())

    final = {}
    methods = {}

    for period, reported_value in reported.items():
        fallback_value = fallback.get(period, 0.0)

        if reported_all_zero and fallback_has_values:
            final[period] = fallback_value
            methods[period] = fallback_method
        else:
            final[period] = reported_value
            methods[period] = reported_method

    return final, methods


def _get_adjustment_amount(adj: dict[str, Any], period: str) -> float:
    if "amounts" in adj:
        return float(adj.get("amounts", {}).get(period, 0.0))
    return float(adj.get("amount", 0.0))


def _blank_periods(row: dict, periods: list[str]) -> dict:
    for period in periods:
        row[period] = None
    return row


def _manual_adjustment_rows(periods: list[str]) -> tuple[list[dict], list[dict], dict[str, float], dict[str, float]]:
    add_rows: list[dict] = []
    subtract_rows: list[dict] = []
    total_add_backs = {period: 0.0 for period in periods}
    total_subtractions = {period: 0.0 for period in periods}

    for category, adjustments in TAX_ADJUSTMENTS.items():
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
            review_note = adj.get("review_note", adj.get("source", "Manual adjustment"))

            row = {
                "Line Type": "detail",
                "Description": description,
                "ITR Ref": itr_label,
                "Review note": review_note,
            }

            has_amount = False

            for period in periods:
                amount = abs(_get_adjustment_amount(adj, period))
                row[period] = amount

                if abs(amount) > 0.005:
                    has_amount = True

                if direction == "add":
                    total_add_backs[period] += amount
                elif direction == "subtract":
                    total_subtractions[period] += amount

            if not has_amount:
                continue

            if direction == "add":
                add_rows.append(row)
            elif direction == "subtract":
                subtract_rows.append(row)

    return add_rows, subtract_rows, total_add_backs, total_subtractions


def _auto_reconciliation_rows_from_labelled_pl(
    labelled_pl: pd.DataFrame,
    periods: list[str],
) -> tuple[list[dict], list[dict], dict[str, float], dict[str, float]]:
    add_rows: list[dict] = []
    subtract_rows: list[dict] = []
    total_add_backs = {period: 0.0 for period in periods}
    total_subtractions = {period: 0.0 for period in periods}

    if labelled_pl is None or labelled_pl.empty:
        return add_rows, subtract_rows, total_add_backs, total_subtractions

    account_col = _get_account_col(labelled_pl)

    rows = labelled_pl[
        labelled_pl.get("Row Type", "").astype(str).str.lower().eq("account")
    ].copy()

    for _, row in rows.iterrows():
        recon_ref = str(row.get("Recon ITR Ref", "") or "").strip()

        if not recon_ref:
            continue

        validate_adjustment_label(recon_ref, str(row.get(account_col, "")))
        direction = get_item7_direction(recon_ref)

        if direction not in {"add", "subtract"}:
            continue

        description = str(row.get(account_col, "") or "").strip()
        label_reason = str(row.get("Label Reason", "") or "").strip()
        review_note = str(row.get("Review Note", "") or "").strip()

        combined_note = review_note
        if label_reason:
            combined_note = f"{review_note} {label_reason}".strip()

        output_row = {
            "Line Type": "detail",
            "Description": description,
            "ITR Ref": recon_ref,
            "Review note": combined_note,
        }

        has_amount = False

        for period in periods:
            amount = abs(clean_amount(row.get(period, 0.0)))
            output_row[period] = amount

            if abs(amount) > 0.005:
                has_amount = True

            if direction == "add":
                total_add_backs[period] += amount
            elif direction == "subtract":
                total_subtractions[period] += amount

        if not has_amount:
            continue

        if direction == "add":
            add_rows.append(output_row)
        elif direction == "subtract":
            subtract_rows.append(output_row)

    return add_rows, subtract_rows, total_add_backs, total_subtractions


def _tax_depreciation_reconciliation_rows(
    periods: list[str],
    tax_depreciation_total: float | None,
    tax_depreciation_source: str | None,
) -> tuple[list[dict], dict[str, float]]:
    """Optionally post extracted tax depreciation to 7F.

    Safe default is controlled by AUTO_POST_TAX_DEPRECIATION_TO_7F=False.
    When enabled, this posts the amount to the first detected period.
    """
    rows: list[dict] = []
    total_subtractions = {period: 0.0 for period in periods}

    if not AUTO_POST_TAX_DEPRECIATION_TO_7F:
        return rows, total_subtractions

    if tax_depreciation_total is None or abs(tax_depreciation_total) < 0.005:
        return rows, total_subtractions

    if not periods:
        return rows, total_subtractions

    validate_adjustment_label("7F", "Tax depreciation / decline in value")

    row = {
        "Line Type": "detail",
        "Description": "Tax depreciation / decline in value",
        "ITR Ref": "7F",
        "Review note": f"Auto-posted from tax depreciation support schedule: {tax_depreciation_source or 'source not recorded'}",
    }

    for idx, period in enumerate(periods):
        amount = abs(tax_depreciation_total) if idx == 0 else 0.0
        row[period] = amount
        total_subtractions[period] += amount

    rows.append(row)
    return rows, total_subtractions


def _build_tax_reconciliation(
    clean_pl_df: pd.DataFrame,
    labelled_pl: pd.DataFrame,
    tax_depreciation_total: float | None = None,
    tax_depreciation_source: str | None = None,
) -> pd.DataFrame:
    net_profit_by_period, net_profit_methods = _extract_net_profit_by_period(clean_pl_df)
    periods = list(net_profit_by_period.keys())

    rows: list[dict] = []

    base_row = {
        "Line Type": "result",
        "Description": "Accounting Profit Before Tax",
        "ITR Ref": "7T",
        "Review note": "",
    }

    for period in periods:
        base_row[period] = net_profit_by_period[period]

    rows.append(base_row)

    auto_add_rows, auto_subtract_rows, auto_add_totals, auto_subtract_totals = _auto_reconciliation_rows_from_labelled_pl(
        labelled_pl,
        periods,
    )

    manual_add_rows, manual_subtract_rows, manual_add_totals, manual_subtract_totals = _manual_adjustment_rows(periods)

    tax_dep_rows, tax_dep_subtract_totals = _tax_depreciation_reconciliation_rows(
        periods,
        tax_depreciation_total,
        tax_depreciation_source,
    )

    add_rows = auto_add_rows + manual_add_rows
    subtract_rows = auto_subtract_rows + manual_subtract_rows + tax_dep_rows

    total_add_backs = {
        period: auto_add_totals[period] + manual_add_totals[period]
        for period in periods
    }

    total_subtractions = {
        period: (
            auto_subtract_totals[period]
            + manual_subtract_totals[period]
            + tax_dep_subtract_totals[period]
        )
        for period in periods
    }

    taxable_income = {
        period: net_profit_by_period[period] + total_add_backs[period] - total_subtractions[period]
        for period in periods
    }

    rows.append(_blank_periods({
        "Line Type": "heading",
        "Description": "Add back",
        "ITR Ref": "",
        "Review note": "",
    }, periods))

    if add_rows:
        rows.extend(add_rows)
    else:
        rows.append(_blank_periods({
            "Line Type": "placeholder",
            "Description": "No add-back entries identified",
            "ITR Ref": "",
            "Review note": "Add rules via Recon ITR Ref or TAX_ADJUSTMENTS.",
        }, periods))

    total_add_back_row = {
        "Line Type": "subtotal",
        "Description": "Total add backs",
        "ITR Ref": "",
        "Review note": "",
    }

    for period in periods:
        total_add_back_row[period] = total_add_backs[period]

    rows.append(total_add_back_row)

    rows.append(_blank_periods({
        "Line Type": "heading",
        "Description": "Subtract",
        "ITR Ref": "",
        "Review note": "",
    }, periods))

    if subtract_rows:
        rows.extend(subtract_rows)
    else:
        rows.append(_blank_periods({
            "Line Type": "placeholder",
            "Description": "No subtraction entries identified",
            "ITR Ref": "",
            "Review note": "Add rules via Recon ITR Ref or TAX_ADJUSTMENTS.",
        }, periods))

    total_subtract_row = {
        "Line Type": "subtotal",
        "Description": "Total subtractions",
        "ITR Ref": "",
        "Review note": "",
    }

    for period in periods:
        total_subtract_row[period] = total_subtractions[period]

    rows.append(total_subtract_row)

    taxable_row = {
        "Line Type": "result",
        "Description": "Taxable Income",
        "ITR Ref": "",
        "Review note": "",
    }

    for period in periods:
        taxable_row[period] = taxable_income[period]

    rows.append(taxable_row)

    tax_row = {
        "Line Type": "detail",
        "Description": f"Tax Payable at {TAX_RATE:.0%}",
        "ITR Ref": "",
        "Review note": "",
    }

    tax_payable_by_period = {}

    for period in periods:
        tax_payable = max(taxable_income[period], 0.0) * TAX_RATE
        tax_payable_by_period[period] = tax_payable
        tax_row[period] = tax_payable

    rows.append(tax_row)

    rd_offset_row = {
        "Line Type": "detail",
        "Description": "R&D offset",
        "ITR Ref": "",
        "Review note": "Manual input only.",
    }

    final_tax_row = {
        "Line Type": "result",
        "Description": "Tax Payable / (Refund due)",
        "ITR Ref": "",
        "Review note": "",
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

    method_row = {
        "Line Type": "note",
        "Description": "Accounting profit extraction note",
        "ITR Ref": "",
        "Review note": "",
    }

    for period in periods:
        method_row[period] = net_profit_methods.get(period, "")

    rows.append(method_row)

    ordered_cols = ["Line Type", "Description"] + periods + ["ITR Ref", "Review note"]

    return pd.DataFrame(rows)[ordered_cols]


def _extract_total_by_period(
    clean_df: pd.DataFrame,
    aliases: list[str],
    prefer_total: bool = True,
) -> dict[str, float]:
    account_col = _get_account_col(clean_df)
    amount_cols = _detect_amount_cols(clean_df)

    search_df = clean_df.copy()

    if prefer_total and "Row Type" in search_df.columns:
        total_df = search_df[
            search_df["Row Type"].astype(str).str.lower().eq("total")
        ].copy()

        if not total_df.empty:
            search_df = total_df

    names = _row_names(search_df, account_col)
    matched = pd.DataFrame()

    for alias in aliases:
        alias_text = alias.strip().lower()

        exact = search_df[names.eq(alias_text)]
        contains = search_df[names.str.contains(re.escape(alias_text), regex=True, na=False)]

        if not exact.empty:
            matched = exact
            break

        if not contains.empty:
            matched = contains
            break

    if matched.empty:
        return {str(col): 0.0 for col in amount_cols}

    row = matched.iloc[-1]
    return {str(col): clean_amount(row.get(col, 0.0)) for col in amount_cols}


def _build_bs_checks(clean_bs_df: pd.DataFrame) -> pd.DataFrame:
    amount_cols = [str(col) for col in _detect_amount_cols(clean_bs_df)]

    total_assets = _extract_total_by_period(clean_bs_df, ["total assets"])
    total_liabilities = _extract_total_by_period(clean_bs_df, ["total liabilities"])
    total_equity = _extract_total_by_period(clean_bs_df, ["total equity"])
    net_assets = _extract_total_by_period(clean_bs_df, ["net assets"])

    equity_variance = {
        "Check": "TEST CHECK equity variance",
        "Calculation": "Total Assets - Total Liabilities - Total Equity",
    }

    net_assets_variance = {
        "Check": "TEST CHECK net assets variance",
        "Calculation": "Net Assets - (Total Assets - Total Liabilities)",
    }

    for period in amount_cols:
        equity_variance[period] = round(
            total_assets.get(period, 0.0)
            - total_liabilities.get(period, 0.0)
            - total_equity.get(period, 0.0),
            2,
        )

        net_assets_variance[period] = round(
            net_assets.get(period, 0.0)
            - (total_assets.get(period, 0.0) - total_liabilities.get(period, 0.0)),
            2,
        )

    return pd.DataFrame([equity_variance, net_assets_variance])


def _build_tax_depreciation_review_item(reports: CleanedReports) -> pd.DataFrame:
    if reports.tax_depreciation_total is None:
        return pd.DataFrame()

    if AUTO_POST_TAX_DEPRECIATION_TO_7F:
        note = "Tax depreciation was auto-posted to 7F because AUTO_POST_TAX_DEPRECIATION_TO_7F=True."
        recon_ref = "7F"
    else:
        note = "Tax depreciation schedule detected. Review whether this should be claimed at 7F."
        recon_ref = ""

    return pd.DataFrame([
        {
            "Source": "Tax Depreciation",
            "Section": "Support schedule",
            "Account": "Tax depreciation / decline in value",
            "ITR Ref": "7F",
            "Recon ITR Ref": recon_ref,
            "Review Note": note,
            "Reason": f"Extracted total {reports.tax_depreciation_total} from {reports.tax_depreciation_source}.",
        }
    ])

def build_workpaper(reports: CleanedReports | None = None) -> Workpaper:
    """
    Build all output data blocks.

    Structure:
    - P&L evidence copied to its own tab.
    - BS evidence copied to its own tab.
    - Tax Reconciliation sheet contains:
      1. P&L block + side labels + P&L label summary
      2. BS block + side labels + BS label summary
      3. final tax reconciliation table
    """
    if reports is None:
        reports = load_clean_report_bundle()

    clean_pl_df = reports.clean_pl
    clean_bs_df = reports.clean_bs

    labelled_pl = label_report(clean_pl_df, "profit_and_loss")
    labelled_bs = label_report(clean_bs_df, "balance_sheet")

    pl_label_summary = _build_label_summary(
        labelled_pl,
        report_name="P&L",
        include_support_only=False,
    )

    bs_label_summary = _build_label_summary(
        labelled_bs,
        report_name="BS",
        include_support_only=False,
    )

    tax_reconciliation = _build_tax_reconciliation(
        clean_pl_df,
        labelled_pl,
        tax_depreciation_total=reports.tax_depreciation_total,
        tax_depreciation_source=reports.tax_depreciation_source,
    )

    bs_checks = _build_bs_checks(clean_bs_df)

    carry_forward_losses = pd.DataFrame(CARRY_FORWARD_LOSSES_TEMPLATE)
    rd_breakdown = pd.DataFrame(RD_BREAKDOWN_TEMPLATE)

    review_blocks = [
        extract_review_items(labelled_pl, "P&L"),
        extract_review_items(labelled_bs, "BS"),
        _build_tax_depreciation_review_item(reports),
    ]

    review_blocks = [df for df in review_blocks if df is not None and not df.empty]

    if review_blocks:
        review_items = pd.concat(review_blocks, ignore_index=True)
    else:
        review_items = pd.DataFrame(
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

    return Workpaper(
        labelled_pl=labelled_pl,
        labelled_bs=labelled_bs,
        pl_label_summary=pl_label_summary,
        bs_label_summary=bs_label_summary,
        tax_reconciliation=tax_reconciliation,
        carry_forward_losses=carry_forward_losses,
        rd_breakdown=rd_breakdown,
        bs_checks=bs_checks,
        review_items=review_items,
    )