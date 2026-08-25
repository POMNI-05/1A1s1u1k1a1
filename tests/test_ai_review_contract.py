from __future__ import annotations

import unittest

from ai_review import (
    AI_REVIEW_RESPONSE_SCHEMA,
    AiReviewPayloadError,
    ReviewSeverity,
    parse_ai_review,
)


class AiReviewContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.decision_ids = {"decision-pl-0042"}
        self.payload = {
            "status": "completed",
            "findings": [
                {
                    "severity": "high",
                    "decision_id": "decision-pl-0042",
                    "evidence": ["Matched account: ATO interest"],
                    "missing_facts": ["Date incurred"],
                    "recommended_review_action": "Accountant to confirm deductibility.",
                }
            ],
            "limitations": ["AI did not determine tax treatment."],
        }

    def test_valid_payload_becomes_immutable_typed_review(self):
        review = parse_ai_review(self.payload, decision_ids=self.decision_ids)

        self.assertEqual(review.status, "completed")
        self.assertEqual(review.findings[0].severity, ReviewSeverity.HIGH)
        self.assertEqual(review.findings[0].decision_id, "decision-pl-0042")

    def test_schema_requires_the_review_fields(self):
        required = AI_REVIEW_RESPONSE_SCHEMA["schema"]["required"]
        finding_required = AI_REVIEW_RESPONSE_SCHEMA["schema"]["properties"]["findings"]
        finding_required = finding_required["items"]["required"]

        self.assertEqual(required, ["status", "findings", "limitations"])
        self.assertIn("recommended_review_action", finding_required)

    def test_missing_required_field_is_rejected(self):
        invalid = dict(self.payload)
        invalid.pop("limitations")

        with self.assertRaisesRegex(AiReviewPayloadError, "missing"):
            parse_ai_review(invalid, decision_ids=self.decision_ids)

    def test_unknown_decision_id_is_rejected(self):
        invalid = {
            **self.payload,
            "findings": [{**self.payload["findings"][0], "decision_id": "other-job-001"}],
        }

        with self.assertRaisesRegex(AiReviewPayloadError, "does not belong"):
            parse_ai_review(invalid, decision_ids=self.decision_ids)

    def test_malformed_provider_output_is_rejected(self):
        invalid = {
            **self.payload,
            "findings": [{**self.payload["findings"][0], "evidence": []}],
        }

        with self.assertRaisesRegex(AiReviewPayloadError, "evidence must not be empty"):
            parse_ai_review(invalid, decision_ids=self.decision_ids)


if __name__ == "__main__":
    unittest.main()
