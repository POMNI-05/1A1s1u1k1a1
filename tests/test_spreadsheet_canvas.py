from __future__ import annotations

import unittest

from frontend.spreadsheet_canvas import merge_canvas_edits
from streamlit.testing.v1 import AppTest


class SpreadsheetCanvasTests(unittest.TestCase):
    def test_component_mount_accepts_the_edits_default_state(self):
        app = AppTest.from_string(
            """
import streamlit as st

canvas = st.components.v2.component(
    'canvas_default_state_test',
    html='<div></div>',
    js='export default function() {}',
)
canvas(
    key='canvas_test',
    default={'edits': {}},
    on_edits_change=lambda: None,
)
"""
        )
        app.run()
        self.assertFalse(app.exception)

    def test_merges_only_authorised_cell_edits(self):
        rows = [
            {
                "Excel row": 7,
                "Account": "Entertainment",
                "ITR Ref": "Exp - 6S",
                "Confidence": "low",
                "Review note": "Review purpose",
                "Tab 3 decision": "No use in Tab 3",
                "Mapping reason": "Section fallback",
            }
        ]
        merged = merge_canvas_edits(
            rows,
            {
                "7::ITR Ref": "Review",
                "7::Review note": "Invoice needed",
                "7::Account": "Do not apply",
                "7::Tab 3 decision": "Do not apply",
            },
        )

        self.assertEqual(merged[0]["ITR Ref"], "Review")
        self.assertEqual(merged[0]["Review note"], "Invoice needed")
        self.assertEqual(merged[0]["Account"], "Entertainment")
        self.assertEqual(merged[0]["Tab 3 decision"], "No use in Tab 3")
