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
        COMPANY_TAX_RATE_CATEGORY,
        RD_BREAKDOWN_TEMPLATE,
        SELECTED_ATO_POLICY,
        SELECTED_INCOME_YEAR,
        TAX_ADJUSTMENTS,
        TAX_RATE,
    )
    from .itr_metadata import WORKSHEET_2, validate_adjustment_label, get_item7_direction
    from .job_config import load_job_config, table_requested
    from .labeller import label_report, extract_review_items
    from .decision_trace import build_decision_traces, review_items_from_traces
except ImportError:  # Direct-script compatibility.
    from cleaner import CleanedReports, load_clean_report_bundle, clean_amount
    from config import (
        COMPANY_TAX_RATE_CATEGORY,
        RD_BREAKDOWN_TEMPLATE,
        SELECTED_ATO_POLICY,
        SELECTED_INCOME_YEAR,
        TAX_ADJUSTMENTS,
        TAX_RATE,
    )
    from itr_metadata import WORKSHEET_2, validate_adjustment_label, get_item7_direction
    from job_config import load_job_config, table_requested
    from labeller import label_report, extract_review_items
    from decision_trace import build_decision_traces, review_items_from_traces

from ai_review import DecisionTrace, ReviewItem
from tax_calculators.company_tax import calculate_company_tax

logger = logging.getLogger(__name__)

@dataclass
class Workpaper:
    labelled_pl: pd.DataFrame
    labelled_bs: pd.DataFrame

    pl_label_summary: pd.DataFrame
    bs_label_summary: pd.DataFrame

    tax_reconciliation: pd.DataFrame
    tax_reconciliation_review_checks: pd.DataFrame
    tax_calculation: pd.DataFrame
    carry_forward_losses: pd.DataFrame
    rd_breakdown: pd.DataFrame
    bs_checks: pd.DataFrame
    review_items: pd.DataFrame
    proposed_adjustments: pd.DataFrame
    support_tables: dict[str, pd.DataFrame]
    decision_traces: tuple[DecisionTrace, ...]
    deterministic_review_items: tuple[ReviewItem, ...]


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

        if lower.endswith(" parse status"):
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

    # Rule packs currently expose the authoritative ITR label, rather than a
    # separate Workpaper Label field.  Older summary code created a blank
    # Workpaper Label column then filtered every row out, producing "No labels
    # detected" beside visible 8G/8H side labels.  Derive the display label
    # from ITR Label when a pack has not provided a distinct workpaper label.
    if "Workpaper Label" not in rows.columns:
        rows["Workpaper Label"] = rows.get("ITR Label", "")

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


