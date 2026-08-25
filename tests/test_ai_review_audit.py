from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from ai_review import (
    AiReviewAuditError,
    DecisionTrace,
    ReviewItem,
    ReviewSeverity,
    WorkpaperResult,
    WorkpaperStatus,
    audit_path_for_workpaper,
    build_ai_review_audit_record,
    read_ai_review_audit,
    update_accountant_disposition,
    write_ai_review_audit,
)


class AiReviewAuditTests(unittest.TestCase):
    def setUp(self) -> None:
        self.trace = DecisionTrace(
            decision_id="decision-pl-001",
            account_name="Entertainment",
            report_type="profit_and_loss",
            source_row=12,
            income_year="2026",
            rule_pack="ITR 2026",
            itr_ref="Exp - 6S",
            itr_label="All other expenses",
            treatment="review_only",
            confidence="high",
            review_required=True,
            rule_id="itr-rule-entertainment",
            matched_pattern=r"\\bentertainment\\b",
            matched_text="Entertainment",
        )
        self.result = WorkpaperResult(
            job_id="job-42",
            income_year="2026",
            status=WorkpaperStatus.COMPLETED,
            output_path="/not/sent/to/provider.xlsx",
            review_items=(
                ReviewItem(
                    review_id="review-42",
                    decision_id=self.trace.decision_id,
                    severity=ReviewSeverity.MEDIUM,
                    title="Entertainment review",
                    evidence=("Rule requires accountant review",),
                    required_action="Accountant to confirm the facts.",
                ),
            ),
            decision_traces=(self.trace,),
        )

    def test_audit_records_minimised_evidence_hash_and_disposition(self):
        record = build_ai_review_audit_record(
            workpaper_result=self.result,
            provider_name="Grok",
            model="grok-4.6",
            review_response={
                "status": "success",
                "findings": [
                    {
                        "severity": "medium",
                        "decision_id": self.trace.decision_id,
                        "evidence": ["Rule requires accountant review"],
                        "missing_facts": ["Business purpose"],
                        "recommended_review_action": "Accountant to review purpose.",
                    }
                ],
                "limitations": ["No tax treatment was determined by AI."],
            },
        )

        self.assertEqual(record["provider"], {"name": "Grok", "model": "grok-4.6"})
        self.assertEqual(record["response"]["status"], "success")
        self.assertEqual(record["accountant_disposition"]["status"], "pending")
        self.assertEqual(len(record["input_sha256"]), 64)
        self.assertNotIn("/not/sent/to/provider.xlsx", json.dumps(record))
        self.assertNotIn("API key", json.dumps(record))

    def test_accountant_can_update_disposition_without_changing_findings(self):
        with TemporaryDirectory() as folder:
            audit_path = audit_path_for_workpaper(Path(folder) / "workpaper.xlsx")
            original = build_ai_review_audit_record(
                workpaper_result=self.result,
                provider_name="Gemini",
                model="gemini-2.5-flash",
                review_response={"status": "success", "findings": [], "limitations": []},
            )
            write_ai_review_audit(original, audit_path)

            updated = update_accountant_disposition(
                audit_path,
                status="accepted",
                reviewer="AB",
                note="Reviewed supporting invoice.",
            )

            self.assertEqual(updated["accountant_disposition"]["status"], "accepted")
            self.assertEqual(updated["accountant_disposition"]["reviewer"], "AB")
            self.assertEqual(updated["response"]["findings"], [])
            self.assertIsNotNone(updated["accountant_disposition"]["updated_at"])
            self.assertEqual(read_ai_review_audit(audit_path), updated)

    def test_invalid_disposition_is_rejected(self):
        with TemporaryDirectory() as folder:
            audit_path = audit_path_for_workpaper(Path(folder) / "workpaper.xlsx")
            write_ai_review_audit(
                build_ai_review_audit_record(
                    workpaper_result=self.result,
                    provider_name="None",
                    model="",
                    review_response={"status": "skipped", "findings": [], "limitations": []},
                ),
                audit_path,
            )
            with self.assertRaisesRegex(AiReviewAuditError, "Unsupported accountant disposition"):
                update_accountant_disposition(audit_path, status="auto_posted")


if __name__ == "__main__":
    unittest.main()
