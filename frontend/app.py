# frontend/app.py
"""
ICGTAX Tax Workpaper Generator — Streamlit UI.

Run from project root:
    streamlit run frontend/app.py

Design:
- One upload box only -> user can upload one combined workbook or multiple Excel files.
- Frontend does not decide which file is P&L or Balance Sheet.
- job_runner copies files into v1/data/.
- v1/main.py runs exactly like the working backend test.
- User/custom ITR overrides are stored in v1/user_itr_overrides.json.
- Previous generated workpapers can be reviewed/downloaded from frontend/downloads/.
- Each generated workpaper gets a sidecar metadata JSON file containing user inputs.
- Gemini can explain ITR labels by reading itr_rules.py / itr_rules_2026.py.
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

import streamlit as st


# ── Path setup ────────────────────────────────────────────────────────────────
FRONTEND_DIR = Path(__file__).resolve().parent
ROOT_DIR = FRONTEND_DIR.parent
V1_DIR = ROOT_DIR / "v1"
DOWNLOADS_DIR = FRONTEND_DIR / "downloads"

if str(FRONTEND_DIR) not in sys.path:
    sys.path.insert(0, str(FRONTEND_DIR))

import ui_text as T
from job_runner import build_base_rate_entity_assessment, run_workpaper_job
from override_editor import (
    append_override,
    build_override_from_form,
    load_override_doc,
)


# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────
ATO_POLICY_YEARS = ["2026", "2025", "2024"]

OPTIONAL_TABLES = {
    "carry_forward_losses": "Carry-forward tax loss table",
    "rd_tax_incentive": "R&D tax incentive table",
    "div7a": "Division 7A / shareholder loan table",
    "fbt_entertainment": "FBT / entertainment review table",
    "depreciation": "Tax depreciation / capital allowance table",
    "superannuation": "Superannuation timing table",
    "gst_reconciliation": "GST / BAS reconciliation table",
    "related_party_loans": "Related party loan table",
    "psi": "Personal services income review table",
}

AI_PROVIDER_OPTIONS = ["None", "Gemini"]

AI_MODEL_OPTIONS = {
    "Gemini": [
        "gemini-2.5-flash",
        "gemini-2.5-pro",
        "gemini-1.5-flash",
    ],
}

RULE_CONTEXT_MAX_CHARS = 45_000


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────
def _list_previous_workpapers(history_owner_id: str) -> list[Path]:
    """Return workpapers owned by the current Streamlit session."""
    owner_dir = DOWNLOADS_DIR / history_owner_id
    if not owner_dir.exists():
        return []

    files = [
        path
        for path in owner_dir.glob("*.xlsx")
        if path.is_file() and not path.name.startswith("~$")
    ]

    return sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)


def _format_history_file(path: Path) -> str:
    try:
        when = datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        return f"{path.name} — {when}"
    except Exception:
        return path.name


def _download_workbook_button(
    *,
    path: Path,
    label: str,
    file_name: str | None = None,
    key: str | None = None,
) -> None:
    with path.open("rb") as f:
        st.download_button(
            label=label,
            data=f.read(),
            file_name=file_name or path.name,
            mime=T.DOWNLOAD_MIME,
            use_container_width=True,
            key=key,
        )


def _metadata_path_for_workpaper(workbook_path: Path) -> Path:
    """Return sidecar metadata path for a workbook.

    Example:
        frontend/downloads/ABC_output.xlsx
        frontend/downloads/ABC_output.metadata.json
    """
    return workbook_path.with_suffix(".metadata.json")


def _load_history_metadata(workbook_path: Path | str | None) -> dict[str, Any]:
    if not workbook_path:
        return {}

    path = Path(workbook_path)
    metadata_path = _metadata_path_for_workpaper(path)

    if not metadata_path.exists():
        return {}

    try:
        with metadata_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return {}

    return data if isinstance(data, dict) else {}


def _save_history_metadata(
    *,
    result: dict[str, Any],
    client_name: str,
    company_type: str,
    company_profile_notes: str,
    company_profile: str,
    reviewer_notes: str,
    document_description: str,
    ato_policy_year: str,
    uploaded_files: list[Any],
    ai_provider: str,
    ai_model: str,
    run_ai_face_check: bool,
    company_tax_rate_category: str,
    base_rate_entity_assessment: dict[str, Any],
    requested_tables: dict[str, bool],
) -> None:
    """Save user inputs beside the generated workbook for history review."""

    if result.get("status") == "error":
        return

    output_path_raw = result.get("output_path")
    if not output_path_raw:
        return

    output_path = Path(output_path_raw)
    if not output_path.exists():
        return

    uploaded_file_names = []
    for uploaded_file in uploaded_files or []:
        name = getattr(uploaded_file, "name", None)
        if name:
            uploaded_file_names.append(name)

    metadata = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "output_name": result.get("output_name", output_path.name),
        "output_path": str(output_path),
        "client_name": client_name,
        "company_type": company_type,
        "company_profile_notes": company_profile_notes,
        "company_profile": company_profile,
        "reviewer_notes": reviewer_notes,
        "document_description": document_description,
        "ato_policy_year": ato_policy_year,
        "uploaded_files": uploaded_file_names,
        "ai_provider": ai_provider,
        "ai_model": ai_model,
        "run_ai_face_check": bool(run_ai_face_check),
        "company_tax_rate_category": company_tax_rate_category,
        "base_rate_entity_assessment": base_rate_entity_assessment,
        "requested_tables": requested_tables,
        "detected": result.get("detected", {}),
        "warnings": result.get("warnings", []),
    }

    metadata_path = _metadata_path_for_workpaper(output_path)
    metadata_path.parent.mkdir(parents=True, exist_ok=True)

    with metadata_path.open("w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)


def _safe_read_text(path: Path, max_chars: int = RULE_CONTEXT_MAX_CHARS) -> str:
    if not path.exists():
        return f"[Missing file: {path}]"

    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        return f"[Could not read {path}: {exc}]"

    if len(text) > max_chars:
        return text[:max_chars] + "\n\n[TRUNCATED: file was longer than context limit.]"

    return text


def _read_itr_rule_context(policy_year: str) -> str:
    """Read the relevant ITR rules source code for Gemini explanation."""

    year = str(policy_year or "2026").strip()

    base_rules = V1_DIR / "itr_rules.py"
    year_rules = V1_DIR / f"itr_rules_{year}.py"

    parts = [
        "===== v1/itr_rules.py =====",
        _safe_read_text(base_rules),
    ]

    if year != "2025":
        parts.extend(
            [
                f"===== v1/itr_rules_{year}.py =====",
                _safe_read_text(year_rules),
            ]
        )

    return "\n\n".join(parts)


def _call_gemini_for_label_explanation(
    *,
    question: str,
    result: dict[str, Any],
    metadata: dict[str, Any],
    policy_year: str,
    api_key: str,
    model: str,
) -> str:
    """Ask Gemini to explain a label using local itr_rules source text.

    Uses the public Gemini REST endpoint via urllib, so no extra SDK is required.
    """

    api_key = str(api_key or "").strip()
    model = str(model or "gemini-2.5-flash").strip()

    if not api_key:
        raise ValueError("Missing Gemini API key.")

    rule_context = _read_itr_rule_context(policy_year)

    prompt = f"""
