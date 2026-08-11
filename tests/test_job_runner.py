from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from frontend import job_runner


class JobRunnerTests(unittest.TestCase):
    def test_all_supported_policy_years_are_preserved(self):
        for year in ("2024", "2025", "2026"):
            with self.subTest(year=year):
                self.assertEqual(job_runner._normalise_policy_year(year), year)

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