def _unapproved_reconciliation_rows_from_labelled_pl(
    labelled_pl: pd.DataFrame,
    periods: list[str],
) -> list[dict]:
    """Return visible Item 7 candidates that are deliberately excluded.

    A reconciliation with unresolved adjustments remains preliminary. The
    source-backed candidates are included in the preliminary calculation so a
    reviewer has a usable starting number, but remain separately marked for
    accountant approval before a lodged tax-return value is finalised.
    """

    if labelled_pl is None or labelled_pl.empty:
        return []

    account_col = _get_account_col(labelled_pl)
    rows = labelled_pl[
        labelled_pl.get("Row Type", "").astype(str).str.lower().eq("account")
    ].copy()
    candidates: list[dict] = []

    for _, row in rows.iterrows():
        recon_ref = str(
            row.get("Recon Display Ref", "")
            or row.get("Recon ITR Ref", "")
            or ""
        ).strip()
        direction = str(row.get("Recon Direction", "") or "").strip().lower()
        auto_post = str(row.get("Auto Post", "") or "").strip().lower()

        if (
            not recon_ref
            or direction not in {"add", "subtract"}
            or auto_post in {"yes", "true", "1", "approved"}
        ):
            continue

        validate_adjustment_label(recon_ref, str(row.get(account_col, "")))
        output_row = {
            "Line Type": f"review_{direction}",
            # Keep the calculation face short.  Proposal/approval evidence is
            # retained in the review note and Inputs & Overrides, not repeated
            # in every Tab 3 account description.
            "Description": str(row.get(account_col, "") or "").strip(),
            "ITR Ref": recon_ref,
            "Review note": (
                f"Included in preliminary calculation only; accountant approval "
                f"required before final lodgment. "
                f"{str(row.get('Review Note', '') or '').strip()}"
            ).strip(),
            # Internal calculation evidence.  This field is deliberately not
            # rendered in the workpaper; the visible description remains the
            # accountant-facing explanation.
            "_Scenario direction": direction,
        }
        has_amount = False
        for period in periods:
            amount = clean_amount(row.get(period, 0.0))
            output_row[period] = amount
            has_amount = has_amount or abs(amount) > 0.005

        if has_amount:
            candidates.append(output_row)

    return candidates


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
    reviewed_tax_depreciation_total: float | None,
    approved_for_posting: bool,
) -> tuple[list[dict], dict[str, float]]:
    """Post only an explicitly approved accountant-entered tax deduction to 7F."""
    rows: list[dict] = []
    total_subtractions = {period: 0.0 for period in periods}

    if (
        reviewed_tax_depreciation_total is None
        or not approved_for_posting
        or abs(reviewed_tax_depreciation_total) < 0.005
    ):
        return rows, total_subtractions

    if not periods:
        return rows, total_subtractions

    validate_adjustment_label("7F", "Tax depreciation / decline in value")

    row = {
        "Line Type": "detail",
        "Description": "Tax depreciation / decline in value",
        "ITR Ref": "7F",
        "Review note": "Posted from an explicitly accountant-approved 7F input.",
    }

    requested_period = _requested_period(periods)
    if requested_period is None:
        logger.warning(
            "PERIOD-001: tax depreciation was not posted because the requested period is ambiguous"
        )
        return rows, total_subtractions

    for period in periods:
        amount = float(reviewed_tax_depreciation_total) if period == requested_period else 0.0
        row[period] = amount
        total_subtractions[period] += amount

    rows.append(row)
    return rows, total_subtractions


def _detected_tax_depreciation_schedule_rows(
    periods: list[str],
    tax_depreciation_total: float | None,
    tax_depreciation_source: str | None,
    matches_selected_period: bool,
) -> list[dict]:
    """Return a matching tax-law schedule as a preliminary Item 7F deduction."""
    if (
        tax_depreciation_total is None
        or abs(float(tax_depreciation_total)) < 0.005
        or not matches_selected_period
        or not periods
    ):
        return []

    requested_period = _requested_period(periods)
    if requested_period is None:
        return []

    validate_adjustment_label("7F", "Tax depreciation / decline in value")
    row = {
        "Line Type": "detail",
        "Description": "Tax depreciation / decline in value",
        "ITR Ref": "7F",
        "Review note": (
            "Included in preliminary calculation from the detected tax-law "
            "depreciation schedule; accountant review may revise it before lodgment. "
            f"Source: {tax_depreciation_source or 'tax depreciation schedule'}"
        ),
        "_Scenario direction": "subtract",
    }
    for period in periods:
        row[period] = float(tax_depreciation_total) if period == requested_period else 0.0
    return [row]


