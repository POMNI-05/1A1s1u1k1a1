# Project Memory

This document is the durable working memory for the tax-workpaper project. It
records safety decisions, development milestones, and the communication
protocol for future work.

## Milestone reminder prompt

After completing every planned stage, send the user this information before
moving to the next stage:

```text
Stage <number/name> completed.
Outcome: <what changed in user and system terms>.
Validation: <tests/checks and their result>.
Next: <the precise next stage>.
Takeaway: <one reusable engineering or accounting-safety lesson>.
```

Also update the relevant project TODO and the active task plan. Do not describe
a stage as complete if its exit criterion or validation has not been met.

## Non-negotiable safety principles

- Raw uploaded workbooks are evidence: never overwrite or silently repair them.
- A blank, an explicit zero, a valid amount, and an unparseable amount are
  different states.
- Never substitute an unsupported policy year with a supported one.
- Deterministic rules and approved accountant actions determine tax outcomes.
- AI is display-only review/explanation. It cannot modify rules, workbooks,
  classifications, tax rates, or tax adjustments.
- Every rule-driven label must retain machine-readable decision evidence.

## Reusable engineering takeaways

- 不确定性不是 `0`、默认年份或一句 warning；它应该是系统里的明确状态。
- 隔离 subprocess 很好，但“隔离”不等于“契约清晰”；`request.json → result.json`
  才让 UI、CLI、API、AI 能共用同一后端。
- Rules 不只是用来算结果；还必须能回答“哪条规则、为什么、基于什么证据”。
- AI 的最佳位置通常是解释、发现遗漏、整理 review—not deciding regulated outcomes.
- 多模型不该让业务代码到处写 `if Gemini / if Grok`；provider adapter
  把供应商变化关在边界里。
- 测试不只是测功能；像“年份不得回退”“金额不得默认为零”这类测试，
  其实是在固定系统的安全哲学。

## Development history

### Before the current safety programme

- The project began as an Excel/Xero-export workpaper generator with the core
  pipeline under `v1/` and a Streamlit UI under `frontend/`.
- 2024, 2025, and 2026 ITR mapping support was added over successive commits.
- User-approved label overrides and Streamlit workpaper history were added.

### Safety programme in Git history

- `89d65a7` — introduced the versioned `tax_calculators/` layer with reviewed
  ATO source JSON, Decimal-based regulated calculators, and fail-closed
  calculation safeguards.
- `90c9a93` — isolated every UI job in a UUID directory, added bounded backend
  execution, session-scoped downloads, and explicit base-rate-entity gating.
- `9f883ba` — added structural Excel safety repairs, output-presentation tests,
  and clearer failures for explicit Excel errors and ambiguous report layouts.

### Current uncommitted programme: AI-review foundation

- **Stage 0 complete:** added provider-neutral `WorkpaperResult`,
  `DecisionTrace`, `ReviewItem`, `AiReview`, strict AI JSON-response validation,
  and contract tests.
- **Stage 1 complete:** unsupported years now fail closed; source monetary
  parsing distinguishes blank/valid/invalid and rejects invalid values rather
  than silently producing zero.
- **Stage 2 complete:** classification now records rule ID, selected rule pack,
  matched regex/text, decision source, and override provenance; deterministic
  `DecisionTrace` and `ReviewItem` objects are built with the workpaper.
- **Stage 3 complete:** every isolated job now uses a versioned `request.json`
  and `result.json` contract. The backend verifies owned paths before running,
  emits deterministic traces/review items in its result, and the frontend
  rejects a missing or malformed result contract.
- **Stage 4 complete:** Gemini and Grok use the same display-only review
  adapter. Provider requests contain only minimised decision evidence, have no
  tool access, and must pass strict output validation before the UI can show a
  finding. No live provider call has been made during implementation.
- **Stage 5 complete:** each generated workbook receives a local
  `*.ai_review_audit.json` sidecar recording provider/model, schema and prompt
  versions, timestamp, minimised-input SHA-256, response status/findings, and
  an accountant disposition. The UI can update only that disposition; the
  sidecar is never read by the tax engine. Privacy, consent, retention and
  operational constraints are documented in
  [`ai_review_data_handling.md`](ai_review_data_handling.md). The full test
  suite passed: 69 tests.
- **Post-release maintenance complete:** unsupported income years now return a
  structured frontend error before file persistence or backend execution. The
  Streamlit result tells the user which years are supported and directs them to
  change the Income year selector. The runtime workflow is documented in six
  per-stage files, each with an issue/debugging log. Full suite after this
  change: 70 tests.
- **Workbook review triage, 25 August 2026:** the review of
  `workpaper_20260825_101536.xlsx` is recorded as a numbered, stage-owned
  backlog. Confirmed structural fixes: Gross Profit is a structural total;
  non-direct Balance Sheet totals receive no ordinary label; a cash/bank-like
  account under liabilities becomes a deterministic review item; and the
  Balance Sheet ITR summary uses the same ITR label data as the detail. P&L
  section-only matches retain a plausible Item 6 disclosure suggestion (for
  example, `Exp - 6S`) for 2024–2026, while remaining low-confidence
  `review_only` decisions. They cannot create an automatic Item 7 adjustment.
  Full suite after these fixes: 76 tests.
