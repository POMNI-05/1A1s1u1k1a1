from __future__ import annotations

import unittest
from decimal import Decimal

from tax_calculators.depreciation import (
    assess_instant_asset_writeoff,
    calculate_decline_in_value,
)


class DepreciationTests(unittest.TestCase):
    def test_prime_cost_formula(self):
        result = calculate_decline_in_value(
            "2025",
            method="prime_cost",
            opening_value="1500",
            effective_life_years="5",
            days_held=365,
        )
        self.assertEqual(result.decline_in_value, Decimal("300.00"))
        self.assertEqual(result.closing_value, Decimal("1200.00"))

    def test_diminishing_value_and_taxable_use(self):
        result = calculate_decline_in_value(
            "2025",
            method="diminishing_value",
            opening_value="1500",
            effective_life_years="5",
            days_held=365,
            taxable_use_ratio="0.80",
        )
        self.assertEqual(result.decline_in_value, Decimal("600.00"))
        self.assertEqual(result.deductible_decline, Decimal("480.00"))

    def test_2025_instant_asset_writeoff_threshold(self):
        result = assess_instant_asset_writeoff(
            "2025",
            asset_cost="19999.99",
            aggregated_turnover="9999999.99",
            eligibility_confirmed=True,
        )
        self.assertTrue(result.eligible_on_supplied_figures)
        self.assertEqual(result.asset_cost_threshold, Decimal("20000"))

    def test_2026_instant_asset_writeoff_uses_enacted_threshold(self):
        result = assess_instant_asset_writeoff(
            "2026",
            asset_cost="19999.99",
            aggregated_turnover="9999999.99",
            eligibility_confirmed=True,
        )
        self.assertTrue(result.eligible_on_supplied_figures)
        self.assertEqual(result.asset_cost_threshold, Decimal("20000"))


if __name__ == "__main__":
    unittest.main()