You are assisting an Australian company tax workpaper reviewer.

Task:
Explain why the system labelled one or more account entries in the generated workpaper.

Use ONLY the information below:
1. User question
2. User-provided reviewer instructions / special facts
3. User-provided description of the uploaded files
4. The ITR rules source code
5. Workpaper metadata

Do not invent ATO rules. If the rule code is unclear, say that accountant review is needed.
When useful, mention the exact rule keywords or label logic that likely caused the mapping.
Keep the explanation practical and concise.

User question:
{question}

Reviewer instructions / special facts:
{metadata.get("reviewer_notes", "")}

What are these files / document description:
{metadata.get("document_description", "")}

Client/company profile:
{metadata.get("company_profile", "")}

ATO / ITR policy year:
{policy_year}

Generated output:
{result.get("output_name", metadata.get("output_name", ""))}

Uploaded files:
{metadata.get("uploaded_files", [])}

Detected report types:
{result.get("detected", metadata.get("detected", {}))}

Warnings:
{result.get("warnings", metadata.get("warnings", []))}

ITR rules source code:
{rule_context}
""".strip()

    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent?key={api_key}"
    )

    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": prompt}],
            }
        ],
        "generationConfig": {
            "temperature": 0.2,
            "topP": 0.8,
            "maxOutputTokens": 1200,
        },
    }

    request = urllib.request.Request(
        url=url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            response_data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Gemini HTTP error {exc.code}: {body}") from exc
    except Exception as exc:
        raise RuntimeError(f"Gemini request failed: {exc}") from exc

    candidates = response_data.get("candidates", [])
    if not candidates:
        raise RuntimeError(f"Gemini returned no candidates: {response_data}")

    parts = candidates[0].get("content", {}).get("parts", [])
    texts = [part.get("text", "") for part in parts if part.get("text")]

    if not texts:
        raise RuntimeError(f"Gemini returned no text: {response_data}")

    return "\n\n".join(texts).strip()


def _fallback_revision_explanation(question: str) -> str:
    q = question.lower()

    explanations: list[tuple[list[str], str]] = [
        (
            ["depreciation", "amortis", "7w", "add back"],
            "**Why is depreciation / amortisation added back (7W)?**\n\n"
            "Accounting depreciation is not usually deductible as-is for tax. "
            "The workpaper adds it back for review/tax treatment, then tax depreciation "
            "should be claimed separately where applicable.\n\n"
            "*Check the tax depreciation schedule before finalising.*",
        ),
        (
            ["cogs", "cost of goods", "cost of sales", "6a"],
            "**Why is Cost of Goods Sold / Cost of Sales under 6A?**\n\n"
            "Cost of sales normally maps to the company tax return cost-of-sales label. "
            "This covers direct costs connected to trading revenue.\n\n"
            "*If the account is not a direct cost of sales, flag it for review.*",
        ),
        (
            ["superannuation", "super", "7x", "prior year"],
            "**Why can superannuation need review?**\n\n"
            "Superannuation deductibility depends on payment timing. Accrued but unpaid super "
            "can need adjustment, while prior-year accrued super paid this year can be deductible.\n\n"
            "*Check actual payment records and opening/closing accruals.*",
        ),
        (
            ["r&d", "research", "7d", "offset", "43.5"],
            "**Why is R&D expenditure added back at 7D?**\n\n"
            "Eligible R&D expenditure is generally removed from ordinary deductions and dealt "
            "with through the R&D Tax Incentive calculation. The add-back prevents double-counting.\n\n"
            "*Confirm R&D eligibility and amounts with the R&D schedule/adviser.*",
        ),
        (
            ["entertainment", "meal", "7w", "non-deductible"],
            "**Why is entertainment flagged for review?**\n\n"
            "Entertainment expenses can be non-deductible or subject to FBT depending on the facts. "
            "The exact nature of the expense should be reviewed before finalising treatment.\n\n"
            "*Confirm whether it is entertainment, staff meal, travel meal, or client function.*",
        ),
        (
            ["6c", "consulting", "revenue", "income"],
            "**Why is consulting/service revenue mapped this way?**\n\n"
            "For many service companies, ordinary business income maps to the main income label. "
            "The exact label depends on the nature of income and withholding status.\n\n"
            "*Check whether any income is subject to withholding or should be separately disclosed.*",
        ),
        (
            ["provision", "annual leave", "long service"],
            "**Why are leave provisions flagged for review?**\n\n"
            "Accounting leave provisions may not equal deductible tax amounts. Tax treatment often "
            "depends on whether leave has actually been paid or merely accrued.\n\n"
            "*Confirm opening and closing provision balances from the Balance Sheet.*",
        ),
    ]

    for keywords, explanation in explanations:
        if any(keyword in q for keyword in keywords):
            return explanation

    return (
        "**Question received.**\n\n"
        f"> *{question.strip()}*\n\n"
        "No Gemini explanation was available for this run. For a full rule-based explanation, "
        "select Gemini in AI API input and enter a Gemini API key. The fallback answer checks only "
        "basic built-in keywords.\n\n"
        "For manual review, check:\n"
        "- the **Review note** column in the workpaper\n"
        "- the **ITR Ref** side labels\n"
        "- `v1/itr_rules.py` / `v1/itr_rules_2026.py`"
    )


def _handle_revision_question(
    *,
    question: str,
    result: dict[str, Any],
    metadata: dict[str, Any],
    policy_year: str,
    ai_provider: str,
    ai_model: str,
    api_key: str,
) -> str:
    """Answer reviewer questions.

    If Gemini is configured, use Gemini with itr_rules source context.
    Otherwise use the lightweight local fallback.
    """

    if ai_provider == "Gemini" and api_key:
        try:
            answer = _call_gemini_for_label_explanation(
                question=question,
                result=result,
                metadata=metadata,
                policy_year=policy_year,
                api_key=api_key,
                model=ai_model or "gemini-2.5-flash",
            )
            return f"**Gemini rule explanation**\n\n{answer}"
        except Exception as exc:
            fallback = _fallback_revision_explanation(question)
            return (
                "**Gemini explanation failed, so fallback explanation was used.**\n\n"
                f"`{exc}`\n\n"
                f"{fallback}"
            )

    return _fallback_revision_explanation(question)


def _render_metadata_block(metadata: dict[str, Any]) -> None:
    """Show stored user inputs for current/history workpaper."""

    if not metadata:
        st.info("No saved metadata found for this workpaper.")
        return

    st.markdown("**Saved user inputs**")

    st.markdown("**Reviewer instructions / special facts**")
    st.write(metadata.get("reviewer_notes") or "—")

    st.markdown("**What are these files**")
    st.write(metadata.get("document_description") or "—")

    st.markdown("**Client / company profile**")
    st.write(metadata.get("company_profile") or "—")

    st.markdown("**ATO / ITR policy year**")
    st.write(metadata.get("ato_policy_year") or "—")

    st.markdown("**Company tax rate assessment**")
    rate_category = metadata.get("company_tax_rate_category") or "review_required"
    st.write(
        {
            "base_rate_entity": "25% — confirmed base rate entity",
            "general": "30% — other company",
            "review_required": "Not confirmed — tax payable not calculated",
        }.get(rate_category, rate_category)
    )
    base_rate_assessment = metadata.get("base_rate_entity_assessment") or {}
    if base_rate_assessment:
        st.caption(
            "Aggregated turnover: "
            f"${base_rate_assessment.get('aggregated_turnover', '—')} · "
            "Assessable income: "
            f"${base_rate_assessment.get('total_assessable_income', '—')} · "
            "Passive income: "
            f"${base_rate_assessment.get('base_rate_entity_passive_income', '—')}"
        )
        ratio = base_rate_assessment.get("passive_income_ratio")
        ratio_text = "—"
        try:
            ratio_text = f"{float(ratio):.2%}"
        except (TypeError, ValueError):
            pass
        st.caption(
            f"Passive-income ratio: {ratio_text} · Reviewer confirmed: "
            f"{'Yes' if base_rate_assessment.get('reviewer_confirmed') is True else 'No'}"
        )

    uploaded = metadata.get("uploaded_files") or []
    st.markdown("**Uploaded files**")
    if uploaded:
        for name in uploaded:
            st.caption(f"• {name}")
    else:
        st.caption("—")


def _render_detected_and_warnings(result: dict[str, Any]) -> None:
    """Render detected reports and backend warnings."""

    st.markdown('<div class="section-header">Detected reports and backend warnings</div>', unsafe_allow_html=True)

    col_det, col_warn = st.columns(2)

    with col_det:
        st.markdown(f"**{T.DETECTED_HEADER}**")
        detected = result.get("detected", {})
        if detected:
            for name, found in detected.items():
                badge_cls = "badge-green" if found else "badge-grey"
                icon = "✓" if found else "–"
                st.markdown(
                    f'<span class="badge {badge_cls}">{icon} {name}</span>',
                    unsafe_allow_html=True,
                )
        else:
            st.caption("No detection summary returned.")

    with col_warn:
        warnings = result.get("warnings", [])
        st.markdown(f"**{T.WARNINGS_HEADER}**")

        if warnings:
            for warning in warnings:
                st.markdown(
                    f'<span class="badge badge-warning">⚠ {warning}</span>',
                    unsafe_allow_html=True,
                )
        else:
            st.markdown(
                f'<span class="badge badge-green">✓ {T.WARNINGS_NONE}</span>',
                unsafe_allow_html=True,
            )


def _render_rule_question_box(
    *,
    result: dict[str, Any],
    metadata: dict[str, Any],
    text_area_key: str,
    button_label: str,
    button_key: str,
) -> None:
    """Render Gemini/fallback question box."""

    st.markdown('<div class="section-header">Ask why the system labelled something</div>', unsafe_allow_html=True)

    revision_text = st.text_area(
        "Ask Gemini to explain the ITR label using itr_rules.py / itr_rules_2026.py",
        placeholder=(
            "Example: Why did consulting income map to 6C? "
            "Why was depreciation added back? "
            "Why is this account marked Review?"
        ),
        help=(
            "If Gemini is configured in AI API input, the app reads the relevant ITR rules file "
            "and asks Gemini to explain the rule logic. Otherwise it uses a simple fallback."
        ),
        height=110,
        key=text_area_key,
        label_visibility="collapsed",
    )

    if st.button(button_label, use_container_width=True, key=button_key):
        if not revision_text.strip():
            st.warning("Please enter a question or revision request.")
        else:
            st.session_state.revision_response = _handle_revision_question(
                question=revision_text,
                result=result,
                metadata=metadata,
                policy_year=metadata.get("ato_policy_year", "2026"),
                ai_provider=st.session_state.get("AI_PROVIDER", "None"),
                ai_model=st.session_state.get("AI_MODEL", "gemini-2.5-flash"),
                api_key=st.session_state.get("AI_API_KEY", ""),
            )
            st.rerun()

    if st.session_state.revision_response:
        st.markdown(
            """
            <div style="background:#f0f4ff;border:1px solid #c8d6f5;border-radius:6px;
                        padding:1rem 1.2rem;margin-top:0.8rem;font-size:0.88rem;">
            """,
            unsafe_allow_html=True,
        )
        st.markdown(st.session_state.revision_response)
        st.markdown("</div>", unsafe_allow_html=True)


def _render_custom_override_box() -> None:
    """Render custom ITR override UI."""

    st.markdown('<div class="section-header">Custom ITR override</div>', unsafe_allow_html=True)

    st.caption(
        "Use this when a labelled account is wrong. "
        "Generate the workpaper again to apply the change."
    )

    with st.expander("Add custom override", expanded=False):
        report_type = st.selectbox(
            "Report type",
            ["profit_and_loss", "balance_sheet"],
            index=0,
            key="override_report_type",
        )

        match_type = st.selectbox(
            "Match type",
            ["contains", "exact", "regex"],
            index=0,
            key="override_match_type",
        )

        account_pattern = st.text_input(
            "Account pattern",
            placeholder="Example: bank fees / consulting income / depreciation",
            key="override_account_pattern",
        )

        section_pattern = st.text_input(
            "Optional section pattern",
            placeholder="Example: income / operating expenses / current assets",
            key="override_section_pattern",
        )

        override_name = st.text_input(
            "Override name",
            placeholder="Example: Bank fees to review",
            key="override_name",
        )

        col_a, col_b = st.columns(2)

        with col_a:
            itr_ref = st.text_input(
                "New ITR Ref",
                placeholder="Example: Review / Inc - 6C / Exp - 6S",
                key="override_itr_ref",
            )

            treatment = st.selectbox(
                "Treatment",
                [
                    "financial_label_only",
                    "review_only",
                    "support_only",
                    "unmapped",
                ],
                index=1,
                key="override_treatment",
            )

        with col_b:
            itr_label = st.text_input(
                "New ITR Label",
                placeholder="Example: User override - review bank fees",
                key="override_itr_label",
            )

            confidence = st.selectbox(
                "Confidence",
                ["high", "medium", "low"],
                index=0,
                key="override_confidence",
            )

        review_note = st.text_area(
            "Review note",
            placeholder="Example: User override: force this account to review.",
            key="override_review_note",
        )

        override_reason = st.text_area(
            "Reason",
            placeholder="Example: Accountant reviewed this account and confirmed the base rule was not appropriate.",
            key="override_reason",
        )

        save_override_clicked = st.button(
            "Save custom override",
            use_container_width=True,
            key="save_custom_override",
        )

        if save_override_clicked:
            try:
                override = build_override_from_form(
                    name=override_name,
                    report_type=report_type,
                    account_pattern=account_pattern,
                    match_type=match_type,
                    itr_ref=itr_ref,
                    itr_label=itr_label,
                    treatment=treatment,
                    confidence=confidence,
                    review_note=review_note,
                    reason=override_reason,
                    section_pattern=section_pattern,
                )

                append_override(override)

                st.success(
                    "Custom override saved. Click Generate workpaper again to apply it."
                )

                st.json(override)

            except Exception as exc:
                st.error(f"Could not save override: {exc}")

    with st.expander("Current custom overrides", expanded=False):
        override_doc = load_override_doc()
        st.json(override_doc)


def _render_debug_block(result: dict[str, Any]) -> None:
    """Render backend debug block."""

    with st.expander(T.SECTION_DEBUG, expanded=False):
        st.markdown(f"**{T.UPLOAD_USED_HEADER}**")
        for name in result.get("uploaded_files", []):
            st.caption(f"• {name}")

        st.markdown(f"**{T.DEBUG_FRONTEND_UPLOAD_DIR}**")
        st.code("\n".join(result.get("frontend_upload_paths", [])), language="text")

        st.markdown(f"**{T.DEBUG_BACKEND_DATA_DIR}**")
        st.code("\n".join(result.get("backend_data_paths", [])), language="text")

        st.markdown(f"**{T.DEBUG_BACKEND_OUTPUT_DIR}**")
        st.code(str(result.get("backend_output_path", "")), language="text")

        st.markdown(f"**{T.DEBUG_BACKEND_COMMAND}**")
        st.code(result.get("backend_command", ""), language="bash")

        st.markdown(f"**{T.DEBUG_BACKEND_LOG}**")
        st.code(result.get("backend_log", ""), language="text")


# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title=T.APP_TITLE,
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)


# ── CSS ───────────────────────────────────────────────────────────────────────
st.markdown(
    """
