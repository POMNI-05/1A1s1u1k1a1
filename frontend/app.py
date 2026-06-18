# frontend/app.py
"""
ICGTAX Tax Workpaper Generator — Streamlit UI.

Run from project root: streamlit run frontend/app.py

Design:
- One upload box only -> User can upload one combined workbook or multiple Excel files.
- Frontend does not decide which file is P&L or Balance Sheet.
- job_runner copies files into v1/data/.
- v1/main.py runs exactly like the working backend test.
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

# ── Path setup ────────────────────────────────────────────────────────────────
FRONTEND_DIR = Path(__file__).resolve().parent

if str(FRONTEND_DIR) not in sys.path:
    sys.path.insert(0, str(FRONTEND_DIR))

import ui_text as T
from job_runner import run_workpaper_job

# ─────────────────────────────────────────────────────────────────────────────
# Revision question handler
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
    "psi": "PSI / personal services income review table",
}


def _handle_revision_question(question: str, result: dict) -> str:
    q = question.lower()

    explanations: list[tuple[list[str], str]] = [
        (
            ["depreciation", "amortis", "7w", "add back"],
            "**Why is depreciation / amortisation added back (7W)?**\n\n"
            "Accounting depreciation is not usually deductible as-is for tax. "
            "The workpaper adds it back for review/tax treatment, then tax depreciation "
            "should be claimed separately where applicable.\n\n"
            "*Check the tax depreciation schedule before finalising.*"
        ),
        (
            ["cogs", "cost of goods", "cost of sales", "6a"],
            "**Why is Cost of Goods Sold / Cost of Sales under 6A?**\n\n"
            "Cost of sales normally maps to the company tax return cost-of-sales label. "
            "This covers direct costs connected to trading revenue.\n\n"
            "*If the account is not a direct cost of sales, flag it for review.*"
        ),
        (
            ["superannuation", "super", "7x", "prior year"],
            "**Why can superannuation need review?**\n\n"
            "Superannuation deductibility depends on payment timing. Accrued but unpaid super "
            "can need adjustment, while prior-year accrued super paid this year can be deductible.\n\n"
            "*Check actual payment records and opening/closing accruals.*"
        ),
        (
            ["r&d", "research", "7d", "offset", "43.5"],
            "**Why is R&D expenditure added back at 7D?**\n\n"
            "Eligible R&D expenditure is generally removed from ordinary deductions and dealt "
            "with through the R&D Tax Incentive calculation. The add-back prevents double-counting.\n\n"
            "*Confirm R&D eligibility and amounts with the R&D schedule/adviser.*"
        ),
        (
            ["entertainment", "meal", "7w", "non-deductible"],
            "**Why is entertainment flagged for review?**\n\n"
            "Entertainment expenses can be non-deductible or subject to FBT depending on the facts. "
            "The exact nature of the expense should be reviewed before finalising treatment.\n\n"
            "*Confirm whether it is entertainment, staff meal, travel meal, or client function.*"
        ),
        (
            ["6c", "consulting", "revenue", "income"],
            "**Why is consulting/service revenue mapped this way?**\n\n"
            "For many service companies, ordinary business income maps to the main income label. "
            "The exact label depends on the nature of income and withholding status.\n\n"
            "*Check whether any income is subject to withholding or should be separately disclosed.*"
        ),
        (
            ["provision", "annual leave", "long service"],
            "**Why are leave provisions flagged for review?**\n\n"
            "Accounting leave provisions may not equal deductible tax amounts. Tax treatment often "
            "depends on whether leave has actually been paid or merely accrued.\n\n"
            "*Confirm opening and closing provision balances from the Balance Sheet.*"
        ),
    ]

    for keywords, explanation in explanations:
        if any(keyword in q for keyword in keywords):
            return explanation

    return (
        "**Question received.**\n\n"
        f"> *{question.strip()}*\n\n"
        "This question has been noted. For full explanation, check:\n"
        "- the **Review note** column in the workpaper\n"
        "- the **ITR Ref** side labels\n"
        "- backend mapping rules / metadata\n\n"
        "*Dynamic Claude/GPT explanation can be connected later.*"
    )


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

    .review-count {
        font-size: 2rem;
        font-weight: 600;
        color: #1a1a2e;
        line-height: 1;
    }

    .review-label {
        font-size: 0.8rem;
        color: #888;
        margin-top: 2px;
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


# ── Layout ────────────────────────────────────────────────────────────────────
left, right = st.columns([1, 1], gap="large")


# ─────────────────────────────────────────────────────────────────────────────
# LEFT COLUMN
# ─────────────────────────────────────────────────────────────────────────────
with left:
    st.markdown(f'<div class="app-title">{T.APP_TITLE}</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="app-subtitle">{T.APP_SUBTITLE}</div>', unsafe_allow_html=True)

    client_name = st.text_input(
        T.CLIENT_NAME_LABEL,
        placeholder=T.CLIENT_NAME_PLACEHOLDER,
        help=T.CLIENT_NAME_HELP,
    )

    # ── Upload files ─────────────────────────────────────────────────────────
    st.markdown(f'<div class="section-header">{T.SECTION_FILES}</div>', unsafe_allow_html=True)

    uploaded_files = st.file_uploader(
        T.UPLOAD_FILES_LABEL,
        type=T.UPLOAD_FILE_TYPES,
        accept_multiple_files=True,
        key="excel_files_uploader",
        help=T.UPLOAD_FILES_HELP,
    )

    if uploaded_files:
        st.caption(f"{len(uploaded_files)} {T.UPLOAD_SELECTED_PREFIX}")
        for uploaded_file in uploaded_files:
            st.caption(f"• {uploaded_file.name}")

    # ── Client profile ───────────────────────────────────────────────────────
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

    # ── Document description ─────────────────────────────────────────────────
    st.markdown(f'<div class="section-header">{T.SECTION_DESCRIBE}</div>', unsafe_allow_html=True)

    ato_policy_year = st.selectbox(
        "ATO / ITR policy year",
        options=ATO_POLICY_YEARS,
        index=0,
        help="This will be passed to the backend so itr_rules / ato_policy can switch rule sets.",
    )

    st.caption("Optional review tables to include / prepare")

    requested_tables: dict[str, bool] = {}

    table_col_1, table_col_2 = st.columns(2)

    for idx, (table_key, table_label) in enumerate(OPTIONAL_TABLES.items()):
        target_col = table_col_1 if idx % 2 == 0 else table_col_2
        with target_col:
            requested_tables[table_key] = st.checkbox(
                table_label,
                value=table_key in {
                    "carry_forward_losses",
                    "rd_tax_incentive",
                    "depreciation",
                    "superannuation",
                },
                key=f"table_{table_key}",
            )

    reviewer_notes = st.text_area(
        "Reviewer instructions / special facts",
        placeholder=(
            "Example: Prior-year tax losses exist; R&D claim expected; "
            "director loan may need Div 7A review; check consulting income classification."
        ),
        height=80,
    )

    run_ai_face_check = st.checkbox(
        "Run Gemini face-check after workbook generation",
        value=True,
        help=(
            "Sends user inputs + a workbook summary to Gemini to identify obvious issues. "
            "It should not replace accountant review."
        ),
    )

    document_description = st.text_area(
        T.DOC_DESCRIPTION_LABEL,
        placeholder=T.DOC_DESCRIPTION_PLACEHOLDER,
        help=T.DOC_DESCRIPTION_HELP,
        height=90,
    )

    # ── Generate ─────────────────────────────────────────────────────────────
    st.markdown("")

    generate_clicked = st.button(
        T.GENERATE_BUTTON_LABEL,
        type="primary",
        use_container_width=True,
    )

    if generate_clicked:
        if not uploaded_files:
            st.error(T.ERROR_NO_FILES)
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
                )
            st.session_state.job_result = result
            st.session_state.revision_response = None
            st.rerun()

    # ── Admin ────────────────────────────────────────────────────────────────
    with st.expander(T.ADMIN_HEADER, expanded=False):
        st.markdown(
            f"""
            <div class="admin-section">
                <div class="admin-label">Admin only</div>
                <p style="font-size:0.85rem;color:#6b5c3a;margin-top:0.5rem;">
                    {T.ADMIN_WARNING}
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        if st.button(T.ADMIN_BUTTON):
            st.info(T.ADMIN_NOT_IMPL)