- **Period-header repair, 25 August 2026:** `PERIOD-001` in a 2025 P&L was a
  false ambiguity: the writer saw the report title containing “2025” and the
  actual 2025 column header. It now finds the selected period only in the
  Account/Description header row. Genuine ambiguity still fails closed and is
  shown as a direct Streamlit recovery message. Full suite after this fix: 77
  tests.
- **Review-only result-contract repair, 25 August 2026:** a structural
  cash/bank-under-liabilities review legitimately has no ITR reference. The
  typed result contract now accepts an empty `DecisionTrace.itr_ref` for this
  narrow review-only state, so a completed workbook is not rejected at the
  frontend boundary. Full suite after this fix: 78 tests.
- **Compatibility follow-up, 25 August 2026:** structural review traces now
  use the explicit `Review` sentinel rather than an empty ITR reference. This
  is not a filing label, but it keeps the review visible and compatible with
  both older and newer frontend contract readers. Full suite: 78 tests.
- **Trace normalisation follow-up, 25 August 2026:** the actual failure family
  included several existing review-only Balance Sheet rules (GST/tax/payroll/
  provision/related-party support), not only the structural conflict. The trace
  builder now normalises every unlabelled review-only decision to `Review`
  before result serialization. Full suite: 78 tests.
- **Section-fallback calibration, 25 August 2026:** accountant feedback
  confirmed that a section-only operating expense should still show its
  proposed Item 6 answer (normally `Exp - 6S` / `All other expenses`) rather
  than a blank `Review` label. The proposal remains low-confidence and
  `review_only`, carries no reconciliation keys, and cannot create an
  automatic Item 7 tax adjustment. Focused regression suite: 18 tests.
- **Calculation-workflow repair, 25 August 2026:** re-uploaded workpapers no
  longer let generated ITR helper/summary columns contaminate source amount and
  period detection. The selected source period is used for the reconciliation
  base; ambiguity remains `PERIOD-001`. R&D is conditional rather than a
  default reconciliation form/offset, and Item 7F depreciation can only post
  from an explicit reviewed amount with accountant approval. The Balance Sheet
  now uses the same compact source-linked ITR-total pattern as P&L. Full suite:
  83 tests.
- **Reconciliation validity follow-up, 25 August 2026:** a valid accounting
  profit base can still yield a preliminary—not final—taxable-income figure
  when proposed Item 7 adjustments await accountant approval. The
  reconciliation now shows those source amounts and approval boundary directly
  on Tab 3, without posting them. Full suite: 84 tests.
- **ATO-aligned reconciliation, 25 August 2026:** Tab 3 now follows the Item
  6T → approved add-backs → subtotal → approved subtractions → Item 7T path,
  with explicit source/review evidence, selected-year loss code `L`, and
  completeness checks. Indicative company tax is now downstream in a separate
  schedule and is not calculated from a preliminary Item 7 result. Full suite:
  88 tests.
- **Single-sheet preliminary reconciliation, 25 August 2026:** accountant
  review is a control after pre-calculation, rather than a reason to suppress
  it. Tab 3 therefore includes identified pending Item 7 proposals in a
  clearly marked `7T (preliminary)` calculation, retains the proposal evidence
  and final-lodgment boundary, and carries the associated company-tax
  pre-calculation on the same tab. The separate Tax Calculation sheet is no
  longer created. Full suite: 88 tests.
- **Tab 3 presentation simplification, 25 August 2026:** empty reconciliation
  scaffolding is omitted. Approved and pending adjustments are split by whether
  they increase or reduce taxable income; pending-review rows are visibly red
  and remain in the pre-calculation only. Full suite: 89 tests.
- **ATO-led minimal Tab 3, 25 August 2026:** Tab 3 is now only the Item 6T to
  Item 7T calculation bridge. It omits generic Item 7 checklist rows, source
  extraction notes and policy notes; those reviews appear on Checks instead.
  With no triggered adjustment or confirmed tax rate, the bridge contains only
  6T and preliminary/final 7T. Full suite: 89 tests.
- **Deliberate-stop UI, 25 August 2026:** `CELL-001`, `CELL-002`, `PERIOD-001`
  and `STRUCT-003` now render as protected input states rather than generic
  pipeline errors. The UI explains the reason and source repair/re-upload path,
  while confirming that no amount was guessed or changed and no workbook was
  created. The job runner preserves the typed backend safety code even when the
  backend exits non-zero. Focused UI/safety suite: 32 tests; full suite: 93
  tests passed.
- **Xero intake and concise Tab 3, 25 August 2026:** amount detection now
  requires a genuine period/value header, excluding Xero structural/separator
  columns and `[FX]` markers before parsing. The three supplied Xero samples
  all generate successfully. Tab 3 is a compact calculation bridge: 6T,
  red-text ADD/SUBTRACT headings when applicable, their totals, and preliminary
  7T. There are no pending-review fills or company-tax rows on Tab 3; review
  evidence remains separate. Full suite: 94 tests passed.