<style>
    @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap');

    html, body, [class*="css"] {
        font-family: 'IBM Plex Sans', sans-serif;
    }

    .block-container {
        padding-top: 2rem;
        padding-bottom: 2rem;
    }

    .section-header {
        font-size: 0.75rem;
        font-weight: 600;
        letter-spacing: 0.12em;
        text-transform: uppercase;
        color: #888;
        margin-bottom: 0.5rem;
        margin-top: 1.5rem;
        border-bottom: 1px solid #e8e8e8;
        padding-bottom: 0.3rem;
    }

    .app-title {
        font-size: 1.6rem;
        font-weight: 600;
        color: #1a1a2e;
        letter-spacing: -0.02em;
        margin-bottom: 0;
    }

    .app-subtitle {
        font-size: 0.85rem;
        color: #999;
        margin-top: 0.1rem;
        margin-bottom: 1.5rem;
        font-family: 'IBM Plex Mono', monospace;
    }

    .result-card {
        background: #f8fafb;
        border: 1px solid #e0e8ef;
        border-radius: 8px;
        padding: 1.2rem 1.4rem;
        margin-bottom: 1rem;
    }

    .result-card-success {
        border-left: 4px solid #2ecc71;
    }

    .badge {
        display: inline-block;
        font-size: 0.75rem;
        font-weight: 500;
        padding: 2px 8px;
        border-radius: 4px;
        margin-right: 6px;
        margin-bottom: 4px;
    }

    .badge-green {
        background: #d4edda;
        color: #155724;
    }

    .badge-grey {
        background: #e9ecef;
        color: #6c757d;
    }

    .badge-warning {
        background: #fff3cd;
        color: #856404;
    }

    hr {
        border: none;
        border-top: 1px solid #eee;
        margin: 1.5rem 0;
    }

    .admin-section {
        background: #fff9f0;
        border: 1px solid #ffe4b5;
        border-radius: 6px;
        padding: 1rem 1.2rem;
        margin-top: 1rem;
    }

    .admin-label {
        font-size: 0.72rem;
        letter-spacing: 0.1em;
        text-transform: uppercase;
        color: #c0883a;
        font-weight: 600;
    }

    code {
        white-space: pre-wrap;
    }
