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
- Optional Gemini/Grok review uses only minimised decision evidence.
"""

from __future__ import annotations

import json
import re
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

if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

if str(FRONTEND_DIR) not in sys.path:
    sys.path.insert(0, str(FRONTEND_DIR))

import ui_text as T
from job_runner import build_base_rate_entity_assessment, run_workpaper_job
from scan_runner import (
    cleanup_scan,
    open_scan_source_files,
    run_scan_job,
    verify_scan_sources,
)
from ai_review import (
    ACCOUNTANT_DISPOSITION_STATUSES,
    audit_path_for_workpaper,
    read_ai_review_audit,
    update_accountant_disposition,
)
from override_editor import (
    append_override,
    build_override_from_form,
    load_override_doc,
)
from workpaper_library import group_workpapers_by_client
from workbook_canvas import (
    WorkbookCanvasError,
    export_manual_workbook_revision,
    load_workbook_canvas,
    render_workbook_canvas,
)


def _ensure_ui_text_hot_reload_compatibility() -> None:
    """Backfill renamed UI constants when Streamlit has cached an older module."""

    fallbacks = {
        "BUSINESS_PROFILE_LABEL": "Business profile / industry",
        "BUSINESS_PROFILE_SECTION_TITLE": "Business profile",
        "BUSINESS_PROFILE_SECTION_ICON": "🏢",
        "BUSINESS_PROFILE_IMPACT_NOTE": (
            "Used to pre-select likely review schedules and save engagement context. "
            "Calculations still come only from uploaded workbooks, deterministic rules "
            "and reviewed accountant inputs."
        ),
        "BUSINESS_PROFILE_OPTIONS": [
            "Service / consulting company",
            "Professional practice",
            "Product / trading company",
            "Retail / hospitality business",
            "Wholesale / distribution business",
            "Construction / contracting business",
            "Manufacturing business",
            "Software / SaaS company",
            "Technology company (possible R&D)",
            "Investment / holding company",
            "Property investment company",
            "Property development company",
            "Mixed operating group",
            "Other",
        ],
        "BUSINESS_PROFILE_ICONS": {
            "Service / consulting company": "💼",
            "Professional practice": "⚖️",
            "Product / trading company": "📦",
            "Retail / hospitality business": "🏪",
            "Wholesale / distribution business": "🚚",
            "Construction / contracting business": "🏗️",
            "Manufacturing business": "🏭",
            "Software / SaaS company": "💻",
            "Technology company (possible R&D)": "🔬",
            "Investment / holding company": "📈",
            "Property investment company": "🏢",
            "Property development company": "🏘️",
            "Mixed operating group": "🧭",
            "Other": "•",
        },
        "ATO_STATUS_SECTION": "ATO company-return status",
        "ATO_STATUS_IMPACT_NOTE": (
            "These return-status facts feed the company tax-rate control below. "
            "Special statuses block tax payable until an accountant confirms the rate."
        ),
        "ATO_STATUS_PRESET_LABEL": "Status preset",
        "ATO_STATUS_PRESET_OPTIONS": [
            "Private",
            "Public",
            "Special/review",
            "Detailed",
        ],
        "ATO_RESIDENCY_LABEL": "Residency status",
        "ATO_RESIDENCY_OPTIONS": [
            "Australian resident company",
            "Non-resident company",
            "Non-resident company carrying on business through an Australian PE",
            "Not required for selected entity type",
        ],
        "ATO_ENTITY_TYPE_LABEL": "Entity type for company return",
        "ATO_ENTITY_TYPE_OPTIONS": [
            "Private company",
            "Public company",
            "Non-profit company",
            "Strata title body corporate",
            "Corporate unit trust",
            "Public trading trust",
            "Trustee capacity / other special rate",
            "Life insurance company / friendly society",
            "Medium credit union",
            "Other / review required",
        ],
        "ATO_SPECIAL_STATUS_LABEL": "Special status",
        "ATO_SPECIAL_STATUS_OPTIONS": [
            "Non-profit company",
            "Trustee capacity / other special rate",
            "Life insurance company / friendly society",
            "Medium credit union",
            "Other / review required",
        ],
        "ATO_ACTIVITY_LABEL": "Activity indicator",
        "ATO_ACTIVITY_OPTIONS": [
            "None / ordinary trading or investment activity",
            "Life insurance or friendly society activity",
            "Pooled development fund / special entity activity",
            "Other activity requiring return-status review",
        ],
        "ATO_CONSOLIDATION_LABEL": "Consolidation status",
        "ATO_CONSOLIDATION_OPTIONS": [
            "Not a consolidated or MEC group member",
            "Consolidated or MEC head company",
            "Consolidated or MEC subsidiary member with non-membership period",
        ],
    }

    for name, value in fallbacks.items():
        if not hasattr(T, name):
            setattr(T, name, value)


_ensure_ui_text_hot_reload_compatibility()


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
    "related_party_loans": "Related party loan table",
    "psi": "Personal services income review table",
}

AI_PROVIDER_OPTIONS = ["None", "Gemini", "Grok"]

AI_MODEL_OPTIONS = {
    "Gemini": [
        "gemini-2.5-flash",
        "gemini-2.5-pro",
        "gemini-1.5-flash",
    ],
    "Grok": ["grok-4.6"],
}

RULE_CONTEXT_MAX_CHARS = 45_000


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────
def _list_previous_workpapers(history_owner_id: str) -> list[Path]:
    """Return session workpapers plus explicitly generated local batch runs."""
    history_dirs = {
        DOWNLOADS_DIR / history_owner_id,
        DOWNLOADS_DIR / "local-batch",
    }
    files = [
        path
        for history_dir in history_dirs
        if history_dir.exists()
        for path in history_dir.glob("*.xlsx")
        if path.is_file() and not path.name.startswith("~$")
    ]

    return sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)


def _format_history_file(path: Path) -> str:
    try:
        when = datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        return f"{path.name} — {when}"
    except Exception:
        return path.name


def _render_safety_stop_panel(result: dict[str, Any]) -> bool:
    """Render a plain-language fail-closed result; return whether one matched."""
    guidance = T.safety_stop_guidance(
        result.get("error_code"),
        result.get("selected_income_year"),
    )
    if guidance is None:
        return False

    st.error(guidance["title"])
    st.info(guidance["reason"])
    st.markdown(f"**What to do:** {guidance['action']}")
    st.caption(T.SAFETY_STOP_NO_CHANGE)
    return True


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
    business_profile_industry: str,
    company_profile_notes: str,
    company_profile: str,
    ato_company_status: dict[str, Any],
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
        "company_type": business_profile_industry,
        "business_profile_industry": business_profile_industry,
        "company_profile_notes": company_profile_notes,
        "company_profile": company_profile,
        "ato_company_status": ato_company_status,
        "reviewer_notes": reviewer_notes,
        "document_description": document_description,
        "ato_policy_year": ato_policy_year,
        "uploaded_files": uploaded_file_names,
        "ai_provider": ai_provider,
        "ai_model": ai_model,
        "run_ai_face_check": bool(run_ai_face_check),
        "ai_review_audit_path": result.get("ai_review_audit_path", ""),
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


def _save_revision_metadata(
    *,
    source_workpaper: Path,
    revision_workpaper: Path,
    revision_audit_path: Path,
) -> None:
    """Carry client context forward while recording an immutable revision link."""

    metadata = dict(_load_history_metadata(source_workpaper))
    metadata.update(
        {
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "output_name": revision_workpaper.name,
            "output_path": str(revision_workpaper),
            "parent_workpaper": source_workpaper.name,
            "revision_audit_path": str(revision_audit_path),
        }
    )
    metadata_path = _metadata_path_for_workpaper(revision_workpaper)
    with metadata_path.open("w", encoding="utf-8") as metadata_file:
        json.dump(metadata, metadata_file, indent=2, ensure_ascii=False)


def _render_ai_review_audit(workbook_path: Path | str | None) -> None:
    """Show a review sidecar and permit only accountant-disposition updates."""

    if not workbook_path:
        return

    audit_path = audit_path_for_workpaper(workbook_path)
    if not audit_path.exists():
        return

    try:
        audit = read_ai_review_audit(audit_path)
    except Exception as exc:
        st.warning(f"AI review audit could not be read: {exc}")
        return

    response = audit.get("response", {})
    provider = audit.get("provider", {})
    disposition = audit.get("accountant_disposition", {})
    key_prefix = f"ai_audit_{audit_path.as_posix()}"

    with st.expander("AI review audit (display-only)", expanded=False):
        st.caption(
            "This record is not part of the tax calculation. Updating the disposition "
            "does not change the workbook, rules, or tax outcome."
        )
        st.write(
            f"Provider: {provider.get('name', 'None')} · "
            f"Model: {provider.get('model', '') or '—'} · "
            f"Response: {response.get('status', 'unknown')}"
        )
        st.caption(
            f"Evidence hash: {audit.get('input_sha256', 'unavailable')} · "
            f"Prompt version: {audit.get('review_contract', {}).get('prompt_version', 'unknown')}"
        )

        findings = response.get("findings", [])
        if findings:
            st.markdown("**AI findings (review only)**")
            for index, finding in enumerate(findings, start=1):
                if not isinstance(finding, dict):
                    continue
                st.write(
                    f"{index}. [{finding.get('severity', 'unknown')}] "
                    f"{finding.get('recommended_review_action', 'No action supplied.')}"
                )
                st.caption(
                    f"Decision: {finding.get('decision_id', 'unknown')} · "
                    f"Evidence: {'; '.join(finding.get('evidence', []))}"
                )
        else:
            st.info("No AI findings were recorded for this workpaper.")

        ordered_statuses = ["pending", "accepted", "rejected", "not_applicable"]
        current_status = disposition.get("status", "pending")
        if current_status not in ACCOUNTANT_DISPOSITION_STATUSES:
            current_status = "pending"
        status = st.selectbox(
            "Accountant disposition",
            options=ordered_statuses,
            index=ordered_statuses.index(current_status),
            key=f"{key_prefix}_status",
        )
        reviewer = st.text_input(
            "Reviewer name or initials",
            value=disposition.get("reviewer", ""),
            key=f"{key_prefix}_reviewer",
        )
        note = st.text_area(
            "Accountant review note",
            value=disposition.get("note", ""),
            key=f"{key_prefix}_note",
        )
        if st.button("Save accountant disposition", key=f"{key_prefix}_save"):
            try:
                update_accountant_disposition(
                    audit_path,
                    status=status,
                    reviewer=reviewer,
                    note=note,
                )
            except Exception as exc:
                st.error(f"Could not save accountant disposition: {exc}")
            else:
                st.success("Accountant disposition saved. The workbook was not changed.")


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

Client/business profile:
{metadata.get("company_profile", "")}

ATO company-return status:
{metadata.get("ato_company_status", {})}

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

    st.markdown("**Business profile / industry**")
    st.write(
        metadata.get("business_profile_industry")
        or metadata.get("company_type")
        or "—"
    )

    st.markdown("**Client / workpaper context**")
    st.write(metadata.get("company_profile") or "—")

    ato_status = metadata.get("ato_company_status") or {}
    if ato_status:
        st.markdown("**ATO company-return status**")
        status_lines = [
            ato_status.get("residency_status"),
            ato_status.get("entity_type"),
            ato_status.get("activity_indicator"),
            ato_status.get("consolidation_status"),
        ]
        st.write(" · ".join(str(line) for line in status_lines if line) or "—")
        indicators = []
        if ato_status.get("small_business_entity_indicator"):
            indicators.append("Small business entity indicator selected")
        if ato_status.get("base_rate_entity_indicator"):
            indicators.append("Base-rate-entity indicator noted")
        if ato_status.get("significant_global_entity"):
            indicators.append("SGE")
        if ato_status.get("cbc_reporting_entity"):
            indicators.append("CBC reporting entity")
        if indicators:
            st.caption(" · ".join(indicators))
        if ato_status.get("forces_rate_review"):
            st.warning(
                "ATO status requires accountant review before company tax payable "
                "is calculated."
            )

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


def _build_ato_company_status(
    *,
    status_preset: str,
    residency_status: str,
    entity_type: str,
    activity_indicator: str,
    small_business_entity_indicator: bool,
    base_rate_entity_indicator: bool,
    significant_global_entity: bool,
    cbc_reporting_entity: bool,
    consolidation_status: str,
) -> dict[str, Any]:
    """Return display-only ATO return-status context for metadata/audit."""

    review_triggers = {
        "Non-profit company",
        "Trustee capacity / other special rate",
        "Life insurance company / friendly society",
        "Medium credit union",
        "Other / review required",
        "Life insurance or friendly society activity",
        "Pooled development fund / special entity activity",
        "Other activity requiring return-status review",
    }
    selected = {entity_type, activity_indicator}
    forces_rate_review = bool(selected & review_triggers)
    review_reason = ""
    if forces_rate_review:
        review_reason = (
            "Selected ATO status may use a special company-rate treatment. "
            "Company tax payable is withheld until accountant review confirms the rate."
        )

    return {
        "status_preset": status_preset,
        "residency_status": residency_status,
        "entity_type": entity_type,
        "activity_indicator": activity_indicator,
        "small_business_entity_indicator": small_business_entity_indicator is True,
        "base_rate_entity_indicator": base_rate_entity_indicator is True,
        "significant_global_entity": significant_global_entity is True,
        "cbc_reporting_entity": cbc_reporting_entity is True,
        "consolidation_status": consolidation_status,
        "forces_rate_review": forces_rate_review,
        "rate_review_reason": review_reason,
    }


def _suggest_review_tables_for_business_profile(
    business_profile_industry: str,
    *,
    company_profile_notes: str = "",
    document_description: str = "",
    reviewer_notes: str = "",
) -> dict[str, str]:
    """Return conservative review-scope defaults and their visible reasons."""

    profile = str(business_profile_industry or "").lower()
    context = " ".join(
        [
            profile,
            str(company_profile_notes or "").lower(),
            str(document_description or "").lower(),
            str(reviewer_notes or "").lower(),
        ]
    )
    suggestions: dict[str, str] = {}

    if re.search(r"\b(loss|losses|tax loss|prior[- ]year loss|carry[- ]forward)\b", context):
        suggestions["carry_forward_losses"] = (
            "Notes or source description mention losses. Add the loss-review schedule "
            "so eligibility and available losses are checked before any Item 7R deduction."
        )

    if any(term in profile for term in ("technology", "software", "saas", "r&d")):
        suggestions["rd_tax_incentive"] = (
            "Technology/R&D profile. Add the R&D review schedule for registration, "
            "schedule tie-out, associate-payment and Item 7D/Item 21 checks."
        )
    elif re.search(r"\b(r&d|rnd|research and development|research)\b", context):
        suggestions["rd_tax_incentive"] = (
            "Notes mention R&D. Add the R&D review schedule before any R&D claim "
            "or accounting add-back is considered."
        )

    if any(
        term in profile
        for term in (
            "product",
            "trading",
            "retail",
            "hospitality",
            "wholesale",
            "distribution",
            "construction",
            "contracting",
            "manufacturing",
            "property",
        )
    ):
        suggestions["depreciation"] = (
            "Asset/inventory-style profile. Check tax depreciation or capital "
            "allowances before any Item 7F posting."
        )

    if any(
        term in profile
        for term in ("investment", "holding", "property", "mixed operating group")
    ):
        suggestions["related_party_loans"] = (
            "Investment/holding/property profile. Related-party balances are more "
            "likely and should be reviewed before disclosure or adjustment."
        )

    if re.search(r"\b(div\s*7a|division\s*7a|director loan|shareholder loan)\b", context):
        suggestions["div7a"] = (
            "Notes mention shareholder/director loans or Div 7A. Add the review "
            "schedule for loan terms, repayments, benchmark interest and distributable surplus."
        )

    return suggestions


def _format_business_profile_option(option: str) -> str:
    """Display an icon with each profile while preserving the raw option value."""

    icon = getattr(T, "BUSINESS_PROFILE_ICONS", {}).get(option, "•")
    return f"{icon} {option}"


def _render_requested_table_control(
    *,
    key: str,
    suggested_review_tables: dict[str, str],
) -> bool:
    """Render a review-schedule checkbox with a visible suggestion reason."""

    is_suggested = key in suggested_review_tables
    label = OPTIONAL_TABLES[key]

    with st.container(border=True):
        if is_suggested:
            st.markdown(
                f"""
                <div class="schedule-suggestion">
                    <strong>Suggested review schedule</strong><br>
                    {suggested_review_tables[key]}
                </div>
                """,
                unsafe_allow_html=True,
            )
        elif key == "carry_forward_losses":
            st.caption(
                "Carry-forward losses are added only when selected or suggested from "
                "loss-related notes. The backend creates a review gate, not a posted deduction."
            )

        widget_key = f"requested_table_{key}"
        checkbox_kwargs: dict[str, Any] = {
            "key": widget_key,
            "help": (
                "Suggested by engagement context; untick if it is not relevant."
                if is_suggested
                else "Selected schedules are added to the workbook as review schedules."
            ),
        }
        if widget_key not in st.session_state:
            checkbox_kwargs["value"] = is_suggested

        return st.checkbox(label, **checkbox_kwargs)


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


def _render_tax_rate_control(
    ato_policy_year: str,
    *,
    forced_review_reason: str = "",
) -> tuple[str, dict[str, Any]]:
    """Render the mandatory company-rate decision and return its controlled outcome."""

    st.markdown('<div class="section-header">Company tax-rate determination</div>', unsafe_allow_html=True)

    with st.container(border=True):
        if forced_review_reason:
            st.markdown(
                f"""
                <div class="result-card result-card-warning" style="padding:0.75rem 0.9rem;margin-bottom:0;">
                    <div style="font-weight:600;color:#7a4b00;">Tax rate requires confirmation</div>
                    <div style="font-size:0.84rem;color:#5f4400;">
                        {forced_review_reason}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            return "review_required", {}

        st.caption(
            "Confirm the company rate before calculating tax payable. Choose base-rate "
            "assessment only when the current-year turnover and passive-income facts are reviewed."
        )

        tax_rate_decision = st.radio(
            "Company tax-rate decision",
            options=["assess_base_rate", "general", "review_required"],
            format_func=lambda value: {
                "assess_base_rate": "Assess eligibility for the 25% base-rate-entity rate",
                "general": "30% — other company",
                "review_required": "Pending accountant review — do not calculate tax payable",
            }[value],
            help=(
                "Choose 25% assessment only when the engagement includes evidence for the "
                "current-year aggregated-turnover and passive-income tests."
            ),
            key="company_tax_rate_decision",
        )

        if tax_rate_decision == "general":
            st.success("30% treatment selected. Record any unusual facts in reviewer instructions.")
            return "general", {}

        if tax_rate_decision == "review_required":
            st.markdown(
                """
                <div class="result-card result-card-warning" style="padding:0.75rem 0.9rem;margin-bottom:0;">
                    <div style="font-weight:600;color:#7a4b00;">Tax rate requires confirmation</div>
                    <div style="font-size:0.84rem;color:#5f4400;">
                        Company tax payable will remain uncalculated until the reviewer confirms the applicable rate.
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            return "review_required", {}

        st.markdown("**25% base-rate-entity assessment**")
        st.caption(
            "Use current-year amounts. Aggregated turnover includes relevant connected and "
            "affiliated entities; the passive-income test applies to the company itself."
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
                "Company assessable income ($)",
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
            passive_percentage = float(preliminary_assessment["passive_income_ratio"])
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
                figures_ready and preliminary_assessment["eligible_on_supplied_figures"]
            )
            reviewer_confirmed_base_rate = st.checkbox(
                "I confirm the connected/affiliated entity position and passive-income "
                "classification have been reviewed.",
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
        except ValueError as exc:
            st.error(f"Base-rate-entity assessment could not be completed: {exc}")
            return "review_required", {}

        if not figures_ready:
            st.info("Enter company assessable income to complete the 25% assessment.")
        elif not preliminary_assessment["eligible_on_supplied_figures"]:
            st.warning("The supplied figures do not qualify for the 25% rate.")
        elif reviewer_confirmed_base_rate:
            st.success("25% treatment confirmed on the supplied facts.")
            return "base_rate_entity", base_rate_entity_assessment
        else:
            st.info("Confirm the review statement above to apply the 25% rate.")

        return "review_required", base_rate_entity_assessment


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
    html, body, [class*="css"] {
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }

    .block-container {
        max-width: 1440px;
        /* Streamlit's fixed Chrome/Safari header overlays the document. Keep
           the first navigation row below it while compacting the page body. */
        padding-top: 4.25rem;
        padding-bottom: 2.5rem;
    }

    @media (max-width: 768px) {
        .block-container {
            padding-top: 3.75rem;
        }
    }

    .section-header {
        font-size: 0.75rem;
        font-weight: 700;
        letter-spacing: 0.12em;
        text-transform: uppercase;
        color: #64748b;
        margin-bottom: 0.35rem;
        margin-top: 1.15rem;
        border-bottom: 1px solid #e2e8f0;
        padding-bottom: 0.45rem;
    }

    .app-title {
        font-size: 1.4rem;
        font-weight: 600;
        color: #0f172a;
        letter-spacing: -0.02em;
        margin-bottom: 0;
    }

    .app-subtitle {
        font-size: 0.85rem;
        color: #64748b;
        margin-top: 0.1rem;
        margin-bottom: 0.85rem;
        font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, monospace;
    }

    .result-card {
        background: #f8fafc;
        border: 1px solid #dbe4ee;
        border-radius: 10px;
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
        background: #f8fafc;
        border: 1px solid #dbe4ee;
        border-radius: 8px;
        padding: 0.8rem 1rem;
        margin: 0.25rem 0 1rem;
    }

    .admin-label {
        font-size: 0.72rem;
        letter-spacing: 0.1em;
        text-transform: uppercase;
        color: #475569;
        font-weight: 700;
    }

    .profile-banner {
        display: flex;
        gap: 0.85rem;
        align-items: flex-start;
        border: 1px solid #cbd5e1;
        border-left: 4px solid #0f766e;
        border-radius: 8px;
        background: #f8fafc;
        padding: 0.85rem 1rem;
        margin: 0.25rem 0 0.85rem;
    }

    .profile-banner-icon {
        font-size: 1.35rem;
        line-height: 1.2;
    }

    .profile-banner-title {
        font-size: 0.95rem;
        color: #0f172a;
        font-weight: 700;
        margin-bottom: 0.2rem;
    }

    .profile-banner-copy {
        font-size: 0.83rem;
        color: #475569;
        margin: 0;
    }

    .schedule-suggestion {
        border: 1px solid #fca5a5;
        border-left: 4px solid #dc2626;
        border-radius: 8px;
        background: #fef2f2;
        padding: 0.65rem 0.75rem;
        margin: 0.15rem 0 0.5rem;
        color: #7f1d1d;
        font-size: 0.82rem;
    }

    .schedule-suggestion strong {
        color: #991b1b;
    }

    code {
        white-space: pre-wrap;
    }

    div[data-testid="stExpander"] {
        border: 1px solid #dbe4ee;
        border-radius: 10px;
        background: #ffffff;
    }

    div[data-testid="stExpander"] details summary {
        font-weight: 600;
        color: #1e293b;
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
    st.session_state.view_mode = "generator"

if "upload_key_nonce" not in st.session_state:
    st.session_state.upload_key_nonce = 0

if "current_workpaper_metadata" not in st.session_state:
    st.session_state.current_workpaper_metadata = {}

if "history_owner_id" not in st.session_state:
    st.session_state.history_owner_id = uuid.uuid4().hex

if "generator_stage" not in st.session_state:
    st.session_state.generator_stage = "upload"

if "scan_result" not in st.session_state:
    st.session_state.scan_result = None

if "review_answers" not in st.session_state:
    st.session_state.review_answers = {}

# Preserve an in-progress browser session after the navigation terminology
# changed. The old values were internal UI states, never persisted tax data.
if st.session_state.view_mode == "new":
    st.session_state.view_mode = "generator"
elif st.session_state.view_mode == "history":
    st.session_state.view_mode = "library"


# ── Compact navigation ────────────────────────────────────────────────────────
home_col, generator_col, editor_col = st.columns([0.8, 1.5, 1.5])

with home_col:
    if st.button("⌂ Main page (history)", key="open_client_library", use_container_width=True):
        st.session_state.view_mode = "library"
        st.session_state.revision_response = None
        st.rerun()

with generator_col:
    if st.button("1 · Generate workpaper", key="open_generator", use_container_width=True):
        st.session_state.view_mode = "generator"
        st.rerun()

with editor_col:
    if st.button("2 · Review & edit", key="open_review_editor", use_container_width=True):
        selected_history = st.session_state.get("selected_history_file")
        current_output = (st.session_state.get("job_result") or {}).get("output_path")
        if selected_history or current_output:
            st.session_state.editor_workpaper_path = str(selected_history or current_output)
        st.session_state.view_mode = "editor"
        st.rerun()

st.markdown("<hr style='margin:0.8rem 0 1rem;'>", unsafe_allow_html=True)


# ── Layout ────────────────────────────────────────────────────────────────────
if st.session_state.view_mode == "editor":
    # The spreadsheet canvas owns the editing surface; no side-panel form.
    left, right = st.columns([0.001, 0.999], gap="small")
elif st.session_state.view_mode == "generator":
    left = st.container()
    right = None
else:
    left, right = st.columns([1, 1], gap="large")


# ─────────────────────────────────────────────────────────────────────────────
# LEFT COLUMN
# ─────────────────────────────────────────────────────────────────────────────
with left:
    if st.session_state.view_mode == "library":
        st.markdown('<div class="app-title">Client workpaper library</div>', unsafe_allow_html=True)
        st.markdown(
            '<div class="app-subtitle">Select a client, then open a workpaper for review or download.</div>',
            unsafe_allow_html=True,
        )

        previous_files = _list_previous_workpapers(st.session_state.history_owner_id)

        if not previous_files:
            st.info("No previous workpapers found in frontend/downloads/ yet.")
        else:
            grouped_workpapers = group_workpapers_by_client(
                previous_files,
                metadata_loader=_load_history_metadata,
            )
            selected_client = st.selectbox(
                "Client",
                options=list(grouped_workpapers),
                key="selected_history_client",
            )
            selected_history_file = st.selectbox(
                "Workpaper",
                options=grouped_workpapers[selected_client],
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

                if st.button(
                    "Open in review & edit",
                    type="primary",
                    use_container_width=True,
                    key="open_selected_workpaper_in_editor",
                ):
                    st.session_state.editor_workpaper_path = str(selected_history_file)
                    st.session_state.view_mode = "editor"
                    st.rerun()

                st.markdown("<hr>", unsafe_allow_html=True)

                history_metadata = _load_history_metadata(selected_history_file)
                _render_metadata_block(history_metadata)

        st.markdown("<hr>", unsafe_allow_html=True)

        with st.expander("Current custom ITR overrides", expanded=False):
            override_doc = load_override_doc()
            st.json(override_doc)

    elif st.session_state.view_mode == "generator":
        st.markdown(f'<div class="app-title">{T.APP_TITLE}</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="app-subtitle">{T.APP_SUBTITLE}</div>', unsafe_allow_html=True)

        stage = st.session_state.generator_stage
        st.markdown(f"**Workflow:** {'Upload & profile' if stage == 'upload' else 'Scan & confirm' if stage == 'review' else 'Generate / result'}")

        if stage == "upload":
            st.markdown('<div class="section-header">1. Upload & profile</div>', unsafe_allow_html=True)
            with st.container(border=True):
                client_name = st.text_input(
                    T.CLIENT_NAME_LABEL,
                    placeholder=T.CLIENT_NAME_PLACEHOLDER,
                    help=T.CLIENT_NAME_HELP,
                    key="stage1_client_name",
                )
                ato_policy_year = st.selectbox(
                    "Income year",
                    options=ATO_POLICY_YEARS,
                    index=0,
                    help="Saved as profile context for scan; tax-rate assessment is confirmed after scan.",
                    key="stage1_ato_policy_year",
                )
                profile_entity_type = st.selectbox(
                    "Entity type",
                    options=["Private company", "Public company", "Special / unsure"],
                    index=0,
                    help="Profile context only. Legal/tax statuses are confirmed after scan.",
                    key="stage1_profile_entity_type",
                )
                business_profile_industry = st.selectbox(
                    T.BUSINESS_PROFILE_LABEL,
                    options=T.BUSINESS_PROFILE_OPTIONS,
                    index=0,
                    format_func=_format_business_profile_option,
                    key="stage1_business_profile_industry",
                    help=T.BUSINESS_PROFILE_IMPACT_NOTE,
                )
                uploaded_files = st.file_uploader(
                    T.UPLOAD_FILES_LABEL,
                    type=T.UPLOAD_FILE_TYPES,
                    accept_multiple_files=True,
                    key=f"excel_files_uploader_{st.session_state.upload_key_nonce}",
                    help=T.UPLOAD_FILES_HELP,
                )
                reviewer_notes = st.text_area(
                    "Reviewer / source note",
                    placeholder="Optional context for the scan and review trail.",
                    height=90,
                    key="stage1_reviewer_notes",
                )
                if uploaded_files:
                    st.caption(f"{len(uploaded_files)} file(s) selected")
                    for uploaded_file in uploaded_files:
                        st.caption(f"- {uploaded_file.name}")

                if st.button("Scan files", type="primary", use_container_width=True):
                    profile = {
                        "client_name": client_name,
                        "ato_policy_year": ato_policy_year,
                        "profile_entity_type": profile_entity_type,
                        "business_profile_industry": business_profile_industry,
                        "reviewer_notes": reviewer_notes,
                    }
                    with st.spinner("Scanning uploaded files without tax calculations..."):
                        scan_result = run_scan_job(
                            uploaded_files=uploaded_files,
                            profile=profile,
                        )
                    if scan_result.get("status") != "success":
                        st.error(scan_result.get("error_message") or "Scan failed.")
                        if scan_result.get("backend_log"):
                            with st.expander("Scan log", expanded=False):
                                st.code(scan_result["backend_log"])
                    else:
                        st.session_state.scan_result = scan_result
                        st.session_state.review_answers = {}
                        st.session_state.generator_stage = "review"
                        st.rerun()

        elif stage == "review":
            scan_result = st.session_state.scan_result or {}
            profile = scan_result.get("profile") or {}
            suggestions = {item["review_area"]: item for item in scan_result.get("suggestions", [])}
            profile_suggestions = _suggest_review_tables_for_business_profile(
                profile.get("business_profile_industry", ""),
                reviewer_notes=profile.get("reviewer_notes", ""),
            )
            suggested_review_tables = {
                key: value.get("reason", "")
                for key, value in suggestions.items()
                if key in OPTIONAL_TABLES
            }
            suggested_review_tables.update(profile_suggestions)
            generation_payload: dict[str, Any] = {}
            blocking_items: list[str] = []

            left_scan, right_review = st.columns([1, 1])
            with left_scan:
                st.markdown('<div class="section-header">System found</div>', unsafe_allow_html=True)
                with st.container(border=True):
                    st.markdown("**Detected reports**")
                    for report in scan_result.get("detected_reports", []):
                        st.caption(
                            f"{report['report_type']} | {report['source_file']} | "
                            f"{report['sheet_name']} | score {report['detection_score']}"
                        )
                    if not scan_result.get("detected_reports"):
                        st.info("No reports detected yet.")

                with st.container(border=True):
                    st.markdown("**Observed accounts / evidence**")
                    observations = scan_result.get("observations", [])
                    if observations:
                        for observation in observations[:30]:
                            amount = observation.get("amount")
                            amount_text = "—" if amount is None else f"${amount:,.2f}"
                            st.caption(
                                f"{observation['id']}: {observation['account']} | {amount_text} | "
                                f"{observation['report']} / {observation.get('section') or 'Unsectioned'}"
                            )
                    else:
                        st.caption("No review-trigger account wording detected.")

                with st.container(border=True):
                    st.markdown("**Suggested review areas**")
                    if suggested_review_tables:
                        for key, reason in suggested_review_tables.items():
                            st.markdown(
                                f"<div class='schedule-suggestion'><strong>{OPTIONAL_TABLES.get(key, key)}</strong><br>{reason}</div>",
                                unsafe_allow_html=True,
                            )
                    else:
                        st.caption("No scanner suggestions. Reviewers can still add areas on the right.")
                    for warning in scan_result.get("warnings", []):
                        st.warning(warning)

                if st.button("Reset scan", use_container_width=True):
                    cleanup_scan(st.session_state.scan_result)
                    st.session_state.scan_result = None
                    st.session_state.job_result = None
                    st.session_state.generator_stage = "upload"
                    st.session_state.upload_key_nonce += 1
                    st.rerun()

            with right_review:
                st.markdown('<div class="section-header">Reviewer confirms</div>', unsafe_allow_html=True)

                ato_policy_year = profile.get("ato_policy_year", "2026")
                client_name = profile.get("client_name", "")
                business_profile_industry = profile.get("business_profile_industry", "Other")
                company_profile_notes = profile.get("profile_entity_type", "")
                reviewer_notes = profile.get("reviewer_notes", "")
                company_profile = f"{business_profile_industry}. {company_profile_notes}".strip(". ")
                document_description = "Scanned staged upload"

                with st.container(border=True):
                    ato_status_preset = st.radio(
                        T.ATO_STATUS_PRESET_LABEL,
                        options=T.ATO_STATUS_PRESET_OPTIONS,
                        index=0 if profile.get("profile_entity_type") == "Private company" else 1 if profile.get("profile_entity_type") == "Public company" else 2,
                        horizontal=True,
                        key="stage2_ato_status_preset",
                    )
                    residency_status = "Australian resident company"
                    entity_type = "Public company" if ato_status_preset == "Public" else "Private company"
                    activity_indicator = "None / ordinary trading or investment activity"
                    consolidation_status = "Not a consolidated or MEC group member"
                    small_business_entity_indicator = False
                    base_rate_entity_indicator = False
                    significant_global_entity = False
                    cbc_reporting_entity = False
                    if ato_status_preset == "Special/review":
                        entity_type = st.selectbox(
                            T.ATO_SPECIAL_STATUS_LABEL,
                            options=T.ATO_SPECIAL_STATUS_OPTIONS,
                            index=0,
                            key="stage2_special_entity_type",
                        )
                    elif ato_status_preset == "Detailed":
                        residency_status = st.selectbox(T.ATO_RESIDENCY_LABEL, T.ATO_RESIDENCY_OPTIONS, key="stage2_residency")
                        entity_type = st.selectbox(T.ATO_ENTITY_TYPE_LABEL, T.ATO_ENTITY_TYPE_OPTIONS, key="stage2_entity_type")
                        consolidation_status = st.selectbox(T.ATO_CONSOLIDATION_LABEL, T.ATO_CONSOLIDATION_OPTIONS, key="stage2_consolidation")
                        activity_indicator = st.selectbox(T.ATO_ACTIVITY_LABEL, T.ATO_ACTIVITY_OPTIONS, key="stage2_activity")
                        small_business_entity_indicator = st.checkbox("Small business entity", key="stage2_sbe")
                        base_rate_entity_indicator = st.checkbox("Base rate entity", key="stage2_bre")
                        significant_global_entity = st.checkbox("SGE", key="stage2_sge")
                        cbc_reporting_entity = st.checkbox("CBC reporting entity", key="stage2_cbc")

                ato_company_status = _build_ato_company_status(
                    status_preset=ato_status_preset,
                    residency_status=residency_status,
                    entity_type=entity_type,
                    activity_indicator=activity_indicator,
                    small_business_entity_indicator=small_business_entity_indicator,
                    base_rate_entity_indicator=base_rate_entity_indicator,
                    significant_global_entity=significant_global_entity,
                    cbc_reporting_entity=cbc_reporting_entity,
                    consolidation_status=consolidation_status,
                )
                tax_rate_choice, base_rate_entity_assessment = _render_tax_rate_control(
                    ato_policy_year,
                    forced_review_reason=ato_company_status.get("rate_review_reason", ""),
                )

                st.markdown("**Review schedules**")
                requested_tables = {key: False for key in OPTIONAL_TABLES}
                reviewed_tax_losses: dict[str, Any] = {}
                reviewed_div7a: dict[str, Any] = {}

                loss_existence = st.radio(
                    "Does the company have reviewed prior-year tax losses available?",
                    options=["No", "Yes", "Not sure / review required"],
                    horizontal=True,
                    key="stage2_prior_year_tax_losses_exist",
                )
                requested_tables["carry_forward_losses"] = loss_existence != "No"
                if loss_existence == "Yes":
                    opening_losses = st.text_input("Reviewed available prior-year tax losses", key="stage2_opening_losses")
                    eligibility_confirmed = st.radio(
                        "Has utilisation eligibility been reviewed?",
                        options=["No", "Yes"],
                        horizontal=True,
                        key="stage2_loss_eligibility",
                    ) == "Yes"
                    requested_utilisation = st.text_input(
                        "Proposed utilisation",
                        disabled=not eligibility_confirmed,
                        key="stage2_loss_utilisation",
                    )
                    eligibility_basis = st.text_input(
                        "Eligibility basis",
                        disabled=not eligibility_confirmed,
                        key="stage2_loss_basis",
                    )
                    reviewed_tax_losses = {
                        "opening_losses": opening_losses,
                        "requested_utilisation": requested_utilisation,
                        "eligibility_confirmed": eligibility_confirmed,
                        "eligibility_basis": eligibility_basis,
                        "review_note": st.text_area("Tax loss review note", height=70, key="stage2_loss_note"),
                        "approved_for_posting": False,
                    }

                for key in OPTIONAL_TABLES:
                    if key in {"carry_forward_losses", "div7a"}:
                        continue
                    default = key in suggested_review_tables
                    requested_tables[key] = st.checkbox(
                        OPTIONAL_TABLES[key],
                        value=default,
                        key=f"stage2_requested_table_{key}",
                    )

                manual_add = st.multiselect(
                    "Add another review area",
                    options=list(OPTIONAL_TABLES),
                    format_func=lambda key: OPTIONAL_TABLES[key],
                    key="stage2_manual_add_review_area",
                )
                for key in manual_add:
                    requested_tables[key] = True

                requested_tables["div7a"] = st.checkbox(
                    OPTIONAL_TABLES["div7a"],
                    value="div7a" in suggested_review_tables,
                    key="stage2_requested_table_div7a",
                )
                if requested_tables["div7a"]:
                    st.markdown("**Division 7A review workflow**")
                    private_status_label = st.radio(
                        "Division 7A entity status",
                        ["Confirmed private company", "Not a private company", "Review required"],
                        horizontal=True,
                        key="stage2_div7a_private_status",
                    )
                    private_company_status = {
                        "Confirmed private company": "confirmed_private",
                        "Not a private company": "not_private",
                        "Review required": "review_required",
                    }[private_status_label]
                    transaction_exists_label = "Unsure / review required"
                    transaction_type = ""
                    source_account = ""
                    source_balance = ""
                    balance_direction = "unsure"
                    shareholder_status = "review_required"
                    loan_amount = opening_balance = repayments_before_lodgment = outstanding_at_lodgment = ""
                    fully_repaid = complying_status = "review_required"
                    repayment_integrity_reviewed = False
                    loan_start_year = loan_term_years = remaining_term_years = eligible_repayments = ""
                    reviewed_distributable_surplus = div7a_source_note = div7a_review_note = ""
                    if private_company_status == "confirmed_private":
                        transaction_exists_label = st.radio(
                            "Were there any payments, loans or debt forgiveness transactions involving a shareholder or associate during the income year?",
                            ["No", "Yes", "Unsure / review required"],
                            horizontal=True,
                            key="stage2_div7a_transaction_exists",
                        )
                        if transaction_exists_label == "Yes":
                            transaction_type_label = st.radio(
                                "What type of transaction occurred?",
                                [
                                    "Loan",
                                    "Payment / private expense",
                                    "Debt forgiveness",
                                    "Trust / UPE arrangement",
                                    "Indirect / interposed entity arrangement",
                                    "Other / unsure",
                                ],
                                key="stage2_div7a_transaction_type",
                            )
                            transaction_type = {
                                "Loan": "loan",
                                "Payment / private expense": "payment_private_expense",
                                "Debt forgiveness": "debt_forgiveness",
                                "Trust / UPE arrangement": "trust_upe",
                                "Indirect / interposed entity arrangement": "indirect_interposed",
                                "Other / unsure": "other_unsure",
                            }[transaction_type_label]
                            source_account = st.text_input("Relevant source account", key="stage2_div7a_source_account")
                            source_balance = st.text_input("Source balance / amount", key="stage2_div7a_source_balance")
                            if transaction_type == "loan":
                                balance_direction = {
                                    "Shareholder/director owes the company": "shareholder_director_owes_company",
                                    "Company owes shareholder/director": "company_owes_shareholder_director",
                                    "Unsure / review required": "unsure",
                                }[st.radio("Who owes whom?", ["Shareholder/director owes the company", "Company owes shareholder/director", "Unsure / review required"], key="stage2_div7a_direction")]
                                shareholder_status = {
                                    "Confirmed": "confirmed",
                                    "No": "no",
                                    "Review required": "review_required",
                                }[st.radio("Was the borrower a shareholder or an associate of a shareholder?", ["Confirmed", "No", "Review required"], horizontal=True, key="stage2_div7a_shareholder_status")]
                                loan_amount = st.text_input("Original / current-year loan amount", key="stage2_div7a_loan_amount")
                                opening_balance = st.text_input("Opening loan balance", key="stage2_div7a_opening_balance")
                                repayments_before_lodgment = st.text_input("Repayments before lodgment day", key="stage2_div7a_repayments_before")
                                outstanding_at_lodgment = st.text_input("Outstanding balance at lodgment day", key="stage2_div7a_outstanding")
                                fully_repaid = {"Yes": "yes", "No": "no", "Review required": "review_required"}[
                                    st.radio("Was the relevant loan fully repaid before lodgment day?", ["Yes", "No", "Review required"], horizontal=True, key="stage2_div7a_fully_repaid")
                                ]
                                if fully_repaid == "yes":
                                    repayment_integrity_reviewed = st.checkbox("Repayment integrity reviewed", key="stage2_div7a_integrity")
                                elif fully_repaid == "no":
                                    complying_status = {"Confirmed": "confirmed", "No": "no", "Review required": "review_required"}[
                                        st.radio("Was a complying Division 7A loan agreement in place by lodgment day?", ["Confirmed", "No", "Review required"], horizontal=True, key="stage2_div7a_complying")
                                    ]
                                    if complying_status == "confirmed":
                                        loan_start_year = st.text_input("Loan start year", key="stage2_div7a_start_year")
                                        loan_term_years = st.text_input("Loan term years", key="stage2_div7a_term")
                                        remaining_term_years = st.text_input("Remaining term years", key="stage2_div7a_remaining")
                                        eligible_repayments = st.text_input("Actual eligible repayments", key="stage2_div7a_eligible_repayments")
                                    reviewed_distributable_surplus = st.text_input("Reviewed distributable surplus", key="stage2_div7a_surplus")
                            else:
                                st.warning("This branch is review-only in the MVP. No loan/MYR calculation will be performed.")
                                div7a_source_note = st.text_area("Entities involved / supporting document reference", height=70, key="stage2_div7a_source_note")
                        div7a_review_note = st.text_area("Division 7A reviewer note", height=70, key="stage2_div7a_note")
                    else:
                        st.info("Division 7A calculations are not run unless private-company status is confirmed by the reviewer.")

                    reviewed_div7a = {
                        "private_company_status": private_company_status,
                        "transaction_exists": {"No": "no", "Yes": "yes", "Unsure / review required": "unsure"}.get(transaction_exists_label, "unsure"),
                        "transaction_type": transaction_type,
                        "source_account": source_account,
                        "source_balance": source_balance,
                        "balance_direction": balance_direction,
                        "shareholder_or_associate_status": shareholder_status,
                        "loan_amount": loan_amount,
                        "opening_balance": opening_balance,
                        "repayments_before_lodgment": repayments_before_lodgment,
                        "outstanding_at_lodgment": outstanding_at_lodgment,
                        "fully_repaid_before_lodgment": fully_repaid,
                        "repayment_integrity_reviewed": repayment_integrity_reviewed,
                        "complying_loan_status": complying_status,
                        "loan_start_year": loan_start_year,
                        "loan_term_years": loan_term_years,
                        "remaining_term_years": remaining_term_years,
                        "eligible_repayments": eligible_repayments,
                        "reviewed_distributable_surplus": reviewed_distributable_surplus,
                        "review_note": div7a_review_note,
                        "source_note": div7a_source_note,
                        "approved": False,
                    }

                reviewed_tax_depreciation = ""
                tax_depreciation_approved_for_posting = False
                if requested_tables.get("depreciation"):
                    reviewed_tax_depreciation = st.text_input("Reviewed tax depreciation deduction (Item 7F)", key="stage2_tax_dep")
                    tax_depreciation_approved_for_posting = st.checkbox(
                        "Accountant approved this amount for Item 7F posting",
                        disabled=not str(reviewed_tax_depreciation).strip(),
                        key="stage2_tax_dep_approved",
                    )

                hash_ok, hash_errors = verify_scan_sources(scan_result)
                if not hash_ok:
                    blocking_items.extend(hash_errors)
                generation_payload = {
                    "company_profile": company_profile,
                    "document_description": document_description,
                    "client_name": client_name,
                    "ato_policy_year": ato_policy_year,
                    "requested_tables": requested_tables,
                    "reviewer_notes": reviewer_notes,
                    "tax_rate_choice": tax_rate_choice,
                    "base_rate_entity_assessment": base_rate_entity_assessment,
                    "reviewed_tax_losses": reviewed_tax_losses,
                    "reviewed_div7a": reviewed_div7a,
                    "reviewed_tax_depreciation": reviewed_tax_depreciation,
                    "tax_depreciation_approved_for_posting": tax_depreciation_approved_for_posting,
                    "business_profile_industry": business_profile_industry,
                    "company_profile_notes": company_profile_notes,
                    "ato_company_status": ato_company_status,
                }

            st.markdown("<hr>", unsafe_allow_html=True)
            st.markdown("**Generate workpaper**")
            requested_tables = generation_payload.get("requested_tables") or {}
            st.caption(f"Reports: {len(scan_result.get('detected_reports', []))}")
            st.caption(f"Included review areas: {', '.join(OPTIONAL_TABLES[k] for k, v in requested_tables.items() if v) or 'None'}")
            if blocking_items:
                for item in blocking_items:
                    st.error(item)

            if st.button("Generate workpaper from confirmed review", type="primary", use_container_width=True, disabled=bool(blocking_items)):
                file_handles = []
                try:
                    file_handles = open_scan_source_files(scan_result)
                    with st.spinner(T.GENERATING_SPINNER_LABEL):
                        result = run_workpaper_job(
                            extra_files=file_handles,
                            company_profile=generation_payload["company_profile"],
                            document_description=generation_payload["document_description"],
                            client_name=generation_payload["client_name"],
                            ato_policy_year=generation_payload["ato_policy_year"],
                            requested_tables=generation_payload["requested_tables"],
                            reviewer_notes=generation_payload["reviewer_notes"],
                            run_ai_face_check=False,
                            company_tax_rate_category=generation_payload["tax_rate_choice"],
                            base_rate_entity_assessment=generation_payload["base_rate_entity_assessment"],
                            reviewed_tax_losses=generation_payload["reviewed_tax_losses"],
                            reviewed_div7a=generation_payload["reviewed_div7a"],
                            reviewed_tax_depreciation=generation_payload["reviewed_tax_depreciation"],
                            tax_depreciation_approved_for_posting=generation_payload["tax_depreciation_approved_for_posting"],
                            history_owner_id=st.session_state.history_owner_id,
                        )
                finally:
                    for handle in file_handles:
                        handle.close()

                _save_history_metadata(
                    result=result,
                    client_name=generation_payload["client_name"],
                    business_profile_industry=generation_payload["business_profile_industry"],
                    company_profile_notes=generation_payload["company_profile_notes"],
                    company_profile=generation_payload["company_profile"],
                    ato_company_status=generation_payload["ato_company_status"],
                    reviewer_notes=generation_payload["reviewer_notes"],
                    document_description=generation_payload["document_description"],
                    ato_policy_year=generation_payload["ato_policy_year"],
                    uploaded_files=[],
                    ai_provider="None",
                    ai_model="",
                    run_ai_face_check=False,
                    company_tax_rate_category=generation_payload["tax_rate_choice"],
                    base_rate_entity_assessment=generation_payload["base_rate_entity_assessment"],
                    requested_tables=generation_payload["requested_tables"],
                )
                output_path = result.get("output_path")
                st.session_state.current_workpaper_metadata = _load_history_metadata(output_path) if output_path else {}
                st.session_state.job_result = result
                st.session_state.revision_response = None
                if output_path:
                    cleanup_scan(st.session_state.scan_result)
                    st.session_state.scan_result = None
                st.session_state.generator_stage = "result"
                st.rerun()

        elif stage == "result":
            st.markdown('<div class="section-header">3. Generate / result</div>', unsafe_allow_html=True)
            result = st.session_state.job_result or {}
            if result.get("status") == "success":
                st.success(T.SUCCESS_MESSAGE)
                output_path = Path(result["output_path"])
                with open(output_path, "rb") as f:
                    st.download_button(
                        T.DOWNLOAD_BUTTON_LABEL,
                        data=f,
                        file_name=result.get("output_name") or output_path.name,
                        mime=T.DOWNLOAD_MIME,
                        use_container_width=True,
                    )
            else:
                st.error(result.get("error_message") or "Generation failed.")
            if st.button("Start another staged workpaper", use_container_width=True):
                st.session_state.job_result = None
                st.session_state.current_workpaper_metadata = {}
                st.session_state.generator_stage = "upload"
                st.session_state.upload_key_nonce += 1
                st.rerun()

    else:
        pass


# ─────────────────────────────────────────────────────────────────────────────
# RIGHT COLUMN
# ─────────────────────────────────────────────────────────────────────────────
if right is not None:
    with right:
        if st.session_state.view_mode == "library":
            st.markdown('<div class="section-header">Workpaper preview</div>', unsafe_allow_html=True)

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
                    _render_ai_review_audit(selected_history_file)
                    st.markdown("<hr>", unsafe_allow_html=True)
                    st.caption("Use Review & edit to record a reviewer-controlled workbook revision.")
                else:
                    st.warning("Selected history file no longer exists.")
            else:
                st.info("Select a previous workpaper from the left panel.")

        elif st.session_state.view_mode == "editor":
            editor_path_raw = st.session_state.get("editor_workpaper_path")
            editor_path = Path(editor_path_raw) if editor_path_raw else None
            if not editor_path or not editor_path.exists():
                st.info("Open Main page, choose a workpaper and select Open in Review & edit.")
            else:
                try:
                    workbook_sheets = load_workbook_canvas(editor_path)
                except Exception as exc:
                    st.error(f"Could not open this workbook for browser editing: {exc}")
                    workbook_sheets = []

                if not workbook_sheets:
                    st.warning("This workbook has no visible worksheets to edit.")
                else:
                    edits = render_workbook_canvas(
                        workbook_sheets,
                        key=f"workbook_canvas_{editor_path.name}",
                    )
                    footer_left, footer_right = st.columns([1, 1])
                    with footer_left:
                        st.caption(f"{len(edits)} unsaved cell change(s) · all visible cells are editable")
                    with footer_right:
                        if st.button("Save a new Excel revision", type="primary", use_container_width=True):
                            try:
                                revision_path, audit_path, change_count = export_manual_workbook_revision(
                                    source_workbook=editor_path,
                                    sheets=workbook_sheets,
                                    edits=edits,
                                )
                                _save_revision_metadata(
                                    source_workpaper=editor_path,
                                    revision_workpaper=revision_path,
                                    revision_audit_path=audit_path,
                                )
                            except WorkbookCanvasError as exc:
                                st.error(str(exc))
                            except Exception as exc:
                                st.error(f"Could not save the manual workbook revision: {exc}")
                            else:
                                st.session_state.revision_response = {
                                    "path": str(revision_path),
                                    "audit_path": str(audit_path),
                                    "change_count": change_count,
                                }
                                st.success(f"Saved {change_count} cell change(s) to a new workbook. Original unchanged.")
                    revision_response = st.session_state.get("revision_response") or {}
                    revision_path_raw = revision_response.get("path")
                    if revision_path_raw and Path(revision_path_raw).exists():
                        revision_path = Path(revision_path_raw)
                        _download_workbook_button(
                            path=revision_path,
                            label="Download revised Excel",
                            file_name=revision_path.name,
                            key=f"download_revision_{revision_path.name}",
                        )
