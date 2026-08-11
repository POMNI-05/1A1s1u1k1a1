from __future__ import annotations

import io
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from openpyxl import Workbook, load_workbook

from frontend import job_runner


def _combined_workbook() -> io.BytesIO:
    workbook = Workbook()
    pl = workbook.active
    pl.title = "Profit and Loss"
    pl.append(["Profit and Loss"])
    pl.append([])
    pl.append(["Account", "30 Jun 2026"])
    pl.append(["Trading Income", None])
    pl.append(["Sales", 1000])
    pl.append(["Total Income", 1000])
    pl.append(["Operating Expenses", None])
    pl.append(["Entertainment", 100])
    pl.append(["Total Operating Expenses", 100])
    pl.append(["Net Profit", 900])

    bs = workbook.create_sheet("Balance Sheet")
    bs.append(["Balance Sheet"])
    bs.append([])
    bs.append(["Account", "30 Jun 2026"])
    bs.append(["Current Assets", None])
    bs.append(["Cash", 1000])
    bs.append(["Total Assets", 1000])
    bs.append(["Current Liabilities", None])
    bs.append(["Loan", 400])
    bs.append(["Total Liabilities", 400])
    bs.append(["Equity", None])
    bs.append(["Retained Earnings", 600])
    bs.append(["Total Equity", 600])
    bs.append(["Net Assets", 600])

    stream = io.BytesIO()
    stream.name = "combined.xlsx"
    workbook.save(stream)
    stream.seek(0)
    return stream


class EndToEndTests(unittest.TestCase):
    def test_isolated_job_generates_workbook_and_cleans_working_files(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            with (
                patch.object(job_runner, "JOBS_DIR", root / "jobs"),
                patch.object(job_runner, "DOWNLOADS_DIR", root / "downloads"),
            ):
                result = job_runner.run_workpaper_job(
                    extra_files=[_combined_workbook()],
                    client_name="Synthetic",
                    ato_policy_year="2026",
                    company_tax_rate_category="general",
                    history_owner_id="test-session",
                    requested_tables={"fbt_entertainment": True},
                )

            self.assertEqual(result["status"], "success", result.get("error_message"))
            self.assertTrue(result["job_cleaned_up"])
            self.assertFalse((root / "jobs" / result["job_id"]).exists())

            output = Path(result["output_path"])
            self.assertTrue(output.exists())
            self.assertEqual(output.parent.name, "test-session")

            workbook = load_workbook(output, data_only=True)
            self.assertIn("Tax Reconciliation", workbook.sheetnames)
            values = [cell.value for row in workbook["Tax Reconciliation"] for cell in row]
            self.assertIn("Proposed Tax Adjustments - Not Posted Unless Approved", values)
            self.assertIn("FBT / Entertainment Review", values)
            # Net profit is 900. The proposed 100 entertainment add-back is not
            # posted, so indicative tax at 30% is 270 rather than 300.
            self.assertIn(270, values)
            self.assertNotIn(300, values)


if __name__ == "__main__":
    unittest.main()
