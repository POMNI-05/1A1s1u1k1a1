from __future__ import annotations

import unittest
from decimal import Decimal

from tax_calculators.division7a import calculate_minimum_yearly_repayment
from tax_calculators.tax_losses import calculate_tax_loss_utilisation
from tax_calculators.validation import ReviewRequiredError


class Division7AAndLossTests(unittest.TestCase):
    def test_division7a_uses_year_specific_rate_and_annuity_formula(self):
        result = calculate_minimum_yearly_repayment(
            "2025",
            opening_balance="100000",
            remaining_term_years=5,
            actual_repayments="20000",
            loan_terms_reviewed=True,
        )
        self.assertEqual(result.benchmark_interest_rate, Decimal("0.0877"))
        self.assertEqual(result.minimum_yearly_repayment, Decimal("25556.00"))
        self.assertEqual(result.repayment_shortfall, Decimal("5556.00"))

    def test_division7a_requires_reviewed_terms(self):
        with self.assertRaises(ReviewRequiredError):
            calculate_minimum_yearly_repayment(
                "2025",
                opening_balance="100000",
                remaining_term_years=5,
            )

    def test_tax_losses_fail_closed_until_eligibility_confirmed(self):
        with self.assertRaises(ReviewRequiredError):
            calculate_tax_loss_utilisation(
                "2025",
                taxable_income_before_losses="100",
                available_losses="80",
            )

    def test_tax_loss_utilisation_is_capped(self):
        result = calculate_tax_loss_utilisation(
            "2025",
            taxable_income_before_losses="100",
            available_losses="80",
            requested_utilisation="90",
            eligibility_confirmed=True,
        )
        self.assertEqual(result.losses_utilised, Decimal("80.00"))
        self.assertEqual(result.remaining_losses, Decimal("0.00"))
        self.assertEqual(result.taxable_income_after_losses, Decimal("20.00"))


if __name__ == "__main__":
    unittest.main()