# ─────────────────────────────────────────────────────────────────────────────
# RIGHT COLUMN
# ─────────────────────────────────────────────────────────────────────────────
with right:
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

        with st.expander(T.SECTION_DEBUG, expanded=False):
            st.markdown(f"**{T.DEBUG_BACKEND_COMMAND}**")
            st.code(result.get("backend_command", ""), language="bash")

            st.markdown(f"**{T.DEBUG_FRONTEND_UPLOAD_DIR}**")
            st.code("\n".join(result.get("frontend_upload_paths", [])), language="text")

            st.markdown(f"**{T.DEBUG_BACKEND_DATA_DIR}**")
            st.code("\n".join(result.get("backend_data_paths", [])), language="text")

            st.markdown(f"**{T.DEBUG_BACKEND_LOG}**")
            st.code(result.get("backend_log", ""), language="text")

    else:
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
            with open(output_path, "rb") as f:
                st.download_button(
                    label=T.DOWNLOAD_BUTTON,
                    data=f.read(),
                    file_name=result.get("output_name", "workpaper.xlsx"),
                    mime=T.DOWNLOAD_MIME,
                    use_container_width=True,
                )
        else:
            st.warning(T.ERROR_OUTPUT_MISSING)

        st.markdown("<hr>", unsafe_allow_html=True)

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

        st.markdown("<hr>", unsafe_allow_html=True)

        # ── Revision / question box ──────────────────────────────────────────
        st.markdown(f'<div class="section-header">{T.SECTION_REVISE}</div>', unsafe_allow_html=True)

        revision_text = st.text_area(
            T.REVISE_LABEL,
            placeholder=T.REVISE_PLACEHOLDER,
            help=T.REVISE_HELP,
            height=110,
            label_visibility="collapsed",
        )

        if st.button(T.REVISE_BUTTON, use_container_width=True):
            if not revision_text.strip():
                st.warning("Please enter a question or revision request.")
            else:
                st.session_state.revision_response = _handle_revision_question(
                    revision_text,
                    result,
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