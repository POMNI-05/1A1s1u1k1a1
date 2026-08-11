from __future__ import annotations

import unittest
from decimal import Decimal

from tax_calculators.registry import SUPPORTED_YEARS, get_decimal_rule, get_year_source
from tax_calculators.validation import CalculatorError, to_decimal


class RegistryAndValidationTests(unittest.TestCase):
    def test_every_supported_year_has_a_valid_source(self):
        for year in SUPPORTED_YEARS:
            with self.subTest(year=year):
                self.assertEqual(get_year_source(year)["income_year"], year)

    def test_source_results_are_defensive_copies(self):
        source = get_year_source("2025")
        source["company_tax"]["general_rate"] = "9.99"
        self.assertEqual(
            get_year_source("2025")["company_tax"]["general_rate"],
            "0.30",
        )

    def test_2026_instant_asset_threshold_is_enacted(self):
        self.assertEqual(
            get_decimal_rule("2026", "instant_asset_writeoff", "threshold"),
            Decimal("20000"),
        )

    def test_decimal_conversion_rejects_bool_and_non_finite_values(self):
        with self.assertRaises(CalculatorError):
            to_decimal(True, "amount")
        with self.assertRaises(CalculatorError):
            to_decimal("NaN", "amount")

    def test_decimal_conversion_uses_human_float_representation(self):
        self.assertEqual(to_decimal(0.1, "amount"), Decimal("0.1"))


if __name__ == "__main__":
    unittest.main()