</style>
""",
    unsafe_allow_html=True,
)


# ── Session state ─────────────────────────────────────────────────────────────
if "job_result" not in st.session_state:
    st.session_state.job_result = None

if "revision_response" not in st.session_state:
    st.session_state.revision_response = None

if "view_mode" not in st.session_state:
    st.session_state.view_mode = "new"

if "upload_key_nonce" not in st.session_state:
    st.session_state.upload_key_nonce = 0

if "current_workpaper_metadata" not in st.session_state:
    st.session_state.current_workpaper_metadata = {}

if "history_owner_id" not in st.session_state:
    st.session_state.history_owner_id = uuid.uuid4().hex


# ── Top navigation ────────────────────────────────────────────────────────────
nav_col_1, nav_col_2 = st.columns(2)

with nav_col_1:
    if st.button("New workpaper", use_container_width=True):
        st.session_state.view_mode = "new"
        st.session_state.job_result = None
        st.session_state.revision_response = None
        st.session_state.current_workpaper_metadata = {}
        st.session_state.upload_key_nonce += 1
        st.rerun()

with nav_col_2:
    if st.button("Previous workpapers", use_container_width=True):
        st.session_state.view_mode = "history"
        st.session_state.revision_response = None
        st.rerun()

st.markdown("<hr>", unsafe_allow_html=True)


# ── Layout ────────────────────────────────────────────────────────────────────
left, right = st.columns([1, 1], gap="large")


# ─────────────────────────────────────────────────────────────────────────────
# LEFT COLUMN
# ─────────────────────────────────────────────────────────────────────────────
with left:
    if st.session_state.view_mode == "history":
        st.markdown('<div class="app-title">Previous workpapers</div>', unsafe_allow_html=True)
        st.markdown(
            '<div class="app-subtitle">Review generated files and saved user inputs</div>',
            unsafe_allow_html=True,
        )

        previous_files = _list_previous_workpapers(st.session_state.history_owner_id)

        if not previous_files:
            st.info("No previous workpapers found in frontend/downloads/ yet.")
        else:
            selected_history_file = st.selectbox(
                "Select previous workpaper",
                options=previous_files,
                format_func=_format_history_file,
                key="selected_history_file",
            )

            if selected_history_file and selected_history_file.exists():
                st.markdown("**Selected workpaper**")
                st.code(str(selected_history_file), language="text")

                _download_workbook_button(
                    path=selected_history_file,
                    label="Download selected workpaper",
                    file_name=selected_history_file.name,
                    key="download_history_workpaper",
                )

                st.markdown("<hr>", unsafe_allow_html=True)

                history_metadata = _load_history_metadata(selected_history_file)
                _render_metadata_block(history_metadata)

        st.markdown("<hr>", unsafe_allow_html=True)

        with st.expander("Current custom ITR overrides", expanded=False):
            override_doc = load_override_doc()
            st.json(override_doc)

    else:
        st.markdown(f'<div class="app-title">{T.APP_TITLE}</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="app-subtitle">{T.APP_SUBTITLE}</div>', unsafe_allow_html=True)

        client_name = st.text_input(
            T.CLIENT_NAME_LABEL,
            placeholder=T.CLIENT_NAME_PLACEHOLDER,
            help=T.CLIENT_NAME_HELP,
        )

        # ── Upload files ─────────────────────────────────────────────────────
        st.markdown(f'<div class="section-header">{T.SECTION_FILES}</div>', unsafe_allow_html=True)

        uploaded_files = st.file_uploader(
            T.UPLOAD_FILES_LABEL,
            type=T.UPLOAD_FILE_TYPES,
            accept_multiple_files=True,
            key=f"excel_files_uploader_{st.session_state.upload_key_nonce}",
            help=T.UPLOAD_FILES_HELP,
        )

        if uploaded_files:
            st.caption(f"{len(uploaded_files)} {T.UPLOAD_SELECTED_PREFIX}")
            for uploaded_file in uploaded_files:
                st.caption(f"• {uploaded_file.name}")

        # ── Client profile ───────────────────────────────────────────────────
        st.markdown(f'<div class="section-header">{T.SECTION_PROFILE}</div>', unsafe_allow_html=True)

        company_type = st.selectbox(
            T.COMPANY_TYPE_LABEL,
            options=T.COMPANY_TYPES,
        )

        company_profile_notes = st.text_area(
            T.COMPANY_PROFILE_LABEL,
            placeholder=T.COMPANY_PROFILE_PLACEHOLDER,
            help=T.COMPANY_PROFILE_HELP,
            height=90,
        )

        company_profile = f"{company_type}. {company_profile_notes}".strip(". ")

        # ── Document / job description ───────────────────────────────────────
        st.markdown(f'<div class="section-header">{T.SECTION_DESCRIBE}</div>', unsafe_allow_html=True)

        ato_policy_year = st.selectbox(
            "ATO / ITR policy year",
            options=ATO_POLICY_YEARS,
            index=0,
            help="This will be passed to the backend so itr_rules / ato_policy can switch rule sets.",
        )

        selected_table_keys = st.multiselect(
            "Optional review schedules",
            options=list(OPTIONAL_TABLES),
            format_func=lambda key: OPTIONAL_TABLES[key],
            help="Only selected schedules will be added to the workbook.",
        )
        requested_tables = {
            key: key in selected_table_keys
            for key in OPTIONAL_TABLES
        }

        assess_base_rate = st.checkbox(
            "Assess eligibility for the 25% base-rate-entity tax rate",
            value=False,
            help=(
                "The system checks the two numerical thresholds. An accountant "
                "must still confirm aggregation and passive-income classification."
            ),
        )

        base_rate_entity_assessment: dict[str, Any] = {}
        base_rate_available = False

        if assess_base_rate:
            st.caption(
                "Enter income-year figures. Aggregated turnover must include relevant "
                "connected and affiliated entities."
            )
            bre_col_1, bre_col_2, bre_col_3 = st.columns(3)
            with bre_col_1:
                aggregated_turnover = st.number_input(
                    "Aggregated turnover ($)",
                    min_value=0.0,
                    value=0.0,
                    step=1000.0,
                    format="%.2f",
                )
            with bre_col_2:
                total_assessable_income = st.number_input(
                    "Total assessable income ($)",
                    min_value=0.0,
                    value=0.0,
                    step=1000.0,
                    format="%.2f",
                )
            with bre_col_3:
                passive_income = st.number_input(
                    "Base-rate passive income ($)",
                    min_value=0.0,
                    value=0.0,
                    step=1000.0,
                    format="%.2f",
                )

            figures_ready = total_assessable_income > 0
            reviewer_confirmed_base_rate = False
            try:
                preliminary_assessment = build_base_rate_entity_assessment(
                    ato_policy_year,
                    aggregated_turnover=str(aggregated_turnover),
                    total_assessable_income=str(total_assessable_income),
                    base_rate_entity_passive_income=str(passive_income),
                )
                passive_percentage = float(
                    preliminary_assessment["passive_income_ratio"]
                )
                turnover_result = (
                    "Pass" if preliminary_assessment["turnover_below_threshold"] else "Fail"
                )
                passive_result = (
                    "Pass"
                    if preliminary_assessment["passive_income_ratio_within_limit"]
                    else "Fail"
                )
                st.caption(
                    f"Turnover test: {turnover_result} · Passive-income test: "
                    f"{passive_result} ({passive_percentage:.2%})"
                )

                numeric_tests_pass = bool(
                    figures_ready
                    and preliminary_assessment["eligible_on_supplied_figures"]
                )
                reviewer_confirmed_base_rate = st.checkbox(
                    "I confirm the figures include the required connected/affiliated "
                    "entities and the passive-income classification has been reviewed.",
                    value=False,
                    disabled=not numeric_tests_pass,
                )
                base_rate_entity_assessment = build_base_rate_entity_assessment(
                    ato_policy_year,
                    aggregated_turnover=str(aggregated_turnover),
                    total_assessable_income=str(total_assessable_income),
                    base_rate_entity_passive_income=str(passive_income),
                    reviewer_confirmed=reviewer_confirmed_base_rate,
                )
                base_rate_available = bool(
                    numeric_tests_pass and reviewer_confirmed_base_rate
                )
                if not figures_ready:
                    st.info("Enter total assessable income to complete the assessment.")
                elif not preliminary_assessment["eligible_on_supplied_figures"]:
                    st.warning("The supplied figures do not qualify for the 25% rate.")
                elif base_rate_available:
                    st.success("The 25% rate is available for selection on the supplied facts.")
            except ValueError as exc:
                st.error(f"Base-rate-entity assessment could not be completed: {exc}")

        tax_rate_options = ["review_required", "general"]
        if base_rate_available:
            tax_rate_options.insert(1, "base_rate_entity")

        tax_rate_choice = st.selectbox(
            "Company tax rate",
            options=tax_rate_options,
            format_func=lambda value: {
                "review_required": "Not confirmed — do not calculate tax payable",
                "base_rate_entity": "25% — confirmed base rate entity",
                "general": "30% — other company",
            }[value],
            help=(
                "The 25% option is locked until the numerical assessment passes and "
                "the reviewer confirmation is selected."
            ),
        )
        if not base_rate_available:
            st.caption("25% is locked until the base-rate-entity assessment is completed.")

        reviewer_notes = st.text_area(
            "Reviewer instructions / special facts",
            placeholder=(
                "Example: Prior-year tax losses exist; R&D claim expected; "
                "director loan may need Div 7A review; check consulting income classification."
            ),
            height=80,
        )

        document_description = st.text_area(
            T.DOC_DESCRIPTION_LABEL,
            placeholder=T.DOC_DESCRIPTION_PLACEHOLDER,
            help=T.DOC_DESCRIPTION_HELP,
            height=90,
        )

        # ── AI API input ─────────────────────────────────────────────────────
        ai_provider = "None"
        ai_model = ""
        api_key = ""
        run_ai_face_check = False

        with st.expander("AI API input", expanded=True):
            st.markdown(
                """
                <div class="admin-section">
                    <div class="admin-label">AI API input</div>
                    <p style="font-size:0.85rem;color:#6b5c3a;margin-top:0.5rem;">
                        Optional. Gemini is used for rule explanations by reading
                        <code>v1/itr_rules.py</code> and the selected year-specific rule file.
                    </p>
                </div>
                """,
                unsafe_allow_html=True,
            )

            ai_provider = st.selectbox(
                "AI provider",
                options=AI_PROVIDER_OPTIONS,
                index=0,
                help=(
                    "Optional AI explanation / face-check after workbook generation. "
                    "Gemini is currently the supported rule-explanation path."
                ),
                key="admin_ai_provider",
            )

            if ai_provider != "None":
                api_key = st.text_input(
                    f"{ai_provider} API key",
                    type="password",
                    placeholder=f"Paste {ai_provider} API key for this session",
                    help=(
                        "The key is used for this Streamlit run only. "
                        "For production, prefer Streamlit secrets or environment variables."
                    ),
                    key="admin_ai_api_key",
                )

                ai_model = st.selectbox(
                    "Model",
                    options=AI_MODEL_OPTIONS.get(ai_provider, []),
                    index=0,
                    help="Select the model used for the optional AI explanation.",
                    key="admin_ai_model",
                )

            run_ai_face_check = st.checkbox(
                "Run AI face-check after workbook generation",
                value=False,
                disabled=ai_provider == "None",
                help=(
                    "Sends user inputs and workbook summary to the selected AI model. "
                    "This should not replace accountant review."
                ),
                key="admin_run_ai_face_check",
            )

            if run_ai_face_check and ai_provider != "None" and not api_key:
                st.warning(f"Please enter a {ai_provider} API key, or turn off AI face-check.")

            st.session_state["AI_PROVIDER"] = ai_provider
            st.session_state["AI_MODEL"] = ai_model
            st.session_state["AI_API_KEY"] = api_key
            st.session_state["AI_API_KEY_ENTERED"] = bool(api_key)

        # ── Generate ─────────────────────────────────────────────────────────
        st.markdown("")

        generate_clicked = st.button(
            T.GENERATE_BUTTON_LABEL,
            type="primary",
            use_container_width=True,
        )

        if generate_clicked:
            if not uploaded_files:
                st.error(T.ERROR_NO_FILES)

            elif run_ai_face_check and ai_provider != "None" and not api_key:
                st.error(f"Please enter a {ai_provider} API key in AI API input, or turn off AI face-check.")

            else:
                with st.spinner(T.GENERATING_SPINNER_LABEL):
                    result = run_workpaper_job(
                        extra_files=uploaded_files,
                        company_profile=company_profile,
                        document_description=document_description,
                        client_name=client_name,
                        ato_policy_year=ato_policy_year,
                        requested_tables=requested_tables,
                        reviewer_notes=reviewer_notes,
                        run_ai_face_check=run_ai_face_check,
                        company_tax_rate_category=tax_rate_choice,
                        base_rate_entity_assessment=base_rate_entity_assessment,
                        history_owner_id=st.session_state.history_owner_id,
                        ai_provider=ai_provider,
                        ai_model=ai_model,
                        ai_api_key=api_key,
                    )

                _save_history_metadata(
                    result=result,
                    client_name=client_name,
                    company_type=company_type,
                    company_profile_notes=company_profile_notes,
                    company_profile=company_profile,
                    reviewer_notes=reviewer_notes,
                    document_description=document_description,
                    ato_policy_year=ato_policy_year,
                    uploaded_files=list(uploaded_files or []),
                    ai_provider=ai_provider,
                    ai_model=ai_model,
                    run_ai_face_check=run_ai_face_check,
                    company_tax_rate_category=tax_rate_choice,
                    base_rate_entity_assessment=base_rate_entity_assessment,
                    requested_tables=requested_tables,
                )

                output_path = result.get("output_path")
                if output_path:
                    st.session_state.current_workpaper_metadata = _load_history_metadata(output_path)
                else:
                    st.session_state.current_workpaper_metadata = {}

                st.session_state.job_result = result
                st.session_state.revision_response = None
                st.session_state.view_mode = "new"
                st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# RIGHT COLUMN
# ─────────────────────────────────────────────────────────────────────────────
with right:
    if st.session_state.view_mode == "history":
        st.markdown('<div class="section-header">History preview</div>', unsafe_allow_html=True)

        selected_history_file = st.session_state.get("selected_history_file")

        if selected_history_file:
            selected_history_file = Path(selected_history_file)
            history_metadata = _load_history_metadata(selected_history_file)

            st.markdown(
                f"""
                <div class="result-card result-card-success">
                    <div style="font-weight:600;font-size:1rem;color:#1a1a2e;margin-bottom:0.6rem;">
                        Previous workpaper selected
                    </div>
                    <div style="font-size:0.82rem;color:#555;">
                        File:
                        <code style="font-family:'IBM Plex Mono',monospace;">
                            {selected_history_file.name}
                        </code>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            if selected_history_file.exists():
                st.caption("Use the download button on the left to open this workbook.")

                with st.expander("Saved metadata JSON", expanded=False):
                    if history_metadata:
                        st.json(history_metadata)
                    else:
                        st.info("No sidecar metadata JSON found for this old workpaper.")

                st.markdown("<hr>", unsafe_allow_html=True)

                fake_result = {
                    "output_name": selected_history_file.name,
                    "output_path": str(selected_history_file),
                    "detected": history_metadata.get("detected", {}),
                    "warnings": history_metadata.get("warnings", []),
                }

                _render_rule_question_box(
                    result=fake_result,
                    metadata=history_metadata,
                    text_area_key="history_revision_question",
                    button_label="Ask about selected previous workpaper",
                    button_key="ask_history_rule_explanation",
                )

            else:
                st.warning("Selected history file no longer exists.")
        else:
            st.info("Select a previous workpaper from the left panel.")

    else:
        result = st.session_state.job_result

        if result is None:
            st.markdown(
                """
                <div style="margin-top:3rem;color:#bbb;text-align:center;">
                    <div style="font-size:2.5rem;margin-bottom:0.5rem;">📄</div>
                    <div style="font-size:0.9rem;">
                        Upload Excel workbook(s) and click <strong>Generate workpaper</strong>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        elif result.get("status") == "error":
            st.markdown(f'<div class="section-header">{T.SECTION_RESULT}</div>', unsafe_allow_html=True)
            st.error(T.ERROR_PIPELINE)

            uploaded_names = result.get("uploaded_files") or []
            if uploaded_names:
                st.markdown("**Uploaded files received:**")
                for name in uploaded_names:
                    st.caption(f"• {name}")

            with st.expander("Error details", expanded=True):
                st.code(result.get("error_message", "Unknown error"), language="text")

            _render_debug_block(result)

        else:
            # 1. Result
            st.markdown(f'<div class="section-header">{T.SECTION_RESULT}</div>', unsafe_allow_html=True)

            st.markdown(
                f"""
                <div class="result-card result-card-success">
                    <div style="font-weight:600;font-size:1rem;color:#1a1a2e;margin-bottom:0.6rem;">
                        ✓ &nbsp;{T.SUCCESS_HEADER}
                    </div>
                    <div style="font-size:0.82rem;color:#555;">
                        Output:
                        <code style="font-family:'IBM Plex Mono',monospace;">
                            {result.get("output_name", "")}
                        </code>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            output_path = result.get("output_path")
            if output_path and Path(output_path).exists():
                _download_workbook_button(
                    path=Path(output_path),
                    label=T.DOWNLOAD_BUTTON,
                    file_name=result.get("output_name", "workpaper.xlsx"),
                    key="download_current_workpaper",
                )
            else:
                st.warning(T.ERROR_OUTPUT_MISSING)

            metadata = st.session_state.current_workpaper_metadata
            if not metadata and output_path:
                metadata = _load_history_metadata(output_path)

            with st.expander("Saved user inputs for this workpaper", expanded=True):
                _render_metadata_block(metadata)

            st.markdown("<hr>", unsafe_allow_html=True)

            # 2. Detected reports and backend warnings
            _render_detected_and_warnings(result)

            st.markdown("<hr>", unsafe_allow_html=True)

            # 3. Ask why system labelled something
            _render_rule_question_box(
                result=result,
                metadata=metadata,
                text_area_key="current_revision_question",
                button_label="Ask rule explanation",
                button_key="ask_current_rule_explanation",
            )

            st.markdown("<hr>", unsafe_allow_html=True)

            # 4. Custom ITR override
            _render_custom_override_box()

            st.markdown("<hr>", unsafe_allow_html=True)

            # Optional debug after the main workflow
            _render_debug_block(result)
