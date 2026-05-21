# frontend/app.py
"""
ICGTAX Tax Workpaper Generator — Streamlit demo UI.

Run from project root:
    streamlit run frontend/app.py

Responsibilities:
- Upload files
- Collect client profile + document description
- Call job_runner.run_workpaper_job()
- Show results + download button
- Post-output question / revision box

All tax logic stays in v1/.
All backend execution is in job_runner.py.
All text labels are in ui_text.py.
"""
from __future__ import annotations

from pathlib import Path

import streamlit as st

# ── Path setup (so job_runner can find v1) ────────────────────────────────────
import sys
FRONTEND_DIR = Path(__file__).resolve().parent
ROOT_DIR     = FRONTEND_DIR.parent
sys.path.insert(0, str(FRONTEND_DIR))

import ui_text as T
from job_runner import run_workpaper_job

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title=T.APP_TITLE,
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Minimal CSS: clean, professional, not flashy ──────────────────────────────
st.markdown("""
<style>
    /* Font */
    @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap');

    html, body, [class*="css"] {
        font-family: 'IBM Plex Sans', sans-serif;
    }

    /* Remove default top padding */
    .block-container { padding-top: 2rem; }

    /* Section headers */
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

    /* App title */
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

    /* Result card */
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
    .result-card-warning {
        border-left: 4px solid #f39c12;
    }
    .result-card-error {
        border-left: 4px solid #e74c3c;
    }

    /* Detected badge */
    .badge {
        display: inline-block;
        font-size: 0.75rem;
        font-weight: 500;
        padding: 2px 8px;
        border-radius: 4px;
        margin-right: 6px;
        margin-bottom: 4px;
    }
    .badge-green { background: #d4edda; color: #155724; }
    .badge-grey  { background: #e9ecef; color: #6c757d; }

    /* Review count */
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

    /* Divider */
    hr { border: none; border-top: 1px solid #eee; margin: 1.5rem 0; }

    /* Admin section */
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
</style>
""", unsafe_allow_html=True)


# ── Session state init ────────────────────────────────────────────────────────
if "job_result" not in st.session_state:
    st.session_state.job_result = None
if "revision_response" not in st.session_state:
    st.session_state.revision_response = None


# ═══════════════════════════════════════════════════════════════════════════════
# Layout: two columns — left = inputs, right = output
# ═══════════════════════════════════════════════════════════════════════════════
left, right = st.columns([1, 1], gap="large")


