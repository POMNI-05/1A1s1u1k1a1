# Project workflow map

This is the operating map for the tax-workpaper application. It follows the
runtime data path, rather than the order in which features were developed.
Each linked stage has its own issue/debugging log; update the relevant stage
file whenever a fault is found, investigated, fixed, or deliberately deferred.

```text
Streamlit inputs
  -> 1. UI and request selection
  -> 2. Isolated job and request.json
  -> 3. Excel intake and safe parsing
  -> 4. Deterministic rules and decision traces
  -> 5. Workpaper/calculator output and result.json
  -> 6. Optional AI review, audit sidecar, and history
```

## Stage index

1. [UI and request selection](workflow/stage_01_ui_and_request.md)
2. [Isolated job and backend contract](workflow/stage_02_job_contract.md)
3. [Excel intake and safe parsing](workflow/stage_03_excel_intake.md)
4. [Rules, labels and decision evidence](workflow/stage_04_rules_and_decisions.md)
5. [Workpaper, calculators and output](workflow/stage_05_workpaper_output.md)
6. [AI review, audit and history](workflow/stage_06_ai_audit_history.md)
7. [Web review editor and client library](workflow/stage_07_web_review_editor.md)

The current workbook-review backlog is
[`review_backlog_20260825.md`](workflow/review_backlog_20260825.md). It maps
every reported issue to a runtime stage and separates confirmed defects from
items still requiring a reproducible evidence case.

The active calculation-workflow repair checklist is
[`calculation_workflow_todo_20260825.md`](TODO/calculation_workflow_todo_20260825.md).
It covers the logged demo reconciliation intake issue, conditional R&D and
depreciation support, and the Balance Sheet ITR presentation. It is deliberately
separate from the completed AI-review roadmap because these are deterministic
workpaper concerns.

The active web-review-editor checklist is
[`web_review_editor_todo_20260825.md`](TODO/web_review_editor_todo_20260825.md).
It covers the client library, compact generator navigation and an auditable
revision editor. A reviewer selects amendments; the application validates and
exports a new revision without overwriting the original workbook.

## How to debug safely

1. Identify the first failed stage; do not diagnose from the final workbook
   alone.
2. Preserve the source workbook and use a copy for reproduction.
3. Read the relevant stage file's *Issue/debugging log* and run its focused
   test before modifying code.
4. Prefer a structured error or review item to a fallback value.
5. Add a regression test, update that stage's issue log, then run the full
   suite: `python -m unittest discover -s tests -v`.

## Ownership boundary

Only deterministic rules and accountant-approved actions can affect a tax
outcome. AI review, UI history, metadata, and audit records are downstream
read-only support functions.