- **Formula-led Tab 3 and binary BS routing, 25 August 2026:** the visible
  `Total ADD`, `Total SUBTRACT` and preliminary 7T cells are now Excel formulas
  with workbook recalculation enabled. Balance Sheet output labels use the
  accurate `ITR Ref` heading and a high-threshold binary `Tab 3 decision`:
  Balance Sheet evidence is `No use in Tab 3` unless an explicit Item 7
  add/subtract route exists (which current BS rules do not create). Confidence,
  reason and review evidence remain visible. The three supplied samples were
  regenerated and formula-inspected. Full suite: 94 tests passed.
- **Detected tax depreciation in preliminary 7T, 25 August 2026:** a tax-law
  depreciation schedule now supports preliminary Item 7F only when it states
  the selected income year and has a non-zero extracted deduction. The amount
  appears in Tab 3 `SUBTRACT`, is part of the formula-led preliminary 7T, and
  never duplicates an accountant-approved override. Wrong-year or zero-total
  schedules remain support evidence only. The supplied TL schedule is FY2025
  with total `0.0`, so it correctly has no FY2026 Item 7F effect. All three
  supplied samples were regenerated; full suite: 97 tests passed.
- **Workbook review layout and source order, 25 August 2026:** P&L and Balance
  Sheet no longer render the backend-only `Tab 3 decision`; decision evidence
  remains available to deterministic review controls. Review note columns are
  wider and wrapped to reduce unnecessarily tall rows. Copied source evidence
  now comes before generated output: a tax-depreciation/Fixed Assets schedule
  is always the third sheet after P&L and Balance Sheet. All supplied samples
  were regenerated and checked; full suite: 102 tests passed.
- **Legacy client workpaper clustering, 25 August 2026:** the client library
  now falls back from saved client metadata to a conservative standard-filename
  tag for older workpapers. `tools/tag_workpapers_by_client.py` previews all
  groups without writes, and can explicitly persist only missing sidecar tags
  or emit a JSON index. It never edits an Excel workbook and never fuzzy-merges
  similar customer names; aliases require human confirmation. A preview found
  45 workpapers, 10 named groups and 8 intentionally unassigned generic files.
  Full suite: 105 tests passed.

## Current roadmap

The authoritative staged checklist is
[`ai_review_integration_todo.md`](ai_review_integration_todo.md).

The runtime workflow and per-stage issue/debugging records are in
[`project_workflow.md`](project_workflow.md). Update the relevant stage file as
part of every diagnosis or fix.

The retained workpaper review from 25 August 2026 is triaged in
[`workflow/review_backlog_20260825.md`](workflow/review_backlog_20260825.md).

1. Stage 0 — contracts and strict AI schema — complete.
2. Stage 1 — fail-closed years and amounts — complete.
3. Stage 2 — deterministic decision evidence — complete.
4. Stage 3 — typed workpaper request/result boundary — complete.
5. Stage 4 — Gemini and Grok shadow-only adapters — complete.
6. Stage 5 — audit record and release verification — complete.
7. Next candidate (not started) — split `frontend/job_runner.py` into focused
   services.
8. Active next programme — [`web_review_editor_todo_20260825.md`](TODO/web_review_editor_todo_20260825.md): compact generator navigation, a client-grouped
   workpaper library, then an audited reviewer-controlled revision editor. It
   must create a new revision file and never overwrite the source workpaper.
   Stage 15A is complete: the compact navigation exposes **⌂ Main page**,
   **Generate workpaper** and **Review & edit**, and the main page groups the
   current session's workpapers by their saved client name. Focused library/UI
   tests, frontend compilation and the full suite (95 tests) passed. Stages
   15B–15C are also complete: the editor permits reviewer-selected ITR Ref,
   confidence and review-note changes only; it writes a separate revision
   workbook, copied client metadata and a sidecar audit record with old/new
   values, reviewer and reason. Source amount/formula/routing edits remain
   blocked. The legacy UI path that sent Python rule source to free-text Gemini
   has been removed; the strict minimised-evidence adapter remains. Full suite:
   100 tests.
- **Spreadsheet-first editor follow-up, 25 August 2026:** the review surface
  has been replaced with a local Streamlit custom component rather than a
  generic dataframe editor. It provides familiar spreadsheet column headers,
  row numbers, frozen Account column, scrolling, sheet selection and
  double-click editing for authorised review fields. The export/audit boundary
  remains unchanged; a Mac Chrome header-safe offset prevents the top
  navigation being obscured. Full suite: 103 tests passed.
- **Free workbook editing, 25 August 2026:** Review & edit is now an
  unrestricted, full-width browser spreadsheet for every visible sheet and
  cell, including formulas. It has bottom sheet tabs and direct editing/paste;
  a save writes a new manual-edit workbook plus cell-level audit sidecar rather
  than overwriting the source. This mode is explicitly not a deterministic
  engine rerun. A follow-up repaired the component's JavaScript clipboard
  parser: Python must preserve JavaScript `\\r`, `\\n` and `\\t` escapes rather
  than embed literal control characters, or Chrome rejects the regular
  expression before the grid can load. Full suite: 107 tests passed.
