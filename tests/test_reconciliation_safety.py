from __future__ import annotations

import unittest
from unittest.mock import patch

import pandas as pd

from v1.workpaper_builder import (
    _auto_reconciliation_rows_from_labelled_pl,
    _build_proposed_adjustments,
    _build_tax_reconciliation,
    _build_tax_reconciliation_review_checks,
    _tax_depreciation_reconciliation_rows,
    _unapproved_reconciliation_rows_from_labelled_pl,
)


class ReconciliationSafetyTests(unittest.TestCase):
    def _labelled_row(self, **updates):
        row = {
            "Account Label": "Entertainment",
            "Row Type": "account",
            "2026": 120.0,
            "ITR Ref": "Exp - 6S",
            "Recon ITR Ref": "7W",
            "Recon Display Ref": "7W",
            "Recon Direction": "add",
            "Treatment": "review_only",
            "Confidence": "medium",
            "Review Note": "Confirm deductibility and FBT treatment.",
            "Auto Post": "",
        }
        row.update(updates)
        return pd.DataFrame([row])

    def test_review_only_rule_is_proposed_but_not_posted(self):
        labelled = self._labelled_row()

        add_rows, subtract_rows, add_totals, subtract_totals = (
            _auto_reconciliation_rows_from_labelled_pl(labelled, ["2026"])
        )
        proposals = _build_proposed_adjustments(labelled, ["2026"])

        self.assertEqual(add_rows, [])
        self.assertEqual(subtract_rows, [])
        self.assertEqual(add_totals["2026"], 0.0)
        self.assertEqual(subtract_totals["2026"], 0.0)
        self.assertEqual(proposals.loc[0, "Approval Status"], "Review required - not posted")

    def test_explicit_approval_posts_and_preserves_negative_sign(self):
        labelled = self._labelled_row(**{"2026": -35.0, "Auto Post": "Approved"})

        add_rows, _, add_totals, _ = _auto_reconciliation_rows_from_labelled_pl(
            labelled,
            ["2026"],
        )

        self.assertEqual(add_rows[0]["2026"], -35.0)
        self.assertEqual(add_totals["2026"], -35.0)

    def test_information_only_build_to_rent_label_never_posts(self):
        labelled = self._labelled_row(
            **{
                "Account Label": "Build to rent capital works",
                "Recon ITR Ref": "7Y",
                "Recon Display Ref": "7Y",
                "Recon Direction": "information_only",
                "Auto Post": "Approved",
            }
        )

        add_rows, subtract_rows, add_totals, subtract_totals = (
            _auto_reconciliation_rows_from_labelled_pl(labelled, ["2026"])
        )

        self.assertEqual(add_rows, [])
        self.assertEqual(subtract_rows, [])
        self.assertEqual(add_totals["2026"], 0.0)
        self.assertEqual(subtract_totals["2026"], 0.0)

    def test_rd_offset_is_absent_without_a_reviewed_rd_claim(self):
        clean_pl = pd.DataFrame(
            {
                "Account Label": ["Net Profit"],
                "2026": [100.0],
                "Row Type": ["total"],
                "Report Section": [""],
            }
        )
        reconciliation = _build_tax_reconciliation(clean_pl, pd.DataFrame())

        self.assertNotIn("R&D offset", reconciliation["Description"].tolist())
        self.assertNotIn("No add-back entries identified", reconciliation["Description"].tolist())
        self.assertNotIn("No subtraction entries identified", reconciliation["Description"].tolist())
        self.assertEqual(
            reconciliation["Description"].tolist(),
            [
                "Accounting profit/(loss) — Item 6T",
                "Preliminary taxable income/(loss) — review required",
            ],
        )

    def test_depreciation_number_posts_only_after_explicit_approval(self):
        not_posted, _ = _tax_depreciation_reconciliation_rows(
            ["2026"],
            reviewed_tax_depreciation_total=125.0,
            approved_for_posting=False,
        )
        posted, totals = _tax_depreciation_reconciliation_rows(
            ["2026"],
            reviewed_tax_depreciation_total=125.0,
            approved_for_posting=True,
        )

        self.assertEqual(not_posted, [])
        self.assertEqual(posted[0]["ITR Ref"], "7F")
        self.assertEqual(posted[0]["2026"], 125.0)
        self.assertEqual(totals["2026"], 125.0)

    def test_matching_tax_law_depreciation_schedule_is_preliminary_7f_subtraction(self):
        clean_pl = pd.DataFrame(
            {
                "Account Label": ["Profit Before Tax"],
                "2026": [100.0],
                "Row Type": ["total"],
                "Report Section": [""],
            }
        )

        reconciliation = _build_tax_reconciliation(
            clean_pl,
            pd.DataFrame(),
            tax_depreciation_total=25.0,
            tax_depreciation_source="tax-depreciation.xlsx :: Schedule",
            tax_depreciation_matches_selected_period=True,
        )

        self.assertIn("SUBTRACT", reconciliation["Description"].tolist())
        schedule_row = reconciliation[
            reconciliation["Description"].eq("Tax depreciation / decline in value")
        ].iloc[0]
        self.assertEqual(schedule_row["ITR Ref"], "7F")
        self.assertEqual(schedule_row["2026"], 25.0)
        self.assertEqual(
            reconciliation[reconciliation["Description"].eq("Total SUBTRACT")].iloc[0]["2026"],
            25.0,
        )
        result = reconciliation[reconciliation["ITR Ref"].eq("7T (preliminary)")].iloc[0]
        self.assertEqual(result["2026"], 75.0)

    def test_wrong_year_or_zero_tax_depreciation_schedule_is_not_used(self):
        clean_pl = pd.DataFrame(
            {
                "Account Label": ["Profit Before Tax"],
                "2026": [100.0],
                "Row Type": ["total"],
                "Report Section": [""],
            }
        )

        reconciliation = _build_tax_reconciliation(
            clean_pl,
            pd.DataFrame(),
            tax_depreciation_total=25.0,
            tax_depreciation_matches_selected_period=False,
        )

        self.assertNotIn("SUBTRACT", reconciliation["Description"].tolist())
        self.assertEqual(
            reconciliation[reconciliation["ITR Ref"].eq("7T")].iloc[0]["2026"],
            100.0,
        )

    def test_unapproved_add_back_is_visible_and_included_in_preliminary_income(self):
        labelled = self._labelled_row(**{"2026": 277.20})
        clean_pl = pd.DataFrame(
            {
                "Account Label": ["Net Profit"],
                "2026": [-8134.45],
                "Row Type": ["total"],
                "Report Section": [""],
            }
        )

        candidates = _unapproved_reconciliation_rows_from_labelled_pl(labelled, ["2026"])
        reconciliation = _build_tax_reconciliation(clean_pl, labelled)

        self.assertEqual(candidates[0]["2026"], 277.20)
        self.assertEqual(candidates[0]["Description"], "Entertainment")
        self.assertIn("approval required", candidates[0]["Review note"])
        self.assertIn("ADD", reconciliation["Description"].tolist())
        total_add = reconciliation[reconciliation["Description"].eq("Total ADD")].iloc[0]
        self.assertEqual(total_add["2026"], 277.20)
        taxable_row = reconciliation[
            reconciliation["Description"].eq("Preliminary taxable income/(loss) — Item 7T")
        ].iloc[0]
        self.assertEqual(taxable_row["2026"], -7857.25)
        self.assertEqual(taxable_row["ITR Ref"], "7T (preliminary)")

    def test_pending_adjustments_are_grouped_by_direction(self):
        add_back = self._labelled_row(**{"2026": 20.0})
        deduction = self._labelled_row(**{
            "Account Label": "Tax depreciation",
            "2026": 25.0,
            "Recon ITR Ref": "7F",
            "Recon Display Ref": "7F",
            "Recon Direction": "subtract",
        })
        clean_pl = pd.DataFrame({
            "Account Label": ["Net Profit"],
            "2026": [100.0],
            "Row Type": ["total"],
            "Report Section": [""],
        })

        reconciliation = _build_tax_reconciliation(
            clean_pl,
            pd.concat([add_back, deduction], ignore_index=True),
        )

        self.assertIn("ADD", reconciliation["Description"].tolist())
        self.assertIn("SUBTRACT", reconciliation["Description"].tolist())
        self.assertEqual(
            reconciliation[reconciliation["Description"].eq("Total ADD")].iloc[0]["2026"],
            20.0,
        )
        self.assertEqual(
            reconciliation[reconciliation["Description"].eq("Total SUBTRACT")].iloc[0]["2026"],
            25.0,
        )
        preliminary = reconciliation[
            reconciliation["ITR Ref"].eq("7T (preliminary)")
        ].iloc[0]
        self.assertEqual(preliminary["2026"], 95.0)

    def test_explicit_profit_before_tax_can_produce_item_7t_and_loss_code(self):
        clean_pl = pd.DataFrame(
            {
                "Account Label": ["Profit Before Tax"],
                "2026": [-50.0],
                "Row Type": ["total"],
                "Report Section": [""],
            }
        )

        reconciliation = _build_tax_reconciliation(clean_pl, pd.DataFrame())
        result_row = reconciliation[reconciliation["ITR Ref"].eq("7T")].iloc[0]

        self.assertEqual(
            result_row["Description"],
            "Taxable/net income or loss — Item 7T",
        )
        self.assertEqual(result_row["Tax return code"], "L")
        self.assertNotIn("No add-back entries identified", reconciliation["Description"].tolist())

    def test_approved_adjustment_posts_to_final_item_7t(self):
        clean_pl = pd.DataFrame(
            {
                "Account Label": ["Profit Before Tax"],
                "2026": [100.0],
                "Row Type": ["total"],
                "Report Section": [""],
            }
        )
        labelled = self._labelled_row(**{"2026": 20.0, "Auto Post": "Approved"})

        reconciliation = _build_tax_reconciliation(clean_pl, labelled)
        result_row = reconciliation[reconciliation["ITR Ref"].eq("7T")].iloc[0]

        self.assertEqual(result_row["Description"], "Taxable/net income or loss — Item 7T")
        self.assertEqual(result_row["2026"], 120.0)

    def test_company_tax_precalculation_is_not_shown_on_minimal_tab_3(self):
        clean_pl = pd.DataFrame(
            {
                "Account Label": ["Profit Before Tax"],
                "2026": [100.0],
                "Row Type": ["total"],
                "Report Section": [""],
            }
        )
        reconciliation = _build_tax_reconciliation(clean_pl, pd.DataFrame())

        with (
            patch("v1.workpaper_builder.TAX_RATE", 0.30),
            patch("v1.workpaper_builder.COMPANY_TAX_RATE_CATEGORY", "general"),
        ):
            reconciliation = _build_tax_reconciliation(clean_pl, pd.DataFrame())

        self.assertNotIn(
            "Indicative company tax before offsets — rate 30%",
            reconciliation["Description"].tolist(),
        )

    def test_plain_net_profit_keeps_item_7t_preliminary_until_base_is_confirmed(self):
        clean_pl = pd.DataFrame(
            {
                "Account Label": ["Net Profit"],
                "2026": [100.0],
                "Row Type": ["total"],
                "Report Section": [""],
            }
        )

        reconciliation = _build_tax_reconciliation(clean_pl, pd.DataFrame())
        review_checks = _build_tax_reconciliation_review_checks(
            clean_pl,
            pd.DataFrame(),
        )

        self.assertNotIn(
            "Item 6T base: confirm Net Profit excludes income tax expense",
            reconciliation["Description"].tolist(),
        )
        self.assertIn(
            "Item 6T base: confirm Net Profit excludes income tax expense",
            review_checks["Check"].tolist(),
        )
        self.assertEqual(
            reconciliation[reconciliation["ITR Ref"].eq("7T (preliminary)")].iloc[0]["Description"],
            "Preliminary taxable income/(loss) — review required",
        )


if __name__ == "__main__":
    unittest.main()
