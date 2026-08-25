from __future__ import annotations

import unittest

from frontend import ui_text


class SafetyStopGuidanceTests(unittest.TestCase):
    def test_each_fail_closed_code_has_plain_language_recovery_guidance(self):
        for code in ("CELL-001", "CELL-002", "PERIOD-001", "STRUCT-003"):
            with self.subTest(code=code):
                guidance = ui_text.safety_stop_guidance(code, "2026")
                self.assertIsNotNone(guidance)
                assert guidance is not None
                self.assertIn("Stopped deliberately", guidance["title"])
                self.assertTrue(guidance["reason"])
                self.assertIn("run again", guidance["action"])

    def test_period_stop_names_selected_year_and_unknown_codes_remain_generic(self):
        guidance = ui_text.safety_stop_guidance("PERIOD-001", "2026")
        assert guidance is not None
        self.assertIn("2026", guidance["reason"])
        self.assertIsNone(ui_text.safety_stop_guidance("UNEXPECTED-999"))

    def test_safety_stop_explicitly_says_nothing_was_changed(self):
        self.assertIn("No workbook was created", ui_text.SAFETY_STOP_NO_CHANGE)
        self.assertIn("no source amount was changed", ui_text.SAFETY_STOP_NO_CHANGE)


if __name__ == "__main__":
    unittest.main()
