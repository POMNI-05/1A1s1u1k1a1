# AI review data handling

## Purpose and boundary

Gemini and Grok are optional, **display-only** reviewers. They may identify a
missing fact or describe a point for accountant review. They do not determine a
tax treatment, modify an ITR label, create an adjustment, change the workbook,
or select a tax rate.

The deterministic workpaper pipeline is completed before an AI call. A failure
to call a provider, a provider timeout, or an invalid provider response leaves
the workbook unchanged.

## Data sent to a provider

When the user explicitly selects an AI provider and supplies an API key, the
application sends only the structured `DecisionTrace` and deterministic
`ReviewItem` evidence required for the shadow review. This can include account
names, ITR references, matched rule evidence, and review actions.

The application does **not** send the raw Excel workbook, source-file paths,
generated workbook path, backend logs, reviewer notes, client profile,
Streamlit session data, or API key as review evidence. Provider requests have
no tools or write capability.

The retired free-text explanation route that supplied Python rule source is not
available in the UI. Rule explanations must be grounded in stored,
machine-readable `DecisionTrace` evidence rather than asking a model to infer
an outcome from application source code.

Account names and factual evidence can still be confidential client data.
Treat this as an external disclosure: obtain the firm/client approval required
by your engagement terms and professional obligations before enabling it.

## Retention and audit trail

For every generated workbook, the application writes a local sidecar named
`<workpaper>.ai_review_audit.json`. It records the selected provider/model,
review-schema and prompt versions, timestamp, SHA-256 hash of the minimised
input, response status and findings, plus an accountant disposition. It does
not retain a duplicate provider prompt, raw workbook, API key, or backend log.

The sidecar stays beside the session-scoped download until the practice removes
the output. The current application has no automatic long-term retention or
deletion policy; the operating practice must set one. Delete or retain the
workbook, metadata sidecar, and AI-review audit sidecar together according to
the engagement file/records policy. Do not treat a local sidecar as an
immutable legal archive; use the firm's approved document-management controls
when that is required.

## Provider and operational controls

- Keep AI disabled by default; enable it only for an approved review.
- Store production keys in approved secret storage, never workbooks, metadata,
  logs, source control, or the audit sidecar.
- Review the selected provider's current data processing, retention, residency,
  access-control, and enterprise terms before production use. These settings
  are account and contract specific.
- The provider adapters request strict JSON output, then validate it locally.
  Unknown decision IDs, malformed responses, and unsupported fields are
  rejected rather than shown as findings.
- The accountant must record a disposition and independently decide any action.
  An accepted finding is still not an automatic adjustment or lodgment decision.
