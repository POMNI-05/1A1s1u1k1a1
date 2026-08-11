# v1/workpaper_builder.py
"""Build accountant-style workpaper data blocks."""

from __future__ import annotations

from dataclasses import dataclass
import logging
import re
from typing import Any

import pandas as pd

try:
    from .cleaner import CleanedReports, load_clean_report_bundle, clean_amount
    from .config import (
        AUTO_POST_TAX_DEPRECIATION_TO_7F,
        COMPANY_TAX_RATE_CATEGORY,
        RD_BREAKDOWN_TEMPLATE,
        RD_OFFSET_AMOUNT,
        SELECTED_ATO_POLICY,
        SELECTED_INCOME_YEAR,
        TAX_ADJUSTMENTS,
        TAX_RATE,
    )
    from .itr_metadata import WORKSHEET_2, validate_adjustment_label, get_item7_direction
    from .job_config import table_requested
    from .labeller import label_report, extract_review_items
except ImportError:  # Direct-script compatibility.
    from cleaner import CleanedReports, load_clean_report_bundle, clean_amount
    from config import (
        AUTO_POST_TAX_DEPRECIATION_TO_7F,
        COMPANY_TAX_RATE_CATEGORY,
        RD_BREAKDOWN_TEMPLATE,
        RD_OFFSET_AMOUNT,
        SELECTED_ATO_POLICY,
        SELECTED_INCOME_YEAR,
        TAX_ADJUSTMENTS,
        TAX_RATE,
    )
    from itr_metadata import WORKSHEET_2, validate_adjustment_label, get_item7_direction
    from job_config import table_requested
    from labeller import label_report, extract_review_items

from tax_calculators.company_tax import calculate_company_tax

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
    proposed_adjustments: pd.DataFrame
    support_tables: dict[str, pd.DataFrame]


