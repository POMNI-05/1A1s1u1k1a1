from __future__ import annotations

import unittest
from decimal import Decimal

from tax_calculators.reconciliation import Adjustment, calculate_reconciliation


class ReconciliationTests(unittest.TestCase):
    def test_only_approved_adjustments_are_posted(self):
        result = calculate_reconciliation(
            "1000",
            [
                Adjustment("Approved add-back", "100", "add", "approved"),
                Adjustment("Proposed add-back", "900", "add", "proposed"),
                Adjustment("Approved subtraction", "25", "subtract", "approved"),
            ],
        )
        self.assertEqual(result.taxable_income, Decimal("1075.00"))
        self.assertEqual(len(result.included_adjustments), 2)
        self.assertEqual(len(result.excluded_adjustments), 1)

    def test_signed_amounts_are_preserved(self):
        result = calculate_reconciliation(
            "1000",
            [Adjustment("Reversal", "-100", "add", "approved")],
        )
        self.assertEqual(result.approved_additions, Decimal("-100.00"))
        self.assertEqual(result.taxable_income, Decimal("900.00"))


if __name__ == "__main__":
    unittest.main()