# ─────────────────────────────────────────────────────────────────────────────
# LEFT COLUMN — Inputs
# ─────────────────────────────────────────────────────────────────────────────
with left:
    st.markdown(f'<div class="app-title">{T.APP_TITLE}</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="app-subtitle">{T.APP_SUBTITLE}</div>', unsafe_allow_html=True)

    # ── Client name ───────────────────────────────────────────────────────────
    client_name = st.text_input(
        T.CLIENT_NAME_LABEL,
        placeholder=T.CLIENT_NAME_PLACEHOLDER,
        help=T.CLIENT_NAME_HELP,
    )

    # ── Section 1: Files ──────────────────────────────────────────────────────
    st.markdown(f'<div class="section-header">{T.SECTION_FILES}</div>', unsafe_allow_html=True)

    upload_mode = st.radio(
        T.UPLOAD_MODE_LABEL,
        options=[T.UPLOAD_MODE_COMBINED, T.UPLOAD_MODE_SEPARATE],
        horizontal=True,
        label_visibility="collapsed",
    )

    combined_file = None
    pl_file       = None
    bs_file       = None

    if upload_mode == T.UPLOAD_MODE_COMBINED:
        combined_file = st.file_uploader(
            T.UPLOAD_COMBINED_LABEL,
            type=T.UPLOAD_FILE_TYPES,
            help=T.UPLOAD_COMBINED_HELP,
            accept_multiple_files=True,
        )
    else:
        col_pl, col_bs = st.columns(2)
        with col_pl:
            pl_file = st.file_uploader(
                T.UPLOAD_PL_LABEL,
                type=T.UPLOAD_FILE_TYPES,
                help=T.UPLOAD_PL_HELP,
                accept_multiple_files=True,
            )
        with col_bs:
            bs_file = st.file_uploader(
                T.UPLOAD_BS_LABEL,
                type=T.UPLOAD_FILE_TYPES,
                help=T.UPLOAD_BS_HELP,
                accept_multiple_files=True,
            )

    # ── Section 2: Client profile ─────────────────────────────────────────────
    st.markdown(f'<div class="section-header">{T.SECTION_PROFILE}</div>', unsafe_allow_html=True)

    company_type = st.selectbox(
        T.COMPANY_TYPE_LABEL,
        options=T.COMPANY_TYPES,
        label_visibility="visible",
    )

    company_profile_notes = st.text_area(
        T.COMPANY_PROFILE_LABEL,
        placeholder=T.COMPANY_PROFILE_PLACEHOLDER,
        help=T.COMPANY_PROFILE_HELP,
        height=90,
    )

    company_profile = f"{company_type}. {company_profile_notes}".strip(". ")

    # ── Section 3: Document description ──────────────────────────────────────
    st.markdown(f'<div class="section-header">{T.SECTION_DESCRIBE}</div>', unsafe_allow_html=True)

    document_description = st.text_area(
        T.DOC_DESCRIPTION_LABEL,
        placeholder=T.DOC_DESCRIPTION_PLACEHOLDER,
        help=T.DOC_DESCRIPTION_HELP,
        height=90,
        label_visibility="visible",
    )

    # ── Generate button ───────────────────────────────────────────────────────
    st.markdown("")
    generate_clicked = st.button(
        T.GENERATE_BUTTON_LABEL,
        type="primary",
        use_container_width=True,
    )

    if generate_clicked:
        # Validate inputs
        valid = True
        if upload_mode == T.UPLOAD_MODE_COMBINED and combined_file:
            st.error(T.ERROR_COMBINED_MISSING)
            valid = False
        elif upload_mode == T.UPLOAD_MODE_SEPARATE and (pl_file is None or bs_file):
            st.error(T.ERROR_SEPARATE_MISSING)
            valid = False

        if valid:
            with st.spinner(T.GENERATING_SPINNER_LABEL):
                result = run_workpaper_job(
                    pl_file=pl_file,
                    bs_file=bs_file,
                    combined_file=combined_file,
                    company_profile=company_profile,
                    document_description=document_description,
                    client_name=client_name,
                )
            st.session_state.job_result      = result
            st.session_state.revision_response = None
            st.rerun()

    # ── Admin section (collapsed by default) ──────────────────────────────────
    with st.expander("Admin: Update ATO metadata", expanded=False):
        st.markdown(f'<div class="admin-section"><div class="admin-label">Admin only</div><p style="font-size:0.85rem;color:#6b5c3a;margin-top:0.5rem;">{T.ADMIN_WARNING}</p></div>', unsafe_allow_html=True)
        if st.button(T.ADMIN_BUTTON):
            st.info(T.ADMIN_NOT_IMPL)


