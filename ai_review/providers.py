"""Schema-constrained, shadow-only Gemini and Grok review adapters."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from .models import AiReview, DecisionTrace, WorkpaperResult, WorkpaperStatus
from .validation import AI_REVIEW_RESPONSE_SCHEMA, parse_ai_review


# Bump this whenever the substantive review instructions change.  Audit records
# store it so a reviewer can distinguish findings made under different prompts.
SHADOW_REVIEW_PROMPT_VERSION = "1.0"


class AIReviewProviderError(RuntimeError):
    """Raised when an AI provider cannot return a safe review response."""


class JsonTransport(Protocol):
    """Minimal injectable transport; keeps provider code independently testable."""

    def post_json(
        self,
        url: str,
        *,
        headers: Mapping[str, str],
        payload: Mapping[str, Any],
        timeout_seconds: float,
    ) -> Mapping[str, Any]:
        """Send JSON and return an object response."""


@dataclass(frozen=True, slots=True)
class ShadowReviewInput:
    """Minimised evidence allowed to leave the deterministic workpaper process."""

    income_year: str
    review_items: tuple[dict[str, Any], ...]
    decision_traces: tuple[dict[str, Any], ...]


def build_shadow_review_input(
    workpaper_result: WorkpaperResult,
    decision_traces: Sequence[DecisionTrace],
) -> ShadowReviewInput:
    """Create a minimised, path-free payload for a display-only AI review."""

    return ShadowReviewInput(
        income_year=workpaper_result.income_year,
        review_items=tuple(
            {
                "review_id": item.review_id,
                "decision_id": item.decision_id,
                "severity": item.severity.value,
                "title": item.title,
                "evidence": list(item.evidence),
                "required_action": item.required_action,
            }
            for item in workpaper_result.review_items
        ),
        decision_traces=tuple(
            {
                "decision_id": trace.decision_id,
                "account_name": trace.account_name,
                "report_type": trace.report_type,
                "income_year": trace.income_year,
                "rule_pack": trace.rule_pack,
                "itr_ref": trace.itr_ref,
                "itr_label": trace.itr_label,
                "treatment": trace.treatment,
                "confidence": trace.confidence,
                "review_required": trace.review_required,
                "rule_id": trace.rule_id,
                "matched_pattern": trace.matched_pattern,
                "matched_text": trace.matched_text,
                "source_references": list(trace.source_references),
                "override_id": trace.override_id,
                "override_reason": trace.override_reason,
            }
            for trace in decision_traces
        ),
    )


def build_shadow_review_prompt(review_input: ShadowReviewInput) -> str:
    """Build a constrained review prompt without paths, raw workbooks, or logs."""

    evidence = json.dumps(
        {
            "income_year": review_input.income_year,
            "deterministic_review_items": review_input.review_items,
            "decision_traces": review_input.decision_traces,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return f"""
You are a read-only reviewer for an Australian company tax workpaper.

You must not determine tax treatment, calculate tax, alter a classification,
recommend an automatic adjustment, or invent missing facts. Use only the
deterministic evidence below. Return no findings when no additional accountant
review point is justified.

Every finding must reference one supplied decision_id. Evidence must identify
the supplied fact that prompted it. Recommended actions must require accountant
review; they must not instruct the system to change a workbook or rules.

