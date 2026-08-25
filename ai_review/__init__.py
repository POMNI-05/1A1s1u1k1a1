"""Provider-neutral, review-only AI contracts for tax workpapers."""

from .models import (
    AiReview,
    AiReviewFinding,
    DecisionTrace,
    ReviewItem,
    ReviewSeverity,
    WorkpaperRequest,
    WorkpaperResult,
    WorkpaperStatus,
)
from .provider import AIReviewProvider
from .audit import (
    ACCOUNTANT_DISPOSITION_STATUSES,
    AI_REVIEW_AUDIT_SCHEMA_VERSION,
    AiReviewAuditError,
    audit_path_for_workpaper,
    build_ai_review_audit_record,
    read_ai_review_audit,
    shadow_review_input_sha256,
    update_accountant_disposition,
    write_ai_review_audit,
)
from .providers import (
    AIReviewProviderError,
    GeminiShadowReviewProvider,
    GrokShadowReviewProvider,
    SHADOW_REVIEW_PROMPT_VERSION,
    ShadowReviewInput,
    build_shadow_review_input,
)
from .workpaper_contract import (
    WORKPAPER_CONTRACT_VERSION,
    WorkpaperContractError,
    read_workpaper_request,
    read_workpaper_result,
    write_workpaper_request,
    write_workpaper_result,
)
from .validation import AI_REVIEW_RESPONSE_SCHEMA, AiReviewPayloadError, parse_ai_review

__all__ = [
    "AI_REVIEW_RESPONSE_SCHEMA",
    "AI_REVIEW_AUDIT_SCHEMA_VERSION",
    "AIReviewProvider",
    "AIReviewProviderError",
    "ACCOUNTANT_DISPOSITION_STATUSES",
    "AiReviewAuditError",
    "AiReview",
    "AiReviewFinding",
    "AiReviewPayloadError",
    "DecisionTrace",
    "GeminiShadowReviewProvider",
    "GrokShadowReviewProvider",
    "ReviewItem",
    "ReviewSeverity",
    "ShadowReviewInput",
    "SHADOW_REVIEW_PROMPT_VERSION",
    "WORKPAPER_CONTRACT_VERSION",
    "WorkpaperContractError",
    "WorkpaperRequest",
    "WorkpaperResult",
    "WorkpaperStatus",
    "parse_ai_review",
    "build_shadow_review_input",
    "audit_path_for_workpaper",
    "build_ai_review_audit_record",
    "read_ai_review_audit",
    "shadow_review_input_sha256",
    "update_accountant_disposition",
    "write_ai_review_audit",
    "read_workpaper_request",
    "read_workpaper_result",
    "write_workpaper_request",
    "write_workpaper_result",
]