SUPPORT_TABLE_TEMPLATES: dict[str, tuple[str, list[dict[str, Any]]]] = {
    "div7a": (
        "Division 7A / Shareholder Loans",
        [{"Description": "Closing shareholder/director loan balance", "Amount": None, "Review note": "Confirm debit/credit balance and Division 7A treatment."}],
    ),
    "fbt_entertainment": (
        "FBT / Entertainment Review",
        [{"Description": "Entertainment and meal expenses", "Amount": None, "Review note": "Confirm deductibility, GST and FBT treatment."}],
    ),
    "depreciation": (
        "Tax Depreciation / Capital Allowances",
        [{"Description": "Tax decline in value deduction", "Amount": None, "Review note": "Agree to reviewed tax depreciation schedule before posting at 7F."}],
    ),
    "superannuation": (
        "Superannuation Timing",
        [{"Description": "Accrued or unpaid superannuation", "Amount": None, "Review note": "Confirm payment date and deductibility."}],
    ),
    "gst_reconciliation": (
        "GST / BAS Reconciliation",
        [{"Description": "GST control account difference", "Amount": None, "Review note": "Reconcile ledger to lodged BAS."}],
    ),
    "related_party_loans": (
        "Related-party Loans",
        [{"Description": "Related-party loan balance", "Amount": None, "Review note": "Confirm counterparty, terms, interest and cross-border implications."}],
    ),
    "psi": (
        "Personal Services Income Review",
        [{"Description": "PSI/PSE review", "Amount": None, "Review note": "Complete PSI tests and attribution review where applicable."}],
    ),
}

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

    Safety:
    - Uploaded workbooks may already contain old ITR/output columns.
    - labeller.py then appends fresh ITR columns.
    - If duplicate column names exist, rows["ITR Ref"] returns a DataFrame,
      not a Series, causing: AttributeError: 'DataFrame' object has no attribute 'str'.
    - This function removes duplicate columns defensively before string operations.
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

    rows = labelled_df.copy()

    # Defensive cleanup: duplicate columns can happen when source files already
    # contain old generated labels such as ITR Ref / Review Note.
    rows = rows.loc[:, ~rows.columns.duplicated()].copy()

    amount_cols = _detect_amount_cols(rows)
    if not amount_cols:
        return pd.DataFrame(columns=columns)

    amount_col = amount_cols[0]

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

        # Extra defensive guard: if duplicate columns survived for any reason,
        # take the first matching column as a Series.
        value = rows[col]
        if isinstance(value, pd.DataFrame):
            value = value.iloc[:, 0]

        rows[col] = value.astype(str).str.strip()

    rows = rows[rows["Workpaper Label"].ne("")].copy()
    rows = rows[rows["ITR Ref"].ne("Review")].copy()

    if not include_support_only:
        rows = rows[~rows["Treatment"].str.lower().eq("support_only")].copy()

    if rows.empty:
        return pd.DataFrame(columns=columns)

    rows["_Amount"] = rows[amount_col].apply(clean_amount)

    # Source Row may be missing in some imported/legacy reports.
    if "Source Row" not in rows.columns:
        rows["Source Row"] = ""

    grouped = (
        rows.groupby(
            ["Workpaper Label", "ITR Ref", "ITR Label", "Treatment"],
            dropna=False,
        )
        .agg(
            Amount=("_Amount", "sum"),
            Confidence=("Confidence", lambda s: _worst_confidence(s.tolist())),
            Review_Note=("Review Note", lambda s: "; ".join(sorted({x for x in s if x}))),
            Source_Rows=(
                "Source Row",
                lambda s: ", ".join(
                    str(int(x)) for x in s if pd.notna(x) and str(x).strip() != ""
                ),
            ),
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

    excluded = names.str.contains(
        r"after tax|\bnpat\b|attributable|comprehensive income",
        regex=True,
        na=False,
    )
    candidates = candidates[~excluded].copy()
    names = _row_names(candidates, account_col)

    priorities = [
        (r"accounting profit(?:/\(loss\))? (?:before tax|pre[- ]?tax)", "Accounting profit before tax"),
        (r"profit(?:/\(loss\))? (?:before tax|pre[- ]?tax)", "Profit before tax"),
        (r"net profit(?:/\(loss\))? (?:before tax|pre[- ]?tax)", "Net profit before tax"),
        (r"net profit|net loss|net profit / loss|net profit/\(loss\)", "Unambiguous net profit"),
    ]

    for pattern, method in priorities:
        matched = candidates[names.str.fullmatch(pattern, na=False)]
        if not matched.empty:
            row = matched.iloc[-1]
            return (
                {str(col): clean_amount(row.get(col, 0.0)) for col in amount_cols},
                f"Reported {method} row",
            )

    return {str(col): 0.0 for col in amount_cols}, "PROFIT-001: pre-tax accounting profit row not found"


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

    final = {}
    methods = {}

    for period, reported_value in reported.items():
        fallback_value = fallback.get(period, 0.0)

        if abs(reported_value) < 0.005 and abs(fallback_value) > 0.005:
            final[period] = fallback_value
            methods[period] = fallback_method
        else:
            final[period] = reported_value
            methods[period] = reported_method

    return final, methods


def _requested_period(periods: list[str]) -> str | None:
    matches = [period for period in periods if str(SELECTED_INCOME_YEAR) in str(period)]
    if len(matches) == 1:
        return matches[0]
    if not matches and len(periods) == 1:
        return periods[0]
    return None


def _get_adjustment_amount(
    adj: dict[str, Any],
    period: str,
    requested_period: str | None,
) -> float:
    if "amounts" in adj:
        return float(adj.get("amounts", {}).get(period, 0.0))
    # A scalar reviewed adjustment belongs to the requested income year only.
    # Repeating it across every source period would fabricate historical data.
    if period != requested_period:
        return 0.0
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
    requested_period = _requested_period(periods)

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
                # Preserve deliberate reversals/credits entered by the reviewer.
                amount = _get_adjustment_amount(adj, period, requested_period)
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

        auto_post = str(row.get("Auto Post", "") or "").strip().lower()
        if auto_post not in {"yes", "true", "1", "approved"}:
            # Rule matches are proposals. They must not change taxable income
            # unless an accountant has explicitly approved automatic posting.
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
            amount = clean_amount(row.get(period, 0.0))
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


def _build_proposed_adjustments(
    labelled_pl: pd.DataFrame,
    periods: list[str],
) -> pd.DataFrame:
    columns = [
        "Account",
        "ITR Ref",
        "Direction",
        *periods,
        "Treatment",
        "Confidence",
        "Approval Status",
        "Review Note",
    ]

    if labelled_pl is None or labelled_pl.empty:
        return pd.DataFrame(columns=columns)

    account_col = _get_account_col(labelled_pl)
    proposals: list[dict[str, Any]] = []

    for _, row in labelled_pl.iterrows():
        if str(row.get("Row Type", "") or "").strip().lower() != "account":
            continue

        recon_ref = str(
            row.get("Recon Display Ref", "")
            or row.get("Recon ITR Ref", "")
            or ""
        ).strip()
        if not recon_ref:
            continue

        auto_post = str(row.get("Auto Post", "") or "").strip().lower()
        proposal: dict[str, Any] = {
            "Account": str(row.get(account_col, "") or "").strip(),
            "ITR Ref": recon_ref,
            "Direction": str(row.get("Recon Direction", "") or "").strip(),
            "Treatment": str(row.get("Treatment", "") or "").strip(),
            "Confidence": str(row.get("Confidence", "") or "").strip(),
            "Approval Status": (
                "Approved for posting"
                if auto_post in {"yes", "true", "1", "approved"}
                else "Review required - not posted"
            ),
            "Review Note": str(row.get("Review Note", "") or "").strip(),
        }
        for period in periods:
            proposal[period] = clean_amount(row.get(period, 0.0))
        proposals.append(proposal)

    return pd.DataFrame(proposals, columns=columns)


def _tax_depreciation_reconciliation_rows(
    periods: list[str],
    tax_depreciation_total: float | None,
    tax_depreciation_source: str | None,
) -> tuple[list[dict], dict[str, float]]:
    """Optionally post extracted tax depreciation to 7F.

    Safe default is controlled by AUTO_POST_TAX_DEPRECIATION_TO_7F=False.
    When enabled, this posts the amount to the uniquely requested period.
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

    requested_period = _requested_period(periods)
    if requested_period is None:
        logger.warning(
            "PERIOD-001: tax depreciation was not posted because the requested period is ambiguous"
        )
        return rows, total_subtractions

    for period in periods:
        amount = float(tax_depreciation_total) if period == requested_period else 0.0
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
        "ITR Ref": "6T",
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
        "ITR Ref": "7T",
        "Review note": "",
    }

    for period in periods:
        taxable_row[period] = taxable_income[period]

    rows.append(taxable_row)

    requested_period = _requested_period(periods)
    tax_rate_label = f"{TAX_RATE:.0%}" if TAX_RATE is not None else "review required"
    tax_row = {
        "Line Type": "detail",
        "Description": f"Indicative tax on taxable income - rate {tax_rate_label}",
        "ITR Ref": "",
        "Review note": (
            "Tax is calculated only for the requested income year. Other source periods "
            "are intentionally blank."
            if TAX_RATE is not None
            else "Select and confirm the company tax rate before relying on tax payable."
        ),
    }

    tax_payable_by_period = {}

    for period in periods:
        taxable_amount = max(taxable_income[period], 0.0)
        if TAX_RATE is None or period != requested_period:
            tax_payable = None
        else:
            tax_result = calculate_company_tax(
                SELECTED_INCOME_YEAR,
                taxable_income=str(taxable_amount),
                rate_category=COMPANY_TAX_RATE_CATEGORY,
                base_rate_eligibility_confirmed=(
                    COMPANY_TAX_RATE_CATEGORY == "base_rate_entity"
                ),
            )
            tax_payable = float(tax_result.gross_tax)
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
        "Description": "Indicative tax after entered R&D offset",
        "ITR Ref": "",
        "Review note": (
            "Does not include all tax offsets, credits, instalments or "
            "special-rate calculations."
        ),
    }

    for period in periods:
        tax_payable = tax_payable_by_period[period]

        if tax_payable is None:
            rd_offset_row[period] = RD_OFFSET_AMOUNT
            final_tax_row[period] = None
        elif RD_OFFSET_AMOUNT is None:
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

    source_registry = SELECTED_ATO_POLICY["source_registry"]
    policy_row = _blank_periods(
        {
            "Line Type": "note",
            "Description": (
                f"ATO rule pack {SELECTED_INCOME_YEAR} "
                f"(verified {source_registry['verified_on']})"
            ),
            "ITR Ref": "",
            "Review note": (
                "Rates and thresholds loaded from the versioned rule registry; "
                "review client eligibility and judgment-dependent treatments."
            ),
        },
        periods,
    )
    rows.append(policy_row)

    ordered_cols = ["Line Type", "Description"] + periods + ["ITR Ref", "Review note"]

    return pd.DataFrame(rows)[ordered_cols]


def _build_carry_forward_losses_input(periods: list[str]) -> pd.DataFrame:
    """Create blank reviewer inputs only for periods validated from the source report."""
    return pd.DataFrame(
        [
            {
                "Period": period,
                "Opening losses": None,
                "Losses utilised": None,
                "New losses incurred": None,
                "Closing losses": None,
                "Status": "REVIEW INPUT REQUIRED",
            }
            for period in periods
        ]
    )


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

    account_col = _get_account_col(clean_bs_df)
    available_names = set(_row_names(clean_bs_df, account_col).tolist())
    has_assets = "total assets" in available_names
    has_liabilities = "total liabilities" in available_names
    has_equity = "total equity" in available_names
    has_net_assets = "net assets" in available_names

    equity_variance = {
        "Check": "TEST CHECK equity variance",
        "Calculation": "Total Assets - Total Liabilities - Total Equity",
        "Status": "TESTED" if has_assets and has_liabilities and has_equity else "NOT TESTED - BS-001",
    }

    net_assets_variance = {
        "Check": "TEST CHECK net assets variance",
        "Calculation": "Net Assets - (Total Assets - Total Liabilities)",
        "Status": "TESTED" if has_net_assets and has_assets and has_liabilities else "NOT TESTED - BS-001",
    }

    for period in amount_cols:
        equity_variance[period] = None if equity_variance["Status"].startswith("NOT TESTED") else round(
            total_assets.get(period, 0.0)
            - total_liabilities.get(period, 0.0)
            - total_equity.get(period, 0.0),
            2,
        )

        net_assets_variance[period] = None if net_assets_variance["Status"].startswith("NOT TESTED") else round(
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

    periods = list(_extract_net_profit_by_period(clean_pl_df)[0].keys())

    carry_forward_losses = (
        _build_carry_forward_losses_input(periods)
        if table_requested("carry_forward_losses")
        else pd.DataFrame()
    )
    rd_breakdown = (
        pd.DataFrame(RD_BREAKDOWN_TEMPLATE)
        if table_requested("rd_tax_incentive")
        else pd.DataFrame()
    )

    support_tables = {
        title: pd.DataFrame(rows)
        for key, (title, rows) in SUPPORT_TABLE_TEMPLATES.items()
        if table_requested(key)
    }

    proposed_adjustments = _build_proposed_adjustments(labelled_pl, periods)

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
        proposed_adjustments=proposed_adjustments,
        support_tables=support_tables,
    )