Deterministic evidence:
{evidence}
""".strip()


@dataclass(slots=True)
class _BaseStructuredReviewProvider:
    api_key: str
    transport: JsonTransport
    model: str
    timeout_seconds: float = 60.0
    provider_name: str = field(init=False, default="")

    def review(
        self,
        workpaper_result: WorkpaperResult,
        decision_traces: Sequence[DecisionTrace],
    ) -> AiReview:
        """Obtain and validate a display-only review from one provider."""

        if workpaper_result.status != WorkpaperStatus.COMPLETED:
            raise AIReviewProviderError("Only completed workpapers can be sent for AI review")
        if not self.api_key.strip():
            raise AIReviewProviderError(f"{self.provider_name} API key is required")

        decision_ids = [trace.decision_id for trace in decision_traces]
        if not decision_ids:
            raise AIReviewProviderError("No deterministic decision traces are available for review")

        prompt = build_shadow_review_prompt(
            build_shadow_review_input(workpaper_result, decision_traces)
        )
        response = self._send_prompt(prompt)
        payload = self._extract_payload(response)
        try:
            return parse_ai_review(payload, decision_ids=decision_ids)
        except Exception as exc:
            raise AIReviewProviderError(
                f"{self.provider_name} returned an invalid structured review: {exc}"
            ) from exc

    def _send_prompt(self, prompt: str) -> Mapping[str, Any]:
        raise NotImplementedError

    def _extract_payload(self, response: Mapping[str, Any]) -> Mapping[str, Any]:
        raise NotImplementedError


@dataclass(slots=True)
class GeminiShadowReviewProvider(_BaseStructuredReviewProvider):
    """Gemini adapter using JSON schema output and no provider-side tools."""

    model: str = "gemini-2.5-flash"
    provider_name: str = field(init=False, default="Gemini")

    def _send_prompt(self, prompt: str) -> Mapping[str, Any]:
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:generateContent"
        )
        payload = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseJsonSchema": AI_REVIEW_RESPONSE_SCHEMA["schema"],
            },
        }
        return self.transport.post_json(
            url,
            headers={"x-goog-api-key": self.api_key, "Content-Type": "application/json"},
            payload=payload,
            timeout_seconds=self.timeout_seconds,
        )

    def _extract_payload(self, response: Mapping[str, Any]) -> Mapping[str, Any]:
        try:
            text = response["candidates"][0]["content"]["parts"][0]["text"]
            payload = json.loads(text)
        except (IndexError, KeyError, TypeError, json.JSONDecodeError) as exc:
            raise AIReviewProviderError("Gemini response did not contain JSON text") from exc
        if not isinstance(payload, dict):
            raise AIReviewProviderError("Gemini JSON response must be an object")
        return payload


@dataclass(slots=True)
class GrokShadowReviewProvider(_BaseStructuredReviewProvider):
    """Grok adapter using the xAI Responses API in schema-constrained mode."""

    model: str = "grok-4.6"
    reasoning_effort: str = "medium"
    provider_name: str = field(init=False, default="Grok")

    def _send_prompt(self, prompt: str) -> Mapping[str, Any]:
        if self.reasoning_effort not in {"low", "medium", "high", "xhigh"}:
            raise AIReviewProviderError("Grok reasoning_effort must be low, medium, high, or xhigh")
        payload = {
            "model": self.model,
            "reasoning": {"effort": self.reasoning_effort},
            "input": [{"role": "user", "content": prompt}],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": AI_REVIEW_RESPONSE_SCHEMA["name"],
                    "schema": AI_REVIEW_RESPONSE_SCHEMA["schema"],
                    "strict": True,
                }
            },
        }
        return self.transport.post_json(
            "https://api.x.ai/v1/responses",
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            payload=payload,
            timeout_seconds=self.timeout_seconds,
        )

    def _extract_payload(self, response: Mapping[str, Any]) -> Mapping[str, Any]:
        text = response.get("output_text")
        if not isinstance(text, str):
            text = _response_output_text(response)
        if not isinstance(text, str):
            raise AIReviewProviderError("Grok response did not contain JSON text")
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise AIReviewProviderError("Grok response did not contain valid JSON") from exc
        if not isinstance(payload, dict):
            raise AIReviewProviderError("Grok JSON response must be an object")
        return payload


def _response_output_text(response: Mapping[str, Any]) -> str | None:
    output = response.get("output")
    if not isinstance(output, list):
        return None
    for item in output:
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        content = item.get("content")
        if not isinstance(content, list):
            continue
        for part in content:
            if isinstance(part, dict) and part.get("type") == "output_text":
                text = part.get("text")
                if isinstance(text, str):
                    return text
    return None
