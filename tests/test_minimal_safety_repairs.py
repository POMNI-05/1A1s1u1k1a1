from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd
from openpyxl import Workbook

from v1.cleaner import (
    ReportInput,
    add_row_type,
    choose_current_amount_col,
    clean_report_input,
    extract_tax_depreciation_total,
)
from v1.workpaper_builder import _build_bs_checks, _extract_net_profit_by_period
from v1.write_workbook import _find_main_amount_col, _looks_like_generated_column


class MinimalSafetyRepairTests(unittest.TestCase):
    def test_requested_year_is_selected_instead_of_numeric_density(self):
        df = pd.DataFrame({"Account": ["Sales"], "2024": [10], "2025": [5]})
        with patch("v1.cleaner.SELECTED_INCOME_YEAR", "2025"):
            self.assertEqual(choose_current_amount_col(df, ["2024", "2025"]), "2025")

    def test_sales_and_other_income_with_amounts_are_accounts(self):
        df = pd.DataFrame(
            {
                "Account Label": ["Sales", "Other Income", "Income"],
                "2025": [100.0, 25.0, 0.0],
            }
        )
        result = add_row_type(df, "Account Label", ["2025"])
        self.assertEqual(result["Row Type"].tolist(), ["account", "account", "heading"])

    def test_explicit_excel_error_is_not_converted_to_zero(self):
        raw = pd.DataFrame(
            [
                ["Account", "2025"],
                ["Sales", "#REF!"],
                ["Other Income", 20],
            ]
        )
        report = ReportInput(
            report_type="profit_and_loss",
            source_path=Path("broken.xlsx"),
            sheet_name="P&L",
            raw_df=raw,
            detection_score=99,
            detection_reason="test",
        )
        with self.assertRaisesRegex(ValueError, "CELL-001"):
            clean_report_input(report)

    def test_known_side_by_side_tax_and_tb_layout_is_rejected(self):
        raw = pd.DataFrame(
            [
                ["Tax Return Disclosures", None, "Source Data from Client Trial Balance"],
                ["Account No", "Account Name", "GL Accounts"],
                ["C", "Gross Written Premiums", "Westpac Visa Account"],
            ]
        )
        report = ReportInput(
            report_type="profit_and_loss",
            source_path=Path("composite.xlsx"),
            sheet_name="ITR - INCOME",
            raw_df=raw,
            detection_score=99,
            detection_reason="test",
        )
        with self.assertRaisesRegex(ValueError, "STRUCT-003"):
            clean_report_input(report)

    def test_profit_priority_excludes_after_tax_and_falls_back_per_period(self):
        df = pd.DataFrame(
            {
                "Account Label": ["Profit Before Tax", "Net Profit After Tax", "Other Income"],
                "2025": [100.0, 80.0, 120.0],
                "2024": [0.0, 70.0, 110.0],
                "Row Type": ["total", "total", "account"],
                "Report Section": ["", "", "Income"],
            }
        )
        values, methods = _extract_net_profit_by_period(df)
        self.assertEqual(values["2025"], 100.0)
        self.assertEqual(values["2024"], 110.0)
        self.assertIn("Profit before tax", methods["2025"])
        self.assertIn("Fallback", methods["2024"])

    def test_depreciation_requires_explicit_total_and_deduction_column(self):
        raw = pd.DataFrame(
            [
                ["Tax Depreciation Schedule", None, None, None],
                ["Name", "Cost", "Depreciation", "Closing Value"],
                ["Asset A", 1000.0, 100.0, 900.0],
                ["Total", 1000.0, 100.0, 900.0],
            ]
        )
        report = ReportInput(
            report_type="tax_depreciation",
            source_path=Path("depreciation.xlsx"),
            sheet_name="Tax Depreciation",
            raw_df=raw,
            detection_score=99,
            detection_reason="test",
        )
        self.assertEqual(extract_tax_depreciation_total(report), 100.0)

    def test_missing_bs_total_is_not_tested_instead_of_zero(self):
        df = pd.DataFrame(
            {
                "Account Label": ["Total Assets", "Total Equity"],
                "2025": [100.0, 100.0],
                "Row Type": ["total", "total"],
            }
        )
        checks = _build_bs_checks(df)
        self.assertTrue(checks["Status"].str.startswith("NOT TESTED - BS-001").all())
        self.assertTrue(checks["2025"].isna().all())

    def test_account_column_is_not_removed_for_containing_total_rows(self):
        wb = Workbook()
        ws = wb.active
        ws["A1"] = "Account"
        ws["A2"] = "Sales"
        ws["A3"] = "Total Income"
        ws["B1"] = "ITR Label"
        self.assertFalse(_looks_like_generated_column(ws, 1))
        self.assertTrue(_looks_like_generated_column(ws, 2))

    def test_writer_rejects_ambiguous_numeric_columns_without_requested_year(self):
        wb = Workbook()
        ws = wb.active
        ws.append(["Account", "Current", "Prior"])
        ws.append(["Sales", 100.0, 90.0])
        with self.assertRaisesRegex(ValueError, "PERIOD-001"):
            _find_main_amount_col(ws, 1, 2, 3)


if __name__ == "__main__":
    unittest.main()
