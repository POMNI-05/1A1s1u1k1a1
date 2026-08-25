from __future__ import annotations

import io
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from ai_review import WorkpaperResult, WorkpaperStatus, write_workpaper_result
from frontend import job_runner
from tax_calculators.validation import CalculatorError


class JobRunnerTests(unittest.TestCase):
    def test_backend_timeout_is_bounded_and_has_safe_default(self):
        with patch.dict(
            "os.environ",
            {"TAX_BACKEND_TIMEOUT_SECONDS": "not-a-number"},
            clear=False,
        ):
            self.assertEqual(
                job_runner._backend_timeout_seconds(),
                job_runner.DEFAULT_BACKEND_TIMEOUT_SECONDS,
            )

        with patch.dict(
            "os.environ",
            {"TAX_BACKEND_TIMEOUT_SECONDS": "1"},
            clear=False,
        ):
            self.assertEqual(
                job_runner._backend_timeout_seconds(),
                job_runner.MIN_BACKEND_TIMEOUT_SECONDS,
            )

    def test_backend_timeout_returns_error_and_cleans_job(self):
        upload = io.BytesIO(b"not needed by mocked backend")
        upload.name = "input.xlsx"

        with TemporaryDirectory() as folder:
            jobs_dir = Path(folder) / "jobs"
            with (
                patch.object(job_runner, "JOBS_DIR", jobs_dir),
                patch.object(
                    job_runner,
                    "_run_v1_main",
                    side_effect=subprocess.TimeoutExpired("v1.main", 30),
                ),
            ):
                result = job_runner.run_workpaper_job(extra_files=[upload])

        self.assertEqual(result["status"], "error")
        self.assertIn("timed out after 30 seconds", result["error_message"])
        self.assertTrue(result["job_cleaned_up"])

    def test_failed_backend_contract_preserves_safety_error_code(self):
        upload = io.BytesIO(b"not needed by mocked backend")
        upload.name = "input.xlsx"

        def failed_backend(*, result_path: Path, **_):
            write_workpaper_result(
                WorkpaperResult(
                    job_id="mock-job",
                    income_year="2026",
                    status=WorkpaperStatus.FAILED,
                    error_code="CELL-002",
                    error_message="CELL-002: unparseable monetary value: '$12O0'",
                ),
                result_path,
            )
            return subprocess.CompletedProcess([], 1, stdout="", stderr="")

        with TemporaryDirectory() as folder:
            with (
                patch.object(job_runner, "JOBS_DIR", Path(folder) / "jobs"),
                patch.object(job_runner, "_run_v1_main", side_effect=failed_backend),
            ):
                result = job_runner.run_workpaper_job(extra_files=[upload])

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error_code"], "CELL-002")
        self.assertEqual(result["selected_income_year"], "2026")
        self.assertIn("unparseable monetary value", result["error_message"])

    def test_all_supported_policy_years_are_preserved(self):
        for year in ("2024", "2025", "2026"):
            with self.subTest(year=year):
                self.assertEqual(job_runner._normalise_policy_year(year), year)

    def test_unsupported_policy_year_is_rejected(self):
        with self.assertRaisesRegex(CalculatorError, "Unsupported income year '2027'"):
            job_runner._normalise_policy_year("2027")

    def test_unsupported_year_returns_ui_guidance_data_without_starting_job(self):
        upload = io.BytesIO(b"not read")
        upload.name = "input.xlsx"

        result = job_runner.run_workpaper_job(
            extra_files=[upload],
            ato_policy_year="2027",
        )

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error_code"], "unsupported_income_year")
        self.assertEqual(result["selected_income_year"], "2027")
        self.assertEqual(result["supported_income_years"], ["2024", "2025", "2026"])
        self.assertEqual(result["job_id"], "")
        self.assertIn("Unsupported income year '2027'", result["error_message"])

    def test_output_is_scoped_to_history_owner(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "source.xlsx"
            source.write_bytes(b"test workbook bytes")

            with patch.object(job_runner, "DOWNLOADS_DIR", root / "downloads"):
                output, _ = job_runner._copy_backend_output_to_downloads(
                    source,
                    client_name="Client A",
                    history_owner_id="session-123",
                )

            self.assertEqual(output.parent.name, "session-123")
            self.assertTrue(output.exists())

    def test_job_options_require_explicit_tax_rate_category(self):
        options = job_runner._build_job_options(company_tax_rate_category="unexpected")
        self.assertEqual(options["company_tax_rate_category"], "review_required")

    def test_reviewed_depreciation_keeps_amount_separate_from_posting_approval(self):
        options = job_runner._build_job_options(
            reviewed_tax_depreciation="$12,345.67",
            tax_depreciation_approved_for_posting=True,
        )
        self.assertEqual(
            options["reviewed_tax_depreciation"],
            {"amount": "12345.67", "approved_for_posting": True},
        )

        blank = job_runner._build_job_options(
            reviewed_tax_depreciation="",
            tax_depreciation_approved_for_posting=True,
        )
        self.assertEqual(
            blank["reviewed_tax_depreciation"],
            {"amount": None, "approved_for_posting": False},
        )

    def test_base_rate_option_requires_passing_confirmed_assessment(self):
        unconfirmed = job_runner.build_base_rate_entity_assessment(
            "2026",
            aggregated_turnover="1000000",
            total_assessable_income="100000",
            base_rate_entity_passive_income="50000",
        )
        options = job_runner._build_job_options(
            ato_policy_year="2026",
            company_tax_rate_category="base_rate_entity",
            base_rate_entity_assessment=unconfirmed,
        )
        self.assertEqual(options["company_tax_rate_category"], "review_required")

        confirmed = dict(unconfirmed, reviewer_confirmed=True)
        options = job_runner._build_job_options(
            ato_policy_year="2026",
            company_tax_rate_category="base_rate_entity",
            base_rate_entity_assessment=confirmed,
        )
        self.assertEqual(options["company_tax_rate_category"], "base_rate_entity")

    def test_base_rate_boundary_and_tampered_result_are_recalculated(self):
        assessment = job_runner.build_base_rate_entity_assessment(
            "2026",
            aggregated_turnover="50000000",
            total_assessable_income="100",
            base_rate_entity_passive_income="80",
            reviewer_confirmed=True,
        )
        self.assertFalse(assessment["turnover_below_threshold"])
        self.assertTrue(assessment["passive_income_ratio_within_limit"])

        assessment["eligible_on_supplied_figures"] = True
        options = job_runner._build_job_options(
            ato_policy_year="2026",
            company_tax_rate_category="base_rate_entity",
            base_rate_entity_assessment=assessment,
        )
        self.assertEqual(options["company_tax_rate_category"], "review_required")


if __name__ == "__main__":
    unittest.main()
