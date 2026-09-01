# Review backlog — workpaper 20260825_101536

Source: review observations for
`workpaper_20260825_101536.xlsx`, generated at 10:15 on 25 August 2026.
The workbook metadata records income year **2025** and source columns for 2025
and 2024. The reviewer mentioned a period mismatch; that specific mismatch is
not yet reproduced from the retained output, so it remains an evidence check,
not an assumed defect.

Statuses mean: **fixed** = regression test added; **confirmed** = observed in
the retained workbook/code; **investigate** = plausible safety concern that
needs a minimal source-workbook reproduction before changing tax logic.

## Stage 1 — UI and request selection

| ID | Status | Issue / debugging target |
| --- | --- | --- |
| R-00 | investigate | Verify the intended source/reporting period versus selected Income year. Do not classify it as a mismatch merely because a comparative 2024 column exists in a 2025 report. |

## Stage 3 — Excel intake and structural rows

| ID | Status | Issue / debugging target |
| --- | --- | --- |
| R-01 | fixed | `Gross Profit` was treated as an account and mapped to `Exp-6A`; it is now a `total` even when it has an amount. |
| R-02 | fixed | Prevent component accounts plus structural subtotal/total rows from contributing to the same ITR aggregation path. |
| R-03 | confirmed | Make the special reconciliation-base nature of Net Profit clearer in output; `6T` should not look like an ordinary ledger-account label. |
| R-15 | fixed | A cash/bank-like account under a liability section now produces a deterministic, review-only structural conflict record; the source is not silently relabelled. |
| R-16 | confirmed | GST needs sign/nature/BAS reconciliation review rather than a generic current-liability treatment. |
| R-17 | confirmed | Item 8 totals (`8G`, `8H`) should be represented as derived totals with source-account support, not ordinary account mappings. |
| R-18 | fixed | Net Assets and Total Equity are now structural/check rows, so they do not receive normal classification confidence records. |
| R-19 | investigate | Add a P&L-to-current-year-earnings/equity reconciliation check. |
| R-26 | fixed | `PERIOD-001` could mistake a report title containing the year for a second period column. The writer now selects the year only from the Account/Description header row. |
| R-27 | fixed | Every review-only trace without a filing label (including GST/tax/payroll/provision support reviews) is normalised to the explicit `Review` sentinel. This preserves the warning through all result-contract readers. |

## Stage 4 — Rules, labels and decision evidence

| ID | Status | Issue / debugging target |
| --- | --- | --- |
| R-04 | revised | A P&L section-only match retains its plausible Item 6 disclosure suggestion (for example, `Exp - 6S`), but is low-confidence `review_only`; it cannot create an automatic Item 7 adjustment. |
| R-05 | revised | Section-only low-confidence cases are mandatory accountant review. The suggested disclosure remains visible rather than being hidden behind a blank reference. |
| R-07 | investigate | Legal expense requires purpose/capital/private review before deductibility conclusions. |
| R-08 | investigate | Split ordinary bank charges from borrowing costs, interest, finance/capital-raising fees. |
| R-09 | investigate | Consulting/accounting expenses need materiality and purpose evidence. |
| R-10 | investigate | Travel needs business/private and apportionment evidence. |
| R-11 | investigate | Motor vehicle disclosure must be separated from private-use/substantiation treatment. |
| R-12 | investigate | Rent needs premises/equipment/lease/related-party context. |
| R-13 | investigate | Confirm current-year wages/salary disclosure mapping against authoritative return schema. |
| R-24 | revised (P&L) | P&L section-only evidence produces a clearly marked disclosure suggestion, not an authoritative tax conclusion. Balance-sheet section-only support remains non-filing support and is tracked separately. |

## Stage 5 — Workpaper, reconciliation and output

| ID | Status | Issue / debugging target |
| --- | --- | --- |
| R-06 | investigate | Keep accounting disclosure mapping separate from an Item 7 entertainment add-back decision. |
| R-14 | fixed | Balance Sheet detail showed `8G/8H` while its summary said “No labels detected”; summary now uses the canonical ITR label when no separate workpaper label exists. |
| R-20 | confirmed | Split the model/output fields for Item 6 disclosure, Item 7 adjustment, and Item 8 balance-sheet disclosure. |
| R-21 | investigate | Validate whether the current reconciliation has all required accounting-PBT → additions → subtractions → taxable-income layers; it must not be described as complete until fact/evidence inputs exist. |
| R-22 | confirmed | Every proposed adjustment needs rule/evidence/reviewer-decision fields; account-name keywords alone cannot create a tax conclusion. |
| R-23 | fixed (section-only) | The section-only low-confidence path now changes behaviour, not only colour: it is review-only and cannot post an automatic Item 7 adjustment, while still displaying its disclosure suggestion. Other explicit account-name rules remain a later confidence-policy review. |
| R-25 | confirmed | Treat ITR disclosure and deductibility/tax adjustment as separate questions and fields. |

## Execution order

1. Structural guardrails: R-03, R-15 to R-19.
2. Confidence and section-fallback policy: R-04, R-05, R-23, R-24.
3. Disclosure versus tax-treatment domain split: R-06 to R-13, R-20 to R-22,
   R-25.

Each implementation must update the owning stage document, add a representative
regression test, and identify the relevant accountant-review boundary.
