# AI Review Integration TODO

## Non-negotiable safety boundary

AI is a read-only reviewer and explainer. It must not determine tax treatment,
change a classification, post an adjustment, alter a workbook, select a tax
rate, or resolve missing facts. A qualified accountant remains responsible for
all decisions and any approved override.

## Stage 0 — Contract and safety design

- [x] Define `WorkpaperResult`, `DecisionTrace`, `ReviewItem`, and `AiReview`
  as typed domain models.
- [x] Define the provider-neutral `AIReviewProvider.review(...)` interface.
- [x] Define a strict JSON schema for AI output and validation behaviour.
- [x] Write acceptance tests for invalid/provider-malformed AI responses.
- **Exit criterion:** a provider can only return validated, review-only data.

## Stage 1 — Fail closed at the input boundary

- [x] Reject unsupported income years rather than defaulting to 2026.
- [x] Preserve the distinction between blank, explicit zero, valid amount, and
  unparseable amount.
- [x] Emit a structured review/error item for every unparseable monetary value.
- **Exit criterion:** no uncertain input is silently converted to a valid zero
  or a different policy year.

## Stage 2 — Deterministic decision evidence

- [x] Give each ITR rule a stable `rule_id`.
- [x] Record rule pack/year, matched pattern, matched text, source reference,
  confidence, treatment, and override provenance.
- [x] Produce structured `DecisionTrace` and `ReviewItem` objects from the
  classifier.
- **Exit criterion:** the system can answer why any label was applied without
  asking an LLM to reverse-engineer Python source.

## Stage 3 — Application contracts and provider boundary

- [x] Replace the implicit backend protocol progressively with
  `WorkpaperRequest` JSON in and `WorkpaperResult` JSON out.
- [x] Add a provider-neutral `AIReviewProvider` service.
- [x] Keep the existing isolated subprocess while migrating the protocol.
- **Exit criterion:** UI, CLI, and a future API can invoke the same workpaper
  contract without knowing `job_runner` internals.

## Stage 4 — Gemini and Grok shadow review

- [x] Implement Gemini and Grok adapters behind the shared provider interface.
- [x] Require schema-validated `AiReview` responses.
- [x] Make AI output display-only; it cannot modify workbook or rule results.
- [x] Minimise and redact provider input; never send API keys or unnecessary
  source files.
- **Exit criterion:** either provider can produce the same validated review
  shape, with no ability to change tax outcomes.

## Stage 5 — Audit and release verification

- [x] Record provider/model, schema version, prompt version, timestamp, input
  hash, response status, and accountant disposition.
- [x] Add unit, contract, malformed-response, and end-to-end tests.
- [x] Document privacy, retention, consent, and operational limits.
- **Exit criterion:** every AI suggestion is traceable, reviewable, and safely
  ignorable. **Met:** `*.ai_review_audit.json` stores only display-only review
  evidence and an accountant disposition; it is never read by the tax engine.

## `AiReview` minimum response shape

```json
{
  "status": "completed",
  "findings": [
    {
      "severity": "high",
      "decision_id": "decision-pl-0042",
      "evidence": ["Matched account: ATO interest"],
      "missing_facts": ["Date the GIC/SIC was incurred"],
      "recommended_review_action": "Accountant to confirm deductibility and, if approved, post an adjustment."
    }
  ],
  "limitations": ["No tax treatment was determined by AI."]
}
```
