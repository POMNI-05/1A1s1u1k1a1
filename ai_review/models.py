"""Domain models shared by deterministic workpaper and AI-review layers."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class WorkpaperStatus(str, Enum):
    """Terminal status produced by the deterministic workpaper pipeline."""

    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class WorkpaperRequest:
    """Validated input contract for one isolated backend workpaper job."""

    job_id: str
    income_year: str
    work_dir: str
    input_dir: str
    input_paths: tuple[str, ...]
    output_path: str
    log_dir: str
    job_options: dict[str, object]


class ReviewSeverity(str, Enum):
    """Severity used by deterministic and AI-generated review items."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass(frozen=True, slots=True)
class DecisionTrace:
    """Evidence for one deterministic account-classification decision.

    `rule_id` and `matched_pattern` are optional during the transition from the
    legacy rules engine. Stage 2 makes them mandatory for rule-based decisions.
    """

    decision_id: str
    account_name: str
    report_type: str
    source_row: int | None
    income_year: str
    rule_pack: str
    itr_ref: str
    itr_label: str
    treatment: str
    confidence: str
    review_required: bool
    rule_id: str | None = None
    matched_pattern: str | None = None
    matched_text: str | None = None
    source_references: tuple[str, ...] = ()
    override_id: str | None = None
    override_reason: str | None = None


@dataclass(frozen=True, slots=True)
class ReviewItem:
    """A deterministic issue that requires accountant attention."""

    review_id: str
    decision_id: str | None
    severity: ReviewSeverity
    title: str
    evidence: tuple[str, ...]
    required_action: str


@dataclass(frozen=True, slots=True)
class WorkpaperResult:
    """Typed result emitted by the deterministic workpaper pipeline."""

    job_id: str
    income_year: str
    status: WorkpaperStatus
    output_path: str | None = None
    warnings: tuple[str, ...] = ()
    review_items: tuple[ReviewItem, ...] = ()
    decision_traces: tuple[DecisionTrace, ...] = ()
    metadata: dict[str, str] = field(default_factory=dict)
    error_code: str | None = None
    error_message: str | None = None


@dataclass(frozen=True, slots=True)
class AiReviewFinding:
    """One schema-validated suggestion from an AI review provider."""

    severity: ReviewSeverity
    decision_id: str
    evidence: tuple[str, ...]
    missing_facts: tuple[str, ...]
    recommended_review_action: str


@dataclass(frozen=True, slots=True)
class AiReview:
    """Display-only AI review; never a tax treatment or a workbook mutation."""

    status: str
    findings: tuple[AiReviewFinding, ...]
    limitations: tuple[str, ...]