def _reconciliation_completeness_rows(
    labelled_pl: pd.DataFrame,
    net_profit_methods: dict[str, str],
) -> tuple[list[dict], bool]:
    """Return evidence checks that explain whether Item 7T is final.

    These are review prompts, not inferred tax adjustments.  A detected
    account-name trigger requires accountant evidence before the Item 7 result
    can be treated as final; no source trigger is recorded as informational.
    """

    rows: list[dict] = []
    base_requires_review = any(
        "before tax" not in str(method).lower()
        for method in net_profit_methods.values()
    )
    base_method = "; ".join(sorted(set(net_profit_methods.values())))
    rows.append(
        {
            "Line Type": "review" if base_requires_review else "note",
            "Description": (
                "Item 6T base: confirm Net Profit excludes income tax expense"
                if base_requires_review
                else "Item 6T base: explicit profit before tax source"
            ),
            "ITR Ref": "6T",
            "Review note": base_method,
        }
    )

    names = ""
    if labelled_pl is not None and not labelled_pl.empty:
        account_col = _get_account_col(labelled_pl)
        names = " ".join(
            str(value or "").lower() for value in labelled_pl[account_col].tolist()
        )

    triggers = [
        (
            "CGT / asset-disposal check",
            r"capital gain|capital loss|disposal|sale of asset|balancing adjustment",
            "Check Item 7A, 7B, 7Q, 7W or 7X and any required CGT support.",
        ),
        (
            "Depreciation / capital-allowance check",
            r"depreciat|amortis|capital works|project pool|decline in value",
            "Check accounting depreciation add-back and reviewed Item 7F/7H/7I deductions.",
        ),
        (
            "Foreign income / TOFA check",
            r"foreign|forex|exchange gain|exchange loss|tofa",
            "Check the relevant Item 7B, 7E, 7Q, 7W or 7X treatment.",
        ),
        (
            "Tax-loss check",
            r"tax loss|prior year loss|carry.?forward loss",
            "Check eligibility and any Item 7R deduction before posting.",
        ),
        (
            "R&D check",
            r"research|r&d|rnd|development",
            "Check whether an R&D schedule/Item 7D and Item 21 claim are actually required.",
        ),
    ]

    triggered_count = 0
    for description, pattern, note in triggers:
        triggered = bool(re.search(pattern, names, flags=re.IGNORECASE))
        triggered_count += int(triggered)
        rows.append(
            {
                "Line Type": "review" if triggered else "note",
                "Description": (
                    f"{description}: REVIEW REQUIRED"
                    if triggered
                    else f"{description}: no source trigger detected"
                ),
                "ITR Ref": "",
                "Review note": note,
            }
        )

    return rows, base_requires_review or bool(triggered_count)


def _company_tax_precalculation_rows(
    periods: list[str],
    taxable_income: dict[str, float],
    includes_review_required_adjustments: bool,
) -> list[dict]:
    """Return company-tax pre-calculation rows for the Tab 3 workpaper.

    The calculation is deliberately on the reconciliation tab: it is the next
    step in the same review workflow, not a second source of truth.  Pending
    adjustments remain visible as review items, but do not suppress a useful
    pre-calculation.
    """

    if TAX_RATE is None:
        return []

    requested_period = _requested_period(periods)
    tax_row = {
        "Line Type": "result",
        "Description": f"Indicative company tax before offsets — rate {TAX_RATE:.0%}",
        "ITR Ref": "",
        "Review note": (
            "Pre-calculation includes review-required adjustments; accountant review may change the final amount."
            if includes_review_required_adjustments
            else "Calculation statement support only; offsets, credits and instalments are excluded."
        ),
    }
    for period in periods:
        taxable_amount = max(clean_amount(taxable_income[period]), 0.0)
        if period != requested_period:
            tax_row[period] = None
            continue
        result = calculate_company_tax(
            SELECTED_INCOME_YEAR,
            taxable_income=str(taxable_amount),
            rate_category=COMPANY_TAX_RATE_CATEGORY,
            base_rate_eligibility_confirmed=(
                COMPANY_TAX_RATE_CATEGORY == "base_rate_entity"
            ),
        )
        tax_row[period] = float(result.gross_tax)
    return [tax_row]


