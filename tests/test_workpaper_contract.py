from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from ai_review import (
    DecisionTrace,
    ReviewItem,
    ReviewSeverity,
    WorkpaperContractError,
    WorkpaperRequest,
    WorkpaperResult,
    WorkpaperStatus,
    read_workpaper_request,
    read_workpaper_result,
    write_workpaper_request,
    write_workpaper_result,
)


class WorkpaperContractTests(unittest.TestCase):
    def _request(self, root: Path) -> WorkpaperRequest:
        input_dir = root / "inputs"
        input_dir.mkdir()
        input_path = input_dir / "input.xlsx"
        input_path.write_bytes(b"evidence")
        return WorkpaperRequest(
            job_id="job-001",
            income_year="2026",
            work_dir=str(root),
            input_dir=str(input_dir),
            input_paths=(str(input_path),),
            output_path=str(root / "output" / "workpaper.xlsx"),
            log_dir=str(root / "logs"),
            job_options={"ato_policy_year": "2026", "requested_tables": {}},
        )

    def test_request_round_trip_and_owned_path_validation(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            request_path = root / "request.json"
            request = self._request(root)

            write_workpaper_request(request, request_path)
            loaded = read_workpaper_request(request_path)

            self.assertEqual(loaded, request)

    def test_request_rejects_path_outside_job_directory(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            request_path = root / "request.json"
            write_workpaper_request(self._request(root), request_path)
            payload = json.loads(request_path.read_text(encoding="utf-8"))
            payload["output_path"] = "/tmp/outside-job.xlsx"
            request_path.write_text(json.dumps(payload), encoding="utf-8")

            with self.assertRaisesRegex(WorkpaperContractError, "inside work_dir"):
                read_workpaper_request(request_path)

    def test_result_round_trip_preserves_trace_and_review_item(self):
        with TemporaryDirectory() as folder:
            result_path = Path(folder) / "result.json"
            trace = DecisionTrace(
                decision_id="decision-profit_and_loss-5",
                account_name="Cost of sales",
                report_type="profit_and_loss",
                source_row=5,
                income_year="2026",
                rule_pack="ITR 2026",
                itr_ref="Exp - 6A",
                itr_label="Cost of sales",
                treatment="financial_label_only",
                confidence="high",
                review_required=False,
                rule_id="itr-rule-example",
                matched_pattern=r"\bcost of sales\b",
                matched_text="cost of sales",
                source_references=("ITR 2026", "Decision source: regex"),
            )
            review_item = ReviewItem(
                review_id="review-decision-profit_and_loss-5",
                decision_id=trace.decision_id,
                severity=ReviewSeverity.MEDIUM,
                title="Review classification",
                evidence=("Rule ID: itr-rule-example",),
                required_action="Accountant to review.",
            )
            result = WorkpaperResult(
                job_id="job-001",
                income_year="2026",
                status=WorkpaperStatus.COMPLETED,
                output_path="/job/output/workpaper.xlsx",
                review_items=(review_item,),
                decision_traces=(trace,),
                metadata={"backend": "v1.main"},
            )

            write_workpaper_result(result, result_path)
            loaded = read_workpaper_result(result_path)

            self.assertEqual(loaded, result)

    def test_result_round_trip_preserves_review_sentinel_for_structural_conflict(self):
        with TemporaryDirectory() as folder:
            result_path = Path(folder) / "result.json"
            trace = DecisionTrace(
                decision_id="decision-balance_sheet-9",
                account_name="Business Bank Account",
                report_type="balance_sheet",
                source_row=9,
                income_year="2025",
                rule_pack="ITR 2025",
                itr_ref="Review",
                itr_label="Balance-sheet structural conflict — review",
                treatment="review_only",
                confidence="high",
                review_required=True,
                rule_id="system-bs-section-conflict-cash-under-liability",
                source_references=("Decision source: structural_validation",),
            )
            result = WorkpaperResult(
                job_id="job-structural-review",
                income_year="2025",
                status=WorkpaperStatus.COMPLETED,
                output_path="/job/output/workpaper.xlsx",
                decision_traces=(trace,),
                metadata={"backend": "v1.main"},
            )

            write_workpaper_result(result, result_path)
            loaded = read_workpaper_result(result_path)

            self.assertEqual(loaded.decision_traces[0].itr_ref, "Review")
            self.assertTrue(loaded.decision_traces[0].review_required)


if __name__ == "__main__":
    unittest.main()
