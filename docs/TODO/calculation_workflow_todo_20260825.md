# Calculation workflow repair TODO — 25 August 2026

Scope: the deterministic Excel workpaper pipeline. This list responds to the
demo run where **Tax Reconciliation** did not expose usable input amounts. It
does not authorise automatic tax conclusions: every adjustment remains
evidence-backed and accountant-approved before it can post.

## Stage 1 — Reproduce the reconciliation intake fault

- [x] Reproduce the logged demo workbook's period/amount-column selection.
- [x] Identify why the selected P&L has no usable reconciliation base or
  source-period amount column.
- [x] Add a failing regression fixture that preserves blanks, zeros and
  unparseable values as distinct states.
- **Exit criterion:** the result explains the missing input rather than showing
  a misleading zero/empty reconciliation.

## Stage 2 — Repair reconciliation input and output

- [x] Select an explicit accounting-profit base from the validated source
  amount column for the requested year only.
- [x] Fail closed when no unique requested period exists; the backend result
  carries the `PERIOD-001` reason rather than producing an empty workbook.
- [x] Render source-backed values in Tax Reconciliation and validate them in a
  representative end-to-end test.
- **Exit criterion:** Tax Reconciliation either shows the detected source
  amount and evidence or returns a clear review-required state.

## Stage 3 — Conditional R&D and depreciation workflow

- [x] Remove the unconditional R&D support schedule and R&D-offset row from new
  workpapers.
- [x] Require an explicitly selected R&D schedule plus reviewed R&D facts
  before an R&D item is included or any R&D amount can post.
- [x] Provide a simple accountant input path for tax depreciation total, with
  schedule extraction remaining optional support evidence.
- [x] Keep all Item 7 postings review-gated; do not infer eligibility from
  account names, company type or AI output.
- **Exit criterion:** absent R&D/depreciation facts produce no fabricated form
  or tax adjustment, while supplied reviewed amounts can be displayed for
  accountant approval.

## Stage 4 — Balance Sheet ITR presentation

- [x] Compare the current Balance Sheet ITR summary against the P&L summary.
- [x] Replace the redundant Balance Sheet summary with the same concise,
  source-linked ITR review pattern used on Profit and Loss.
- [x] Preserve Item 8 support/check information without presenting it as a
  complete balance-sheet tax-return calculation.
- **Exit criterion:** the Balance Sheet tab has one clear labelled-detail and
  ITR-summary review surface, with check/review evidence retained.

## Stage 5 — Documentation and release checks

- [x] Update the owning workflow stage logs with diagnosis, policy boundary and
  validation.
- [x] Run focused tests and the full test suite (83 tests passed).
- **Exit criterion:** documented deterministic behaviour with regression
  coverage and no silent tax-treatment changes.

## Stage 6 — Reconciliation validity and review state

- [x] Reproduce the generated-demo reconciliation and identify every proposed
  adjustment excluded from taxable income.
- [x] Show unapproved Item 7 candidates, their source amounts and the reason
  they are excluded directly on Tax Reconciliation.
- [x] Label the resulting amount as preliminary whenever any required review
  item remains unposted; do not call it a final taxable-income result.
- [x] Add a regression test for a reviewed-but-unapproved add-back.
- **Exit criterion:** a reviewer can see why the reconciliation is preliminary,
  what amount requires approval, and that no unapproved amount changed tax.

## Stage 7 — ATO-aligned Tab 3 before scenario testing

- [x] Make Item 6 label T the explicit reconciliation base, including source
  method and a review state when the source says only “Net Profit”.
- [x] Render the ATO sequence: approved add-backs, add-back subtotal, approved
  subtractions, subtraction subtotal, then Item 7 label T.
- [x] Show loss code `L` for the selected income year when Item 7T is a loss.
- [x] Keep unapproved adjustments visible and excluded, and add a structured
  completeness checklist for evidence-dependent Item 7 matters.
- [x] Move indicative company tax out of Item 7 into a separate calculation
  schedule; do not calculate it until the reconciliation and rate are final.
- [x] Add ATO-structure scenario tests (profit, loss, pending adjustment,
  approved adjustment and missing base evidence).
- **Exit criterion:** Tab 3 is a source-traceable, approval-aware Item 7
  workpaper that does not claim a final tax result without required evidence.

## Stage 8 — Single-sheet preliminary Item 7 calculation

- [x] Include all identified Item 7 adjustments in a usable preliminary
  calculation, while retaining their review/approval evidence.
- [x] Clearly distinguish the preliminary calculation from the accountant's
  final lodged Item 7T without suppressing the pre-calculation number.
- [x] Combine the preliminary company-tax calculation with Tax Reconciliation
  on Tab 3; do not create a duplicate Tax Calculation sheet.
- [x] Add regression coverage for the $277.20 pending-add-back path and update
  the Stage 5 workflow/debugging record.
- **Exit criterion:** Tab 3 gives a traceable pre-calculation including pending
  proposals, followed by review evidence and a clearly separate final-lodgment
  boundary.

## Stage 9 — User-supplied sample-workbook validation

- [x] Generate workpapers for Easy Day Studio, Excelerate and TL Risk into the
  user-specified output directory without altering source files.
- [x] Inspect each output for period selection, Tab 3 reconciliation, output
  checks and obvious source-to-output anomalies.