def _build_tax_reconciliation(
    clean_pl_df: pd.DataFrame,
    labelled_pl: pd.DataFrame,
    tax_depreciation_total: float | None = None,
    tax_depreciation_source: str | None = None,
    tax_depreciation_matches_selected_period: bool = False,
    reviewed_tax_depreciation_total: float | None = None,
    tax_depreciation_approved_for_posting: bool = False,
) -> pd.DataFrame:
    net_profit_by_period, net_profit_methods = _extract_net_profit_by_period(clean_pl_df)
    periods = list(net_profit_by_period.keys())

    rows: list[dict] = []

    base_row = {
        "Line Type": "result",
        "Description": "Accounting profit/(loss) — Item 6T",
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
        reviewed_tax_depreciation_total,
        tax_depreciation_approved_for_posting,
    )

    add_rows = auto_add_rows + manual_add_rows
    subtract_rows = auto_subtract_rows + manual_subtract_rows + tax_dep_rows
    unapproved_rows = _unapproved_reconciliation_rows_from_labelled_pl(
        labelled_pl,
        periods,
    )
    # An approved accountant amount is authoritative and must not be counted
    # again as detected schedule evidence.  Otherwise a matching tax-law
    # schedule is useful preliminary 7F evidence for the later review.
    if not (
        reviewed_tax_depreciation_total is not None
        and tax_depreciation_approved_for_posting
    ):
        unapproved_rows.extend(
            _detected_tax_depreciation_schedule_rows(
                periods,
                tax_depreciation_total,
                tax_depreciation_source,
                tax_depreciation_matches_selected_period,
            )
        )

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

    scenario_taxable_income = dict(taxable_income)
    preliminary_add_backs = dict(total_add_backs)
    preliminary_subtractions = dict(total_subtractions)
    for pending_row in unapproved_rows:
        direction = pending_row.get("_Scenario direction")
        for period in periods:
            amount = clean_amount(pending_row.get(period, 0.0))
            if direction == "add":
                scenario_taxable_income[period] += amount
                preliminary_add_backs[period] += amount
            elif direction == "subtract":
                scenario_taxable_income[period] -= amount
                preliminary_subtractions[period] += amount

    # Tab 3 is a short calculation bridge.  Approved and review-required
    # proposals both feed the preliminary number, while each row's review note
    # remains the audit evidence for the later accountant review.
    review_add_rows = [
        row for row in unapproved_rows if row.get("_Scenario direction") == "add"
    ]
    review_subtract_rows = [
        row for row in unapproved_rows if row.get("_Scenario direction") == "subtract"
    ]
    for row in review_add_rows + review_subtract_rows:
        row["Line Type"] = "detail"

    if add_rows or review_add_rows:
        rows.append(_blank_periods({
            "Line Type": "add_heading",
            "Description": "ADD",
            "ITR Ref": "",
            "Review note": "Add these amounts to accounting profit/(loss).",
        }, periods))
        rows.extend(add_rows + review_add_rows)
        total_add_row = {
            "Line Type": "subtotal",
            "Description": "Total ADD",
            "ITR Ref": "",
            "Review note": "",
        }
        for period in periods:
            total_add_row[period] = preliminary_add_backs[period]
        rows.append(total_add_row)

    if subtract_rows or review_subtract_rows:
        rows.append(_blank_periods({
            "Line Type": "subtract_heading",
            "Description": "SUBTRACT",
            "ITR Ref": "",
            "Review note": "Subtract these amounts from accounting profit/(loss).",
        }, periods))
        rows.extend(subtract_rows + review_subtract_rows)
        total_subtract_row = {
            "Line Type": "subtotal",
            "Description": "Total SUBTRACT",
            "ITR Ref": "",
            "Review note": "",
        }
        for period in periods:
            total_subtract_row[period] = preliminary_subtractions[period]
        rows.append(total_subtract_row)

    completeness_rows, completeness_requires_review = _reconciliation_completeness_rows(
        labelled_pl,
        net_profit_methods,
    )
    is_preliminary = bool(unapproved_rows) or completeness_requires_review

    preliminary_taxable_income = (
        scenario_taxable_income if unapproved_rows else taxable_income
    )
    taxable_row = {
        "Line Type": "result",
        "Description": (
            "Preliminary taxable income/(loss) — Item 7T"
            if unapproved_rows
            else "Preliminary taxable income/(loss) — review required"
            if completeness_requires_review
            else "Taxable/net income or loss — Item 7T"
        ),
        "ITR Ref": "7T (preliminary)" if is_preliminary else "7T",
        "Review note": (
            "Pre-calculation only: accountant review may revise this before the final lodged Item 7T."
            if is_preliminary
            else ""
        ),
        "Tax return code": (
            "L (preliminary)" if is_preliminary else "L"
        ) if (
            _requested_period(periods) is not None
            and preliminary_taxable_income[_requested_period(periods)] < 0
        ) else "",
    }

    for period in periods:
        taxable_row[period] = preliminary_taxable_income[period]

    rows.append(taxable_row)

    ordered_cols = [
        "Line Type",
        "Description",
        *periods,
        "ITR Ref",
        "Tax return code",
        "Review note",
    ]

    return pd.DataFrame(rows)[ordered_cols]


