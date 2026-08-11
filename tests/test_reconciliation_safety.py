from __future__ import annotations

import unittest

import pandas as pd

from v1.workpaper_builder import (
    _auto_reconciliation_rows_from_labelled_pl,
    _build_proposed_adjustments,
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


if __name__ == "__main__":
    unittest.main()