- [x] Record reproducible findings and any required follow-up in the workflow
  debugging log.
- **Current-run record (25 August 2026):** all three source folders were run
  under the current 2026 rules after Xero column detection was narrowed. All
  three workpapers generated and were inspected. The direct-Xero structural
  columns no longer produce a `CELL-002` false stop; the only remaining source
  selection warnings are the separately documented duplicate Balance Sheet
  candidate for Easy Day and duplicate depreciation schedule for TL.
- **Exit criterion:** all three generated files and their review findings are
  available to the user; any anomaly is explicit rather than silently repaired.

## Stage 10 — Simplify the Tab 3 adjustment bridge

- [x] Remove empty add-back/subtraction headings, placeholders and totals.
- [x] Separate approved adjustments from pending-review adjustments, and group
  each by whether it increases or reduces preliminary taxable income.
- [x] Use an unmistakable red visual treatment for all pending-review labels
  and rows; retain source amounts, ITR references and review evidence.
- [x] Add presentation/regression tests and update the Stage 5 workflow log.
- **Exit criterion:** a reviewer can read the adjustment direction and review
  status at a glance, without empty bridge sections obscuring the calculation.

## Stage 11 — ATO-led minimal Tab 3 workflow

- [x] Confirm the selected-year ATO Item 7 sequence and identify which labels
  are relevant only when a supported fact exists.
- [x] Reduce Tab 3 to the accounting result, only triggered adjustment groups,
  preliminary/final taxable result and the tax pre-calculation.
- [x] Move non-calculation completeness prompts out of the calculation bridge
  while preserving them as review evidence elsewhere in the workbook.
- [x] Add regression coverage and update the workflow record with the official
  ATO source and the new display boundary.
- **Exit criterion:** Tab 3 is a short source-to-result calculation bridge; it
  shows no empty categories, generic filing labels or narrative checklists.

## Stage 12 — Explain deliberate safety stops in the UI

- [x] Turn `CELL-001`, `CELL-002`, `PERIOD-001` and structural stop codes into
  plain-language, deliberate-stop panels.
- [x] State that no amount has been silently changed and give a concrete source
  repair/re-upload action for each code.
- [x] Add regression coverage for the error-guidance mapping and document the
  user-facing safety boundary.
- **Exit criterion:** a user can distinguish a protected input problem from a
  software crash without reading backend logs.

## Stage 13 — Xero intake and concise Tab 3 calculation

- [x] Restrict monetary-column detection to genuine report amount columns so
  Xero structural/separator columns do not cause `CELL-002` stops.
- [x] Keep a raw-cell distinction for malformed values in a confirmed amount
  column; do not turn unknown source evidence into a calculated zero.
- [x] Reduce Tab 3 to accounting result, red-text **ADD**/**SUBTRACT** groups,
  their two totals and the preliminary answer; remove pending-review fills and
  duplicate intermediate scaffolding.
- [x] Re-run the three supplied Xero folders and inspect the resulting Tab 3
  calculations.
- **Exit criterion:** standard Xero exports generate without a structural
  `CELL-002` false stop, and Tab 3 reads as one short add/subtract calculation.

## Stage 14 — Formula-led Tab 3 and binary Balance Sheet routing

- [x] Write live Excel formulas for `Total ADD`, `Total SUBTRACT` and the Tab
  3 preliminary 7T result, while retaining the deterministic Python result as
  the generation-time control.
- [x] Show every labelled Balance Sheet account a binary `Use in Tab 3` / `No
  use in Tab 3` decision alongside its evidence.
- [x] Apply a high bar: a Balance Sheet row can be marked `Use` only with a
  direct, explicit Item 7 direction; ordinary Item 8/support/review rows stay
  `No use` and retain their available explanatory information.
- [x] Add regression coverage and inspect the three supplied Xero outputs.
- **Exit criterion:** a reviewer can edit an adjustment in Excel and see 7T
  recalculate, and can see whether each Balance Sheet line is part of Tab 3.

## Stage 15 — Detected tax-depreciation schedule in preliminary 7T

- [x] Detect whether a tax-law depreciation schedule explicitly matches the
  selected income year and has a non-zero deduction total.
- [x] Put a matching detected total into Tab 3 `SUBTRACT / 7F` as preliminary
  schedule evidence, without double-counting an accountant-approved override.
- [x] Keep a wrong-year or zero-total schedule as support only; do not use it
  in the selected-year calculation.
- [x] Add regression coverage and validate the supplied TL schedule.
- **Exit criterion:** a matching tax depreciation schedule visibly supports
  preliminary 7T, while TL's FY2025/$0 schedule cannot affect FY2026.

## Stage 16 — Workbook review layout and source-sheet order

- [x] Widen and wrap Review note output cells so explanatory text is readable
  without making other review columns disproportionate.
- [x] Remove the internal `Tab 3 decision` column from the P&L and Balance
  Sheet sheets; retain its high-threshold routing rule in backend evidence.
- [x] Place copied uploaded support data, including Fixed Assets/tax
  depreciation, before generated reconciliation, inputs and checks sheets.
- [x] Add output-order/layout regressions and validate an output containing a
  tax depreciation schedule.
- **Exit criterion:** source evidence appears first, reviewer notes are
  comfortably readable, and generated tabs remain concise.
