from __future__ import annotations

import unittest
from unittest.mock import patch

import pandas as pd

from ai_review import ReviewSeverity
from v1.decision_trace import build_decision_traces, review_items_from_traces
from v1.labeller import label_report


class DecisionTraceTests(unittest.TestCase):
    def test_regex_match_contains_machine_readable_rule_evidence(self):
        report = pd.DataFrame(
            {
                "Account Label": ["Cost of sales", "Mystery expense"],
                "Row Type": ["account", "account"],
                "Report Section": ["Operating expenses", "Unexpected group"],
                "Source Row": [5, 6],
            }
        )
        with (
            patch("v1.labeller.get_policy_year", return_value="2025"),
            patch("v1.labeller.load_overrides", return_value=[]),
        ):
            labelled = label_report(report, "profit_and_loss")

        traces = build_decision_traces(
            labelled,
            report_type="profit_and_loss",
            income_year="2025",
        )

        self.assertEqual(traces[0].rule_pack, "ITR 2025")
        self.assertTrue(traces[0].rule_id.startswith("itr-rule-"))
        self.assertEqual(traces[0].matched_pattern, r"\bcost of sales\b")
        self.assertEqual(traces[0].matched_text, "cost of sales")
        self.assertEqual(traces[1].rule_id, "unmapped")
        self.assertTrue(traces[1].review_required)

    def test_review_items_are_derived_from_trace_risk_not_ai(self):
        report = pd.DataFrame(
            {
                "Account Label": ["Mystery expense"],
                "Row Type": ["account"],
                "Report Section": ["Unexpected group"],
                "Source Row": [6],
            }
        )
        with (
            patch("v1.labeller.get_policy_year", return_value="2025"),
            patch("v1.labeller.load_overrides", return_value=[]),
        ):
            labelled = label_report(report, "profit_and_loss")

        traces = build_decision_traces(
            labelled,
            report_type="profit_and_loss",
            income_year="2025",
        )
        review_items = review_items_from_traces(traces)

        self.assertEqual(len(review_items), 1)
        self.assertEqual(review_items[0].severity, ReviewSeverity.HIGH)
        self.assertEqual(review_items[0].decision_id, "decision-profit_and_loss-6")

    def test_review_only_unlabelled_row_uses_review_sentinel_in_trace(self):
        labelled = pd.DataFrame(
            {
                "Account": ["Business Bank Account"],
                "Source Row": [9],
                "Row Type": ["account"],
                "ITR Ref": [""],
                "ITR Label": ["Balance-sheet structural conflict — review"],
                "Treatment": ["review_only"],
                "Confidence": ["high"],
                "Rule ID": ["system-bs-section-conflict-cash-under-liability"],
                "Rule Source": ["structural_validation"],
            }
        )

        traces = build_decision_traces(
            labelled,
            report_type="balance_sheet",
            income_year="2025",
        )
        review_items = review_items_from_traces(traces)

        self.assertEqual(len(traces), 1)
        self.assertEqual(traces[0].itr_ref, "Review")
        self.assertTrue(traces[0].review_required)
        self.assertEqual(review_items[0].severity, ReviewSeverity.MEDIUM)


if __name__ == "__main__":
    unittest.main()
