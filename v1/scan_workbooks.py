"""Scan uploaded workbooks without running tax labelling or calculations."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

try:
    from . import cleaner
    from .cleaner import ACCOUNT_LABEL_COL
except ImportError:  # pragma: no cover - direct script compatibility
    import cleaner  # type: ignore
    from cleaner import ACCOUNT_LABEL_COL  # type: ignore


SCAN_SCHEMA_VERSION = "scan_result.v1"


@dataclass(frozen=True)
class ScanObservation:
    id: str
    review_area: str
    account: str
    amount: float | None
    report: str
    section: str
    row_type: str
    source_sheet: str
    source_file: str


@dataclass(frozen=True)
class ScanSuggestion:
    review_area: str
    suggested: bool
    confidence: str
    reason_code: str
    reason: str
    evidence_ids: list[str]
    review_required: bool = True


@dataclass(frozen=True)
class DetectedReport:
    report_type: str
    source_file: str
    sheet_name: str
    detection_score: int
    detection_reason: str
    rows: int


@dataclass(frozen=True)
class ScanResult:
    scan_id: str
    schema_version: str
    detected_reports: list[DetectedReport]
    observations: list[ScanObservation]
    suggestions: list[ScanSuggestion]
    questions: list[dict[str, Any]]
    warnings: list[str]
    source_file_hashes: dict[str, str]


TRIGGER_PATTERNS: tuple[tuple[str, str, str], ...] = (
    ("div7a", "director_loan_account", "director loan"),
    ("div7a", "director_current_account", "director current account"),
    ("div7a", "shareholder_loan_account", "shareholder loan"),
    ("div7a", "shareholder_current_account", "shareholder current account"),
    ("div7a", "loan_to_director_account", "loan to director"),
    ("div7a", "loan_to_shareholder_account", "loan to shareholder"),
    ("related_party_review", "related_party_loan_account", "related party loan"),
    ("related_party_review", "related_party_receivable_account", "related party receivable"),
    ("related_party_review", "associate_loan_account", "associate loan"),
    ("rd_tax_incentive", "rd_account", "r&d"),
    ("rd_tax_incentive", "research_account", "research"),
    ("rd_tax_incentive", "development_account", "development"),
    ("depreciation", "depreciation_account", "depreciation"),
    ("gst_reconciliation", "gst_account", "gst"),
    ("superannuation", "super_account", "superannuation"),
    ("superannuation", "super_account", "super"),
    ("fbt_entertainment", "entertainment_account", "entertainment"),
    ("carry_forward_losses", "tax_loss_account", "tax loss"),
)


SUGGESTION_REASONS = {
    "div7a": "Possible Division 7A review suggested because a director/shareholder loan-style account was detected. This is a trigger only, not a legal conclusion.",
    "related_party_review": "Related-party review suggested because a related-party or associate loan-style account was detected.",
    "rd_tax_incentive": "R&D review suggested because research, development or R&D wording was detected.",
    "depreciation": "Tax depreciation review suggested because depreciation evidence was detected.",
    "gst_reconciliation": "GST reconciliation review suggested because GST account wording was detected.",
    "superannuation": "Superannuation review suggested because super account wording was detected.",
    "fbt_entertainment": "FBT/entertainment review suggested because entertainment wording was detected.",
    "carry_forward_losses": "Tax-loss review suggested because tax-loss wording was detected. Prior-year losses still require reviewer confirmation.",
}


def _source_hashes_from_env() -> dict[str, str]:
    raw = os.getenv("TAX_SCAN_SOURCE_HASHES", "{}")
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _detect_reports(bundle: cleaner.CleanedReports) -> list[DetectedReport]:
    reports = [
        (bundle.pl_input, len(bundle.clean_pl)),
        (bundle.bs_input, len(bundle.clean_bs)),
    ]
    if bundle.tax_depreciation_report is not None:
        reports.append((bundle.tax_depreciation_report, 1))
    return [
        DetectedReport(
            report_type=report_input.report_type,
            source_file=Path(report_input.source_path).name,
            sheet_name=str(report_input.sheet_name),
            detection_score=int(report_input.detection_score),
            detection_reason=report_input.detection_reason,
            rows=row_count,
        )
        for report_input, row_count in reports
    ]


def _amount_column(df) -> str | None:
    for col in df.columns:
        if str(col).endswith(" Parse Status"):
            continue
        if col not in {ACCOUNT_LABEL_COL, "Row Type", "Report Section", "Source Row"}:
            if df[col].dtype.kind in {"i", "u", "f"}:
                return col
    return None


def _observations_for_report(df, report_input: cleaner.ReportInput) -> list[ScanObservation]:
    amount_col = _amount_column(df)
    observations: list[ScanObservation] = []
    report_label = (
        "Balance Sheet"
        if report_input.report_type == cleaner.REPORT_TYPE_BS
        else "Profit and Loss"
    )

    for _, row in df.iterrows():
        account = str(row.get(ACCOUNT_LABEL_COL, "") or "").strip()
        account_lower = account.lower()
        if not account:
            continue
        for review_area, reason_code, needle in TRIGGER_PATTERNS:
            if needle not in account_lower:
                continue
            amount = None
            if amount_col:
                raw_amount = row.get(amount_col)
                amount = None if raw_amount is None else float(raw_amount)
            observation_id = f"obs_{len(observations) + 1:04d}_{review_area}"
            observations.append(
                ScanObservation(
                    id=observation_id,
                    review_area=review_area,
                    account=account,
                    amount=amount,
                    report=report_label,
                    section=str(row.get("Report Section", "") or ""),
                    row_type=str(row.get("Row Type", "") or ""),
                    source_sheet=str(report_input.sheet_name),
                    source_file=Path(report_input.source_path).name,
                )
            )
            break
    return observations


def build_scan_result(scan_id: str) -> ScanResult:
    bundle = cleaner.load_clean_report_bundle()
    observations = (
        _observations_for_report(bundle.clean_pl, bundle.pl_input)
        + _observations_for_report(bundle.clean_bs, bundle.bs_input)
    )
    if bundle.tax_depreciation_report is not None:
        observations.append(
            ScanObservation(
                id=f"obs_{len(observations) + 1:04d}_depreciation",
                review_area="depreciation",
                account="Tax depreciation schedule",
                amount=bundle.tax_depreciation_total,
                report="Tax depreciation",
                section="Support schedule",
                row_type="support_schedule",
                source_sheet=str(bundle.tax_depreciation_report.sheet_name),
                source_file=Path(bundle.tax_depreciation_report.source_path).name,
            )
        )

    suggestions: list[ScanSuggestion] = []
    evidence_by_area: dict[str, list[str]] = {}
    for observation in observations:
        evidence_by_area.setdefault(observation.review_area, []).append(observation.id)
    for review_area, evidence_ids in sorted(evidence_by_area.items()):
        suggestions.append(
            ScanSuggestion(
                review_area=review_area,
                suggested=True,
                confidence="medium",
                reason_code=f"{review_area}_evidence_detected",
                reason=SUGGESTION_REASONS.get(
                    review_area,
                    "Review suggested because potentially relevant account wording was detected.",
                ),
                evidence_ids=evidence_ids,
            )
        )

    questions = [
        {
            "id": "prior_year_tax_losses_exist",
            "review_area": "carry_forward_losses",
            "prompt": "Does the company have reviewed prior-year tax losses available?",
            "always_ask": True,
        },
        {
            "id": "confirmed_review_areas",
            "review_area": "scope",
            "prompt": "Which suggested review areas should be included in the workpaper?",
        },
    ]

    warnings = []
    if bundle.tax_depreciation_report is not None and not bundle.tax_depreciation_matches_selected_period:
        warnings.append(
            "Tax depreciation schedule detected, but the selected-period match could not be confirmed."
        )

    return ScanResult(
        scan_id=scan_id,
        schema_version=SCAN_SCHEMA_VERSION,
        detected_reports=_detect_reports(bundle),
        observations=observations,
        suggestions=suggestions,
        questions=questions,
        warnings=warnings,
        source_file_hashes=_source_hashes_from_env(),
    )


def main() -> int:
    output_path = Path(os.environ["TAX_SCAN_RESULT_PATH"])
    scan_id = os.environ["TAX_SCAN_ID"]
    try:
        result = asdict(build_scan_result(scan_id))
        result["status"] = "success"
    except Exception as exc:
        result = {
            "status": "error",
            "scan_id": scan_id,
            "schema_version": SCAN_SCHEMA_VERSION,
            "error_message": f"{type(exc).__name__}: {exc}",
            "detected_reports": [],
            "observations": [],
            "suggestions": [],
            "questions": [],
            "warnings": [],
            "source_file_hashes": _source_hashes_from_env(),
        }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return 0 if result["status"] == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
