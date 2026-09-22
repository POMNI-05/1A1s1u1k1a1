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

## Stage 19 — Repository structure triage and focused cleanup

- [ ] Map the current frontend/backend/workpaper modules and identify files
  whose size or mixed responsibilities now make maintenance risky.
- [ ] Use existing sample data, retained job artifacts or real project scripts
  to reproduce concrete issues; do not add broad new test scaffolding.
- [ ] Apply only focused fixes or reorganisation that preserve deterministic
  tax outcomes and the original-workbook immutability boundary.
- [ ] Update the owning workflow/debugging log and validate with existing
  workflows.
- **Exit criterion:** remaining issues are either fixed or explicitly
  documented with evidence, and any cleanup reduces coupling without changing
  tax treatment.

## Stage 20 — Generator information architecture and ATO status capture

- [x] Rename the current industry-style company type prompt to business profile
  / industry so it is not confused with ATO company-return status.
- [x] Add a separate ATO company status capture area for residency, entity
  type, activity indicator, business indicators, SGE/CBC and consolidation
  status.
- [x] Keep company tax-rate determination separate and deterministic; special
  company status or rate categories such as non-profit, trustee capacity, life
  insurance and credit union must force review rather than defaulting to 30%.
- [x] Compact the ATO status UI so standard companies can use a short preset
  and detailed return-status fields appear only when needed.
- [x] Make the business profile and ATO status controls visually distinct,
  always visible, and explicit about whether each field affects review scope,
  tax-rate gating, or calculation output.
- [x] Add a typed frontend-to-backend review-schedule handshake for
  carry-forward losses, R&D and Division 7A: frontend selection activates
  backend review schedules, but no deduction, offset, deemed dividend or
  adjustment posts without reviewed facts.
- [x] Move ATO return status and company tax-rate determination immediately
  after upload, then group engagement profile and reconciliation-scope planning
  together with highlighted schedule suggestions and plain-language reasons.
- [x] Add reviewed carry-forward tax loss workflow as a question-driven,
  reviewer/manual-first flow. MVP asks every return whether prior-year tax
  losses exist and captures reviewed available losses, proposed utilisation and
  eligibility review status in a table; backend calculation/posting to Item 7R
  remains deferred until the reviewer-approved posting model is implemented.
- [x] Add reviewed Division 7A workflow as a dynamic review flow. MVP captures
  private-company status, transaction type and reviewer-controlled legal gates;
  only confirmed complying-loan branches run the deterministic MYR calculator,
  and all deemed-dividend/legal conclusions remain review-required.
- [ ] Design the next staged web flow with separate information, generation and
  review/edit surfaces before moving the result/review UI.
- **Exit criterion:** engagement profile, ATO return status and tax-rate
  determination are visibly separate, and no captured status field changes tax
  treatment without explicit reviewed rate evidence.
- **Latest validation:** frontend compile check and focused UI/job-runner
  regressions passed (14 tests, 7 subtests).
- **Schedule-handshake validation:** frontend/backend compile check and focused
  output/job/UI/Division 7A/loss tests passed (25 tests, 10 subtests).
- **Layout/suggestion validation:** frontend compile check and focused
  UI/job-runner/output regressions passed (21 tests, 10 subtests).
- **Tax-loss workflow validation:** frontend/backend compile check and focused
  job/output/reconciliation/UI regressions passed (35 tests, 10 subtests).
- **Division 7A workflow validation:** frontend/backend compile check and
  focused job/output/Div 7A calculator tests passed (27 tests, 6 subtests).

## Stage 21 — Two-stage scan, confirm and generate workflow

- [x] Add a scan-only contract that reuses the existing cleaner/discovery path
  and records source-file hashes without labelling, calculating tax or writing a
  workbook.
- [x] Replace the first generator screen with minimal upload/profile fields and
  a Scan files action.
- [x] Add a two-column Scan & confirm screen where the left side is immutable
  machine-observed evidence and the right side stores reviewer-confirmed facts.
- [x] Compile `requested_tables` from scan suggestions plus reviewer
  confirmations, while keeping a manual Add another review area control.
- [x] Verify source hashes before Stage 2 generation and then call the existing
  deterministic job runner unchanged for labelling, calculation and workbook
  writing.
- [x] Preserve the one-step generation path internally until the staged workflow
  is stable.
- **Exit criterion:** users upload minimal facts, scan evidence, confirm review
  areas/questions, and only then generate a workpaper from the existing backend.
- **Initial validation:** frontend/scan/backend syntax compile passed with
  bytecode cache redirected to `/tmp`. The system Python 3.9 environment could
  not run the dependency-backed suite, so validation was repeated with the
  available Miniconda Python 3.13 environment.
- **Layout refinement:** removed the obsolete generator right-side placeholder
  panel, made Generate workpaper a full-width staged workflow, moved the final
  generate action below the internal scan/confirm columns, and compacted
  tax-rate review warnings into status cards.
- **Release validation:** `git diff --check` passed and the complete unittest
  suite passed under Python 3.13 with all 114 tests successful.
