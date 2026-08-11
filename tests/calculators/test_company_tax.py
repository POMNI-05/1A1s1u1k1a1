from __future__ import annotations

import unittest
from decimal import Decimal

from tax_calculators.company_tax import assess_base_rate_entity, calculate_company_tax
from tax_calculators.validation import CalculatorError, ReviewRequiredError


class CompanyTaxTests(unittest.TestCase):
    def test_base_rate_requires_explicit_confirmation(self):
        with self.assertRaises(ReviewRequiredError):
            calculate_company_tax(
                "2025",
                taxable_income="1000",
                rate_category="base_rate_entity",
            )

    def test_company_tax_uses_selected_rate_and_offsets(self):
        result = calculate_company_tax(
            "2025",
            taxable_income="1000",
            rate_category="base_rate_entity",
            base_rate_eligibility_confirmed=True,
            non_refundable_offsets="25",
        )
        self.assertEqual(result.tax_rate, Decimal("0.25"))
        self.assertEqual(result.gross_tax, Decimal("250.00"))
        self.assertEqual(result.indicative_tax_payable, Decimal("225.00"))

    def test_base_rate_assessment_uses_strict_turnover_threshold(self):
        assessment = assess_base_rate_entity(
            "2025",
            aggregated_turnover="50000000",
            total_assessable_income="100",
            base_rate_entity_passive_income="80",
        )
        self.assertFalse(assessment.eligible_on_supplied_figures)
        self.assertFalse(assessment.turnover_below_threshold)
        self.assertTrue(assessment.passive_income_ratio_within_limit)

    def test_passive_income_cannot_exceed_assessable_income(self):
        with self.assertRaises(CalculatorError):
            assess_base_rate_entity(
                "2025",
                aggregated_turnover="1000",
                total_assessable_income="10",
                base_rate_entity_passive_income="11",
            )


if __name__ == "__main__":
    unittest.main()
