from __future__ import annotations

import json
import unittest
from collections.abc import Mapping
from typing import Any

from ai_review import (
    AIReviewProviderError,
    DecisionTrace,
    GeminiShadowReviewProvider,
    GrokShadowReviewProvider,
    ReviewItem,
    ReviewSeverity,
    WorkpaperResult,
    WorkpaperStatus,
)


class FakeTransport:
    def __init__(self, response: Mapping[str, Any]):
        self.response = response
        self.calls: list[dict[str, Any]] = []

    def post_json(
        self,
        url: str,
        *,
        headers: Mapping[str, str],
        payload: Mapping[str, Any],
        timeout_seconds: float,
    ) -> Mapping[str, Any]:
        self.calls.append(
            {
                "url": url,
                "headers": dict(headers),
                "payload": dict(payload),
                "timeout_seconds": timeout_seconds,
            }
        )
        return self.response


class AiReviewProviderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.trace = DecisionTrace(
            decision_id="decision-profit_and_loss-5",
            account_name="ATO interest",
            report_type="profit_and_loss",
            source_row=5,
            income_year="2026",
            rule_pack="ITR 2026",
            itr_ref="Exp - 6S",
            itr_label="All other expenses",
            treatment="review_only",
            confidence="high",
            review_required=True,
            rule_id="itr-rule-example",
            matched_pattern=r"\bato interest\b",
            matched_text="ato interest",
        )
        self.result = WorkpaperResult(
            job_id="job-001",
            income_year="2026",
            status=WorkpaperStatus.COMPLETED,
            review_items=(
                ReviewItem(
                    review_id="review-001",
                    decision_id=self.trace.decision_id,
                    severity=ReviewSeverity.MEDIUM,
                    title="Review classification",
                    evidence=("Rule ID: itr-rule-example",),
                    required_action="Accountant to review.",
                ),
            ),
        )
        self.review_payload = {
            "status": "completed",
            "findings": [
                {
                    "severity": "high",
                    "decision_id": self.trace.decision_id,
                    "evidence": ["The deterministic rule requires review."],
                    "missing_facts": ["Date incurred"],
                    "recommended_review_action": "Accountant to confirm deductibility.",
                }
            ],
            "limitations": ["No tax treatment was determined by AI."],
        }

    def test_gemini_uses_json_schema_and_never_sends_output_path(self):
        transport = FakeTransport(
            {
                "candidates": [
                    {"content": {"parts": [{"text": json.dumps(self.review_payload)}]}}
                ]
            }
        )
        provider = GeminiShadowReviewProvider(api_key="key", transport=transport)

        review = provider.review(self.result, [self.trace])

        self.assertEqual(review.findings[0].decision_id, self.trace.decision_id)
        call = transport.calls[0]
        self.assertIn("responseJsonSchema", call["payload"]["generationConfig"])
        self.assertNotIn("output_path", str(call["payload"]))
        self.assertNotIn("tools", call["payload"])

    def test_grok_uses_strict_schema_and_requested_reasoning_effort(self):
        transport = FakeTransport({"output_text": json.dumps(self.review_payload)})
        provider = GrokShadowReviewProvider(
            api_key="key",
            transport=transport,
            reasoning_effort="medium",
        )

        review = provider.review(self.result, [self.trace])

        self.assertEqual(review.findings[0].severity, ReviewSeverity.HIGH)
        payload = transport.calls[0]["payload"]
        self.assertEqual(payload["reasoning"]["effort"], "medium")
        self.assertTrue(payload["text"]["format"]["strict"])
        self.assertNotIn("tools", payload)

    def test_provider_rejects_unknown_decision_from_model(self):
        invalid = {
            **self.review_payload,
            "findings": [{**self.review_payload["findings"][0], "decision_id": "other-job"}],
        }
        transport = FakeTransport({"output_text": json.dumps(invalid)})
        provider = GrokShadowReviewProvider(api_key="key", transport=transport)

        with self.assertRaisesRegex(AIReviewProviderError, "invalid structured review"):
            provider.review(self.result, [self.trace])


if __name__ == "__main__":
    unittest.main()
