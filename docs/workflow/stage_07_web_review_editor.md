# Stage 7 — Web review editor and client library

## Purpose

The Streamlit review surface opens a generated workpaper as a browser
spreadsheet and exports a separate manual revision workbook. It does not re-run
or alter the tax engine.

## Inputs and outputs

- Input: a session-scoped generated workpaper and user-selected cell changes.
- Output: `<original>_manual_edit_<timestamp>.xlsx`, a matching
  `.manual_edit_audit.json` record and copied metadata that retains the client
  grouping and parent-workpaper link.

## Editing boundary

Every cell in every visible worksheet is editable, including numeric cells and
formulas. The original workbook is never overwritten: **Save a new Excel
revision** creates a new `.xlsx` and a `.manual_edit_audit.json` sidecar with
changed cell addresses and before/after values. Formula cells are preserved as
formulas and Excel is asked to recalculate when the revision opens.

This is a manual spreadsheet-editing mode, not a deterministic backend rerun.
The user is responsible for any tax or formula consequence of manual edits;
the tax engine, DecisionTrace and AI review do not treat the edited workbook as
new deterministic evidence.

## Issue/debugging log

| State | Issue | Diagnosis and safe resolution |
| --- | --- | --- |
| Resolved | Previous workpapers were a flat file list. | **⌂ Main page** now groups the current session's workpapers by their saved client name and sends a selected file to Review & edit. |
| Resolved | A reviewer could download a workbook but could not work in a familiar spreadsheet surface. | The web editor now uses a full-workbook canvas: Excel-style column headers, row numbers, scrolling, bottom sheet tabs, direct free cell editing, formula entry and tab-separated paste. It creates a new workbook and an adjacent manual-edit audit record. |
| Resolved | Tab 3 showed `BidiComponent Error: Invalid regular expression: missing /` and no workbook grid. | The inline JavaScript paste handler was embedded in a normal Python string, so Python converted JavaScript's `\\r` and `\\n` escapes into control characters. The component now emits literal JavaScript escape sequences, and a regression test prevents the malformed regular expression from returning. |
| Resolved | The compact top navigation could sit beneath Streamlit's fixed Chrome/Safari header. | The page now reserves a header-safe top offset while retaining compact body spacing. |
| Resolved | Older generated workpapers without a metadata sidecar could only appear as an unassigned flat list. | The client library now uses the saved `client_name` first and falls back only to the standard `client_workpaper_timestamp.xlsx` filename convention. `tools/tag_workpapers_by_client.py` is preview-first; `--write-tags` persists only a missing inferred sidecar tag and never changes Excel, while `--write-index PATH` produces an auditable JSON index. It deliberately does not fuzzy-merge similar names; name variants stay separate until a user supplies an explicit canonical mapping. The preview is read-only and generic filename-only workpapers remain unassigned. Full suite: 107 tests passed. |
| Guardrail | Manual editing changes an amount or formula. | It is deliberately allowed at the user's request, but is recorded as an unrestricted manual revision—not a backend recalculation or an AI/deterministic tax conclusion. Confirm the exported file in Excel before relying on it. |
| Retired from UI | The legacy free-text Gemini explanation view sent rule source to a provider. | The UI no longer exposes or calls that flow. Optional Gemini/Grok review remains the strict, minimised-evidence adapter and cannot change a workbook. |

## Debug procedure

1. Select the source workbook from **⌂ Main page** or generate a new one.
2. Open **Review & edit**, choose a worksheet from the bottom sheet tabs and
   edit cells directly.
3. Select **Save a new Excel revision**.
4. Confirm that both the new workbook and its `.manual_edit_audit.json` exist.
5. Confirm the original file's corresponding cell remains unchanged.
6. Run `python -m unittest tests.test_workbook_canvas tests.test_workpaper_library -v`.
7. Preview legacy client tags with `python tools/tag_workpapers_by_client.py`.
   This is read-only.  Use `--write-tags` only after checking the displayed
   groups; use `--write-index client_index.json` when an exportable index is
   required.  Confirm aliases manually rather than relying on fuzzy matching.
