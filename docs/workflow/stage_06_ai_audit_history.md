# Stage 6 — AI review, audit and history

## Purpose

Optional Gemini/Grok adapters review minimised deterministic evidence after the
workbook exists. The result is display-only and is stored with a local audit
sidecar; Streamlit history displays the workbook, metadata and review record.

## Inputs and outputs

- Input: completed `WorkpaperResult`, `DecisionTrace` records and an explicitly
  selected provider/API key.
- Output: schema-validated `AiReview` and `<workpaper>.ai_review_audit.json`.

## Issue/debugging log

| State | Issue | Diagnosis and safe resolution |
| --- | --- | --- |
| Resolved | Provider-specific logic could leak into business code. | Gemini and Grok implement one review interface and strict schema validation. |
| Resolved | AI findings lacked a reviewer outcome. | Audit sidecar stores provider/model, prompt/schema versions, input hash, response status and accountant disposition. |
| Guardrail | Invalid/malformed AI output. | Reject it; do not display or apply it. The workbook remains unchanged. |

## Debug procedure

1. Confirm the workpaper result is completed and has decision traces.
2. Inspect the audit sidecar, never an API key or raw workbook payload.
3. Run `python -m unittest tests.test_ai_review_contract tests.test_ai_review_providers tests.test_ai_review_audit -v`.
4. Read [AI review data handling](../ai_review_data_handling.md) before using a
   real client file with an external provider.
