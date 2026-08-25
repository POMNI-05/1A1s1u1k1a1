"""Translate labelled report rows into auditable domain evidence."""

from __future__ import annotations

from collections.abc import Iterable

import pandas as pd

from ai_review import DecisionTrace, ReviewItem, ReviewSeverity

from .labeller import get_account_col


def build_decision_traces(
    labelled_df: pd.DataFrame,
    *,
    report_type: str,
    income_year: str,
) -> tuple[DecisionTrace, ...]:
    """Build one trace per labelled account or relevant total row."""

    if labelled_df is None or labelled_df.empty:
        return ()

    account_col = get_account_col(labelled_df)
    traces: list[DecisionTrace] = []
    for index, row in labelled_df.iterrows():
        row_type = str(row.get("Row Type", "") or "").strip().lower()
        if row_type not in {"account", "total"}:
            continue

        source_row = row.get("Source Row")
        source_row_number = None if pd.isna(source_row) else int(source_row)
        decision_suffix = source_row_number if source_row_number is not None else index + 1
        treatment = str(row.get("Treatment", "") or "").strip()
        confidence = str(row.get("Confidence", "") or "").strip()
        source_itr_ref = str(row.get("ITR Ref", "") or "").strip()
        # Review-only balance-sheet/support rows may have no filing label. The
        # trace contract uses the explicit `Review` sentinel for them: this is
        # not an ITR disclosure, but it preserves their accountant-review
        # requirement and keeps every cross-process trace schema-valid.
        if not source_itr_ref and treatment not in {"review_only", "unmapped"}:
            continue
        itr_ref = source_itr_ref or "Review"
        review_required = treatment in {"review_only", "unmapped"} or confidence in {
            "low",
            "medium",
        }
        traces.append(
            DecisionTrace(
                decision_id=f"decision-{report_type}-{decision_suffix}",
                account_name=str(row.get(account_col, "") or "").strip(),
                report_type=report_type,
                source_row=source_row_number,
                income_year=income_year,
                rule_pack=str(row.get("Rule Pack", "") or "").strip(),
                itr_ref=itr_ref,
                itr_label=str(row.get("ITR Label", "") or "").strip(),
                treatment=treatment,
                confidence=confidence,
                review_required=review_required,
                rule_id=_optional_text(row.get("Rule ID")),
                matched_pattern=_optional_text(row.get("Matched Pattern")),
                matched_text=_optional_text(row.get("Matched Text")),
                source_references=_source_references(row),
                override_id=_optional_text(row.get("Override Name")),
                override_reason=_optional_text(row.get("Override Reason")),
            )
        )
    return tuple(traces)


def review_items_from_traces(traces: Iterable[DecisionTrace]) -> tuple[ReviewItem, ...]:
    """Produce deterministic review items from trace risk indicators."""

    items: list[ReviewItem] = []
    for trace in traces:
        if not trace.review_required:
            continue
        severity = ReviewSeverity.HIGH if trace.treatment == "unmapped" else ReviewSeverity.MEDIUM
        evidence = [f"ITR reference: {trace.itr_ref or 'not mapped'}"]
        if trace.rule_id:
            evidence.append(f"Rule ID: {trace.rule_id}")
        if trace.matched_pattern:
            evidence.append(f"Matched pattern: {trace.matched_pattern}")
        items.append(
            ReviewItem(
                review_id=f"review-{trace.decision_id}",
                decision_id=trace.decision_id,
                severity=severity,
                title=f"Review classification: {trace.account_name}",
                evidence=tuple(evidence),
                required_action="Accountant to confirm classification and supporting evidence.",
            )
        )
    return tuple(items)


def _optional_text(value: object) -> str | None:
    if pd.isna(value):
        return None
    text = str(value or "").strip()
    return text or None


def _source_references(row: pd.Series) -> tuple[str, ...]:
    references: list[str] = []
    rule_pack = _optional_text(row.get("Rule Pack"))
    if rule_pack:
        references.append(rule_pack)
    source = _optional_text(row.get("Rule Source"))
    if source:
        references.append(f"Decision source: {source}")
    return tuple(references)
