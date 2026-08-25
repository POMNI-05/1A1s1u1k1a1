from __future__ import annotations

import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from frontend.workpaper_library import (
    UNASSIGNED_CLIENT,
    build_client_index,
    group_workpapers_by_client,
    infer_client_name_from_workpaper_filename,
)


class WorkpaperLibraryTests(unittest.TestCase):
    def test_groups_workpapers_by_saved_client_and_sorts_newest_first(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            older = root / "older.xlsx"
            newer = root / "newer.xlsx"
            unassigned = root / "unassigned.xlsx"
            for path in (older, newer, unassigned):
                path.touch()
            os.utime(older, (1, 1))
            os.utime(newer, (2, 2))

            metadata = {
                older: {"client_name": "Acme Pty Ltd"},
                newer: {"client_name": "Acme Pty Ltd"},
                unassigned: {},
            }
            grouped = group_workpapers_by_client(
                [older, newer, unassigned],
                metadata_loader=lambda path: metadata[path],
            )

        self.assertEqual(list(grouped), ["Acme Pty Ltd", UNASSIGNED_CLIENT])
        self.assertEqual(grouped["Acme Pty Ltd"], [newer, older])
        self.assertEqual(grouped[UNASSIGNED_CLIENT], [unassigned])

    def test_standard_filename_is_used_only_when_metadata_has_no_client_name(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            inferred = root / "test1_acme_studio_2026_layout_workpaper_20260825_152226.xlsx"
            saved = root / "test2_acme_studio_2026_layout_workpaper_20260825_152226.xlsx"
            generic = root / "workpaper_20260825_152226.xlsx"
            for path in (inferred, saved, generic):
                path.touch()

            metadata = {
                inferred: {},
                saved: {"client_name": "Acme Studio Pty Ltd"},
                generic: {},
            }
            grouped = group_workpapers_by_client(
                [inferred, saved, generic],
                metadata_loader=lambda path: metadata[path],
            )

        self.assertEqual(
            infer_client_name_from_workpaper_filename(inferred),
            "Acme Studio",
        )
        self.assertEqual(
            grouped["Acme Studio"],
            [inferred],
        )
        self.assertEqual(grouped["Acme Studio Pty Ltd"], [saved])
        self.assertEqual(grouped[UNASSIGNED_CLIENT], [generic])

    def test_client_index_records_saved_and_inferred_tag_provenance(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            saved = root / "Acme_2026_workpaper_20260825_152226.xlsx"
            inferred = root / "Beta_2026_workpaper_20260825_152226.xlsx"
            for path in (saved, inferred):
                path.touch()
            metadata = {saved: {"client_name": "Acme Pty Ltd"}, inferred: {}}

            index = build_client_index(
                [saved, inferred],
                metadata_loader=lambda path: metadata[path],
            )

        by_client = {entry["client_name"]: entry["workpapers"] for entry in index}
        self.assertEqual(by_client["Acme Pty Ltd"][0]["tag_source"], "saved_metadata")
        self.assertEqual(by_client["Beta"][0]["tag_source"], "filename_inferred")