# ─────────────────────────────────────────────────────────────────────────────
# RIGHT COLUMN — Results
# ─────────────────────────────────────────────────────────────────────────────
with right:
    result = st.session_state.job_result

    if result is None:
        # Empty state
        st.markdown("""
        <div style="margin-top:3rem;color:#bbb;text-align:center;">
            <div style="font-size:2.5rem;margin-bottom:0.5rem;">📄</div>
            <div style="font-size:0.9rem;">Upload files and click <strong>Generate workpaper</strong></div>
        </div>
        """, unsafe_allow_html=True)

    elif result["status"] == "error":
        st.markdown(f'<div class="section-header">{T.SECTION_RESULT}</div>', unsafe_allow_html=True)
        st.error(T.ERROR_PIPELINE)
        with st.expander("Error details"):
            st.code(result.get("error_message", "Unknown error"), language="python")

    else:
        # ── Success ───────────────────────────────────────────────────────────
        st.markdown(f'<div class="section-header">{T.SECTION_RESULT}</div>', unsafe_allow_html=True)

        st.markdown(f"""
        <div class="result-card result-card-success">
            <div style="font-weight:600;font-size:1rem;color:#1a1a2e;margin-bottom:0.6rem;">
                ✓ &nbsp;{T.SUCCESS_HEADER}
            </div>
            <div style="font-size:0.82rem;color:#555;">
                Output: <code style="font-family:'IBM Plex Mono',monospace;">{result["output_name"]}</code>
            </div>
        </div>
        """, unsafe_allow_html=True)

        # Download button
        output_path = result.get("output_path")
        if output_path and Path(output_path).exists():
            with open(output_path, "rb") as f:
                st.download_button(
                    label=T.DOWNLOAD_BUTTON,
                    data=f.read(),
                    file_name=result["output_name"],
                    mime=T.DOWNLOAD_MIME,
                    use_container_width=True,
                )

        st.markdown("<hr>", unsafe_allow_html=True)

        # ── Three metric columns ──────────────────────────────────────────────
        col_det, col_rev, col_warn = st.columns(3)

        with col_det:
            st.markdown(f"**{T.DETECTED_HEADER}**")
            detected = result.get("detected", {})
            for name, found in detected.items():
                badge_cls = "badge-green" if found else "badge-grey"
                icon      = "✓" if found else "–"
                st.markdown(
                    f'<span class="badge {badge_cls}">{icon} {name}</span>',
                    unsafe_allow_html=True,
                )

        with col_rev:
            review_count = result.get("review_count", 0)
            colour = "#e67e22" if review_count > 0 else "#2ecc71"
            st.markdown(f"**{T.REVIEW_HEADER}**")
            st.markdown(
                f'<div class="review-count" style="color:{colour};">{review_count}</div>'
                f'<div class="review-label">items need review</div>',
                unsafe_allow_html=True,
            )
            if review_count > 0:
                st.caption(T.REVIEW_HELP)

        with col_warn:
            warnings = result.get("warnings", [])
            st.markdown(f"**{T.WARNINGS_HEADER}**")
            if warnings:
                for w in warnings:
                    st.markdown(
                        f'<span class="badge badge-warning" style="background:#fff3cd;color:#856404;">'
                        f'⚠ {w}</span>',
                        unsafe_allow_html=True,
                    )
            else:
                st.markdown(
                    f'<span class="badge badge-green">✓ {T.WARNINGS_NONE}</span>',
                    unsafe_allow_html=True,
                )

        st.markdown("<hr>", unsafe_allow_html=True)

        # ── Post-output: question / revision box ──────────────────────────────
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
                # ── Route the question ─────────────────────────────────────
                # For now: look up stored label reasons from the workpaper
                # Later: connect to Claude/GPT API for richer responses
                response = _handle_revision_question(revision_text, result)
                st.session_state.revision_response = response
                st.rerun()

        if st.session_state.revision_response:
            st.markdown("""
            <div style="background:#f0f4ff;border:1px solid #c8d6f5;border-radius:6px;
                        padding:1rem 1.2rem;margin-top:0.8rem;font-size:0.88rem;">
            """, unsafe_allow_html=True)
            st.markdown(st.session_state.revision_response)
            st.markdown("</div>", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# Revision question handler (local lookup — no API needed for demo)
# ─────────────────────────────────────────────────────────────────────────────

def _handle_revision_question(question: str, result: dict) -> str:
    """
    Simple keyword-based explanation lookup.
    Matches common questions to stored label reasons from itr_rules.py.

    Later: replace with Claude/GPT API call using the question + workpaper context.
    """
    q = question.lower()

    explanations: list[tuple[list[str], str]] = [
        (
            ["depreciation", "amortis", "7w", "add back"],
            "**Why is depreciation / amortisation added back (7W)?**\n\n"
            "Accounting standards require you to spread the cost of assets over their useful life "
            "as depreciation or amortisation. However, the ATO does not accept accounting depreciation "
            "as a tax deduction. Instead, the ATO has its own rules under Division 40 (decline in value) "
            "and Division 43 (capital works). So accounting depreciation is added back at **7W** "
            "(non-deductible expenses), and tax depreciation is claimed separately at **7F** or **7I**.\n\n"
            "*Check: a tax depreciation schedule should be entered in TAX_ADJUSTMENTS['subtract_7F'].*"
        ),
        (
            ["cogs", "cost of goods", "cost of sales", "6a"],
            "**Why is Cost of Goods Sold / Cost of Sales under 6A?**\n\n"
            "Item 6A on the company tax return covers 'Cost of sales'. This is a standard mapping "
            "for direct costs of revenue — purchases, raw materials, direct labour, and similar items. "
            "The label is applied by the account-name matching rule in `itr_rules.py`.\n\n"
            "*If this item is not a direct cost of sales, flag it for manual review.*"
        ),
        (
            ["superannuation", "super", "7x", "prior year"],
            "**Why is superannuation split across 7W and 7X?**\n\n"
            "Superannuation is deductible only when actually paid to the fund, not when accrued. "
            "So this year's accrued (unpaid) super is **added back at 7W** (non-deductible), "
            "and last year's accrued super that was actually paid this year is **deducted at 7X** "
            "(other deductible expenses). Both amounts must be confirmed from payment records.\n\n"
            "*Enter confirmed amounts in TAX_ADJUSTMENTS in config.py.*"
        ),
        (
            ["r&d", "research", "7d", "offset", "43.5"],
            "**Why is R&D expenditure added back at 7D?**\n\n"
            "R&D costs that were expensed in the accounts are added back at **7D** so they can be "
            "claimed through the R&D Tax Incentive Schedule instead. A standard deduction saves 25% tax, "
            "but the R&D offset is 43.5% (refundable for companies with turnover < $20M) — "
            "a better outcome for eligible companies. The add-back at 7D is matched by an "
            "R&D offset credit entered separately.\n\n"
            "*Confirm R&D eligibility with a registered R&D tax adviser.*"
        ),
        (
            ["entertainment", "meal", "7w", "non-deductible"],
            "**Why is entertainment non-deductible (7W)?**\n\n"
            "Under the ITAA 1997, entertainment expenses — including meals, drinks, and functions — "
            "are generally **not deductible** for income tax purposes and are also subject to FBT "
            "if provided to employees. The account has been flagged as review-required because "
            "the exact nature of the expense needs to be confirmed.\n\n"
            "*Confirm whether this is genuine entertainment or a deductible meal allowance.*"
        ),
        (
            ["6c", "consulting", "revenue", "income"],
            "**Why is consulting/service revenue under 6C?**\n\n"
            "Item 6C on the tax return covers 'gross payments subject to no withholding' — "
            "effectively the main business income for service and consulting companies. "
            "It maps from account names matching 'sales', 'revenue', 'consulting income', etc.\n\n"
            "*If this company receives income subject to foreign withholding or ABN-not-quoted "
            "withholding, those amounts should be under 6A or 6B instead.*"
        ),
        (
            ["provision", "annual leave", "long service"],
            "**Why are leave provisions flagged for review?**\n\n"
            "Leave provisions (annual leave, long service leave) are expensed in the accounts "
            "as employees accrue leave, but the ATO only allows a deduction when the leave is "
            "actually taken and paid. The net **increase** in provision should be **added back (7W)** "
            "and the net **decrease** (leave paid out) should be **deducted (7X)**.\n\n"
            "*Confirm opening and closing provision balances from the Balance Sheet.*"
        ),
    ]

    for keywords, explanation in explanations:
        if any(kw in q for kw in keywords):
            return explanation

    return (
        "**Question received.**\n\n"
        f"> *{question.strip()}*\n\n"
        "This question has been noted. For full explanations, check:\n"
        "- The **Review Note** column in the workpaper (ITR Ref sheet)\n"
        "- The **Label Reason** field stored in each labelled row\n"
        "- `itr_rules.py` → `FINANCIAL_LABEL_RULES` for the matching logic\n\n"
        "*Claude/GPT API integration coming soon for dynamic explanations.*"
    )