# Stage 4 — Rules, labels and decision evidence

## Purpose

The `v1/itr_rules*.py` packs and `v1/labeller.py` classify accounts against
year-specific ITR references. `v1/decision_trace.py` turns those results into
machine-readable evidence and deterministic review items.

## Inputs and outputs

- Input: cleaned account rows and selected income year.
- Output: labels, rule IDs, matched patterns/text, sources, `DecisionTrace`,
  and deterministic `ReviewItem` records.

## Issue/debugging log

Current review backlog: [R-04, R-05 and R-07 to R-13, R-24](review_backlog_20260825.md#stage-4--rules-labels-and-decision-evidence).

| State | Issue | Diagnosis and safe resolution |
| --- | --- | --- |
| Resolved | A label could be explained only by having an LLM reread source code. | Retain rule ID, rule pack, matched pattern/text and source evidence with each decision. |
| Guardrail | Sensitive or uncertain matches. | Mark review-required; do not let AI or a low-confidence match determine treatment. |

## Debug procedure

1. Find the labelled row and its `DecisionTrace` by `decision_id`.
2. Verify selected rule pack/year and matched pattern before changing a rule.
3. Run `python -m unittest tests.test_decision_trace tests.test_policy_years -v`.
4. Add/update a rule with a stable rule ID and a policy-year test.
