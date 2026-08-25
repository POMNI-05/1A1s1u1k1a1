from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from v1.itr_metadata import ITEM_7_LABELS
from v1.ato_policy import get_policy_for_year
from v1.labeller import _get_matcher, _net_profit_mapping


class PolicyYearTests(unittest.TestCase):
    def _matcher_for(self, year: str):
        with tempfile.TemporaryDirectory() as folder:
            config_path = Path(folder) / "job_config.json"
            config_path.write_text(json.dumps({"ato_policy_year": year}), encoding="utf-8")
            with patch.dict(os.environ, {"TAX_JOB_CONFIG_PATH": str(config_path)}, clear=False):
                return _get_matcher()

    def test_all_ui_policy_years_have_a_matcher(self):
        self.assertEqual(self._matcher_for("2024").__module__, "v1.itr_rules_2024")
        self.assertEqual(self._matcher_for("2025").__module__, "v1.itr_rules")
        self.assertEqual(self._matcher_for("2026").__module__, "v1.itr_rules_2026")

    def test_2024_does_not_use_2025_build_to_rent_label(self):
        result = self._matcher_for("2024")(
            "Build to rent capital works",
            "profit_and_loss",
            "Operating expenses",
        )
        self.assertNotEqual(result.get("Recon Display Ref"), "7Y")
        self.assertEqual(result.get("Treatment"), "review_only")

    def test_franking_credit_j_is_distinct_from_removed_training_boost(self):
        self.assertTrue(ITEM_7_LABELS["7J"]["active"])
        self.assertFalse(ITEM_7_LABELS["7J_TRAINING"]["active"])

    def test_accounting_profit_and_taxable_income_labels_are_distinct(self):
        self.assertEqual(_net_profit_mapping()["ITR Ref"], "6T")
        self.assertEqual(ITEM_7_LABELS["7T"]["name"], "Taxable/net income or loss")
        self.assertEqual(ITEM_7_LABELS["7Y"]["direction"], "information_only")

    def test_instant_asset_threshold_is_versioned_for_2026(self):
        self.assertEqual(
            get_policy_for_year("2025")["small_business_thresholds"][
                "instant_asset_writeoff"
            ],
            20_000,
        )
        self.assertEqual(
            get_policy_for_year("2026")["small_business_thresholds"][
                "instant_asset_writeoff"
            ],
            20_000,
        )

    def test_2026_sensitive_rules_remain_review_only(self):
        matcher = self._matcher_for("2026")
        asset = matcher(
            "Instant asset write-off",
            "profit_and_loss",
            "Operating expenses",
        )
        psi = matcher(
            "Personal services income",
            "profit_and_loss",
            "Operating expenses",
        )

        self.assertEqual(asset["Treatment"], "review_only")
        self.assertIn("enacted", asset["Review Note"].lower())
        self.assertEqual(psi["Treatment"], "review_only")
        self.assertNotIn("PCG 2025/5", psi["Review Note"])

    def test_section_only_expense_keeps_6s_answer_but_requires_review_for_any_year(self):
        for year in ("2024", "2025", "2026"):
            with self.subTest(year=year):
                result = self._matcher_for(year)(
                    "Unexplained clearing charge",
                    "profit_and_loss",
                    "Operating expenses",
                )
                self.assertEqual(result["ITR Ref"], "Exp - 6S")
                self.assertEqual(result["ITR Label"], "All other expenses")
                self.assertEqual(result["Treatment"], "review_only")
                self.assertEqual(result["Confidence"], "low")
                self.assertEqual(result["Rule Source"], "section_fallback_review")
                self.assertIn("account-name rule matched", result["Review Note"])


if __name__ == "__main__":
    unittest.main()
