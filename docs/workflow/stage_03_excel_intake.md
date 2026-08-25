# Stage 3 — Excel intake and safe parsing

## Purpose

`v1/cleaner.py` detects report structure, identifies amount columns and turns
raw source cells into cleaned report data without hiding uncertainty.

## Inputs and outputs

- Input: raw Xero/accounting Excel exports.
- Output: cleaned reports with amount parse-status columns for later rules and
  workpaper generation.

## Issue/debugging log

Current review backlog: [R-01 to R-03 and R-15 to R-19](review_backlog_20260825.md#stage-3--excel-intake-and-structural-rows).

| State | Issue | Diagnosis and safe resolution |
| --- | --- | --- |
| Resolved | `INTAKE-004`: a re-uploaded generated workpaper could make the P&L reconciliation appear to have no source amount. | The old output's ITR helper/summary columns were being re-read as source amounts. Intake now ignores only columns carrying generated-workpaper markers (and a summary's companion formula column), then selects the single actual source-period column. Header scoring also no longer treats a ledger balance that happens to contain `20xx` as a date. A missing/ambiguous requested year still fails closed as `PERIOD-001`. |
| Resolved | Invalid monetary text could become `0.0`. | `$400`, commas and parentheses parse safely; blank, explicit zero and valid amount remain distinct; `$12O0`, booleans and non-finite values fail with a structured error. |
| Guardrail | Header/period detection is ambiguous. | Stop with an actionable error rather than selecting the densest numeric column. |

## Debug procedure

1. Work on a copy of the source workbook.
2. Locate the raw cell and its parse status; distinguish blank from zero.
3. Run `python -m unittest tests.test_minimal_safety_repairs -v`.
4. Add the smallest representative workbook/cell case as a regression test;
   do not add a coercion-to-zero fallback.
