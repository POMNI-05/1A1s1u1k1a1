"""Provider boundary for review-only AI integrations."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from .models import AiReview, DecisionTrace, WorkpaperResult


class AIReviewProvider(Protocol):
    """A provider that can review deterministic workpaper evidence.

    Implementations may call Gemini, Grok, or an internal model. They must not
    modify the supplied objects, write workbooks, or determine tax treatment.
    """

    provider_name: str

    def review(
        self,
        workpaper_result: WorkpaperResult,
        decision_traces: Sequence[DecisionTrace],
    ) -> AiReview:
        """Return a schema-validated, display-only review."""
