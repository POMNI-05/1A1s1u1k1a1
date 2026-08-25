# Web review editor TODO — 25 August 2026

## Goal

Provide a two-surface Streamlit workflow: a compact workpaper generator and a
post-generation review editor. The reviewer chooses the amendments; the system
validates, records and exports them. The original generated workbook remains
unchanged.

## Stage 15A — Navigation and client library

- [x] Replace the top-level **New workpaper** / **Previous workpapers** buttons
  with a compact generator/editor switch and a left-side main-page icon.
- [x] Make the main page a client-grouped workpaper library, rather than an
  undifferentiated file list.
- [x] Keep an explicit route back to the generator and preserve session-scoped
  history isolation.
- **Exit criterion:** users can move clearly between the client library, the
  compact generator and the review/editor surface without losing a selected
  workpaper.
- **Validation:** client-grouping regression test, UI-text regressions,
  frontend compilation and full test suite passed (95 tests).

## Stage 15B — Controlled interactive revision editor

- [x] Let a reviewer choose a generated workpaper and the rows/fields to
  revise, with source and calculated columns read-only.
- [x] Validate every amendment against the selected income year and permitted
  domain values; do not infer a tax outcome.
- [x] Save an append-only revision record with old value, new value, reviewer
  note, timestamp and source workpaper identity.
- [x] Rebuild/export a new revision workbook; never overwrite the original.
- **Exit criterion:** a reviewer-controlled, validated amendment produces a
  downloadable revision and an auditable change record.

## Stage 15C — Audit, regression and release documentation

- [x] Add regression tests for client grouping, editable-field restrictions,
  invalid amendments, revision preservation and original-file immutability.
- [x] Document the editor's authority boundary in the workflow and data-handling
  notes.
- [x] Retire the legacy UI route that sent Python rule source to a free-text
  Gemini explanation request; keep only the existing strict evidence adapter.
- **Exit criterion:** the editor has deterministic validation and tests before
  client use.
- **Validation:** focused editor/library/UI tests, frontend compilation and the
  full test suite passed (100 tests).

## Stage 16 — Spreadsheet-first editor presentation

- [x] Replace the dataframe-style review grid with an Excel-like browser canvas.
- [x] Retain the established controlled-edit and audit/export boundary.
- [x] Reserve safe vertical space for Streamlit's fixed browser header.
- **Exit criterion:** reviewers see a familiar spreadsheet surface without
  sacrificing deterministic revision validation.
- **Validation:** spreadsheet-canvas and revision tests, frontend compilation
  and the full suite passed (103 tests).

## Stage 17 — Legacy workpaper client tags and clustering

- [x] Infer a conservative client tag from standard legacy workpaper filenames
  only when saved metadata has no client name.
- [x] Provide a repeatable script that previews groups, writes missing sidecar
  tags only when explicitly requested, and emits a client index.
- [x] Reuse the safe tag fallback in the client library and add regressions for
  metadata priority, filename inference and non-merging of ambiguous names.
- [x] Document the no-fuzzy-merge boundary and validate the existing downloads
  in preview mode without moving source workpapers.
- **Exit criterion:** named legacy workpapers are grouped under a client in the
  library without modifying the Excel evidence or guessing ambiguous aliases.

## Stage 18 — Full-workbook free editing

- [x] Replace the controlled review grid with a full-width workbook canvas.
- [x] Render every visible sheet with bottom tabs and make every existing cell editable.
- [x] Preserve the original workbook and export manual edits to a new workbook
  with changed-cell audit evidence.
- **Exit criterion:** users edit the generated workpaper directly in a familiar
  spreadsheet surface and download a separate revised Excel file.
- **Validation:** full test suite passed (107 tests), including a regression
  test for the inline JavaScript clipboard parser.
