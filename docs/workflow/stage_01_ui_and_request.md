# Stage 1 — UI and request selection

## Purpose

Collect the source workbooks, engagement context, income year, optional
schedules, tax-rate confirmation, and optional AI-review selection in
`frontend/app.py`.

## Inputs and outputs

- Input: Streamlit fields and uploaded Excel files.
- Output: arguments to `frontend.job_runner.run_workpaper_job()` and local
  workbook metadata.

## Issue/debugging log

Current review backlog: [R-00](review_backlog_20260825.md#stage-1--ui-and-request-selection).

| State | Issue | Diagnosis and safe resolution |
| --- | --- | --- |
| Resolved | `DEPR-004`: reviewers had no direct place to supply the tax depreciation deduction. | Selecting **Tax depreciation / capital allowance table** now exposes one optional reviewed Item 7F amount and a separate accountant-approval checkbox. Blank remains blank; entering an amount alone creates review support, while posting requires the explicit approval. |
| Resolved | Unsupported year appeared as a generic pipeline error. | `job_runner` now returns `error_code=unsupported_income_year`; Streamlit shows supported years and tells the user to change **Income year**. No job starts. |
| Resolved | The top-level navigation mixed generation with an ungrouped history list. | The left-side **⌂ Main page** now opens a session-scoped client workpaper library. Workpapers are grouped by saved client name; the compact workspace actions lead to **Generate workpaper** and **Review & edit**. The legacy session states are mapped safely to the new names. |
| Guardrail | A user needs a year not shown in the selector. | Do not add it as a UI string alone. Add reviewed rule sources, tests, mappings and calculator validation first. |

## Debug procedure

1. Confirm the selected year in the left panel.
2. Check `ATO_POLICY_YEARS` in `frontend/app.py` and `SUPPORTED_YEARS` in
   `tax_calculators/registry.py` agree.
3. Run `python -m unittest tests.test_job_runner -v`.
4. If the error is a year issue, the UI must instruct the user to select a
   listed year; it must never silently choose another year.