def _build_tax_reconciliation_review_checks(
    clean_pl_df: pd.DataFrame,
    labelled_pl: pd.DataFrame,
) -> pd.DataFrame:
    """Keep fact-triggered Item 7 review checks out of the calculation bridge."""

    _, net_profit_methods = _extract_net_profit_by_period(clean_pl_df)
    rows, _ = _reconciliation_completeness_rows(labelled_pl, net_profit_methods)
    review_rows = [row for row in rows if row.get("Line Type") == "review"]
    return pd.DataFrame([
        {
            "Check": row["Description"],
            "Status": "REVIEW REQUIRED",
            "ITR Ref": row.get("ITR Ref", ""),
            "Detail": row.get("Review note", ""),
        }
        for row in review_rows
    ])


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

    if reports.tax_depreciation_matches_selected_period and abs(reports.tax_depreciation_total) >= 0.005:
        note = (
            "Matching tax-law depreciation schedule detected. Its total is included "
            "in preliminary Item 7F and remains subject to accountant review."
        )
    elif not reports.tax_depreciation_matches_selected_period:
        note = (
            "Tax depreciation schedule detected for a different income year; it is "
            "support evidence only and is not used in the selected-year Item 7F."
        )
    else:
        note = (
            "Tax depreciation schedule detected, but its extracted total is zero; "
            "it is support evidence only and is not used in preliminary Item 7F."
        )
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

    depreciation_input = (load_job_config().get("reviewed_tax_depreciation") or {})
    reviewed_tax_depreciation_total = None
    if table_requested("depreciation") and depreciation_input.get("amount") is not None:
        reviewed_tax_depreciation_total = clean_amount(depreciation_input["amount"])
        if reviewed_tax_depreciation_total < 0:
            raise ValueError("DEPR-003: reviewed tax depreciation must not be negative")
    tax_depreciation_approved_for_posting = bool(
        table_requested("depreciation")
        and depreciation_input.get("approved_for_posting") is True
    )

    labelled_pl = label_report(clean_pl_df, "profit_and_loss")
    labelled_bs = label_report(clean_bs_df, "balance_sheet")
    decision_traces = (
        *build_decision_traces(
            labelled_pl,
            report_type="profit_and_loss",
            income_year=SELECTED_INCOME_YEAR,
        ),
        *build_decision_traces(
            labelled_bs,
            report_type="balance_sheet",
            income_year=SELECTED_INCOME_YEAR,
        ),
    )
    deterministic_review_items = review_items_from_traces(decision_traces)

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
        tax_depreciation_matches_selected_period=reports.tax_depreciation_matches_selected_period,
        reviewed_tax_depreciation_total=reviewed_tax_depreciation_total,
        tax_depreciation_approved_for_posting=tax_depreciation_approved_for_posting,
    )
    tax_reconciliation_review_checks = _build_tax_reconciliation_review_checks(
        clean_pl_df,
        labelled_pl,
    )
    # Company-tax pre-calculation is part of Tab 3.  Keep this empty legacy
    # payload so the writer does not create a duplicate Tax Calculation sheet.
    tax_calculation = pd.DataFrame()

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
    depreciation_table = support_tables.get("Tax Depreciation / Capital Allowances")
    if depreciation_table is not None and not depreciation_table.empty:
        depreciation_table.loc[0, "Amount"] = reviewed_tax_depreciation_total
        depreciation_table.loc[0, "Review note"] = (
            "Approved for posting at 7F."
            if tax_depreciation_approved_for_posting
            else "Enter/confirm the reviewed deduction and obtain accountant approval before posting at 7F."
        )

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
        tax_reconciliation_review_checks=tax_reconciliation_review_checks,
        tax_calculation=tax_calculation,
        carry_forward_losses=carry_forward_losses,
        rd_breakdown=rd_breakdown,
        bs_checks=bs_checks,
        review_items=review_items,
        proposed_adjustments=proposed_adjustments,
        support_tables=support_tables,
        decision_traces=decision_traces,
        deterministic_review_items=deterministic_review_items,
    )
