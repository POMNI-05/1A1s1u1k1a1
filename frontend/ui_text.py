# frontend/ui_text.py
"""
All display strings, help text, and labels for the Streamlit UI.

Keep all text here so app.py stays clean and text is easy to update.
"""

APP_TITLE    = "Tax Workpaper Generator"
APP_SUBTITLE = "ICGTAX Partners · Automated Tax Reconciliation"

# ── Section headers ────────────────────────────────────────────────────────────
SECTION_FILES    = "1  Upload files"
SECTION_PROFILE  = "2  Client profile"
SECTION_DESCRIBE = "3  Document description"
SECTION_RESULT   = "Result"
SECTION_REVISE   = "Questions & revision requests"

# ── File upload ────────────────────────────────────────────────────────────────
UPLOAD_MODE_LABEL   = "How are your files organised?"
UPLOAD_MODE_COMBINED = "One combined workbook (P&L + BS in same file)"
UPLOAD_MODE_SEPARATE = "Separate P&L and Balance Sheet files"

UPLOAD_COMBINED_LABEL = "Upload combined workbook"
UPLOAD_PL_LABEL       = "Upload Profit & Loss"
UPLOAD_BS_LABEL       = "Upload Balance Sheet"
UPLOAD_FILE_TYPES     = ["xlsx", "xls"]

UPLOAD_COMBINED_HELP = "A single Excel file containing both P&L and Balance Sheet as separate sheets."
UPLOAD_PL_HELP       = "Xero P&L export (.xlsx). Usually 'Profit and Loss' sheet."
UPLOAD_BS_HELP       = "Xero Balance Sheet export (.xlsx). Usually 'Balance Sheet' sheet."

# ── Client name ────────────────────────────────────────────────────────────────
CLIENT_NAME_LABEL       = "Client / engagement name"
CLIENT_NAME_PLACEHOLDER = "e.g. Smith Holdings Pty Ltd FY2025"
CLIENT_NAME_HELP        = "Used in the output filename. Optional."

# ── Company profile prompt ─────────────────────────────────────────────────────
COMPANY_TYPE_LABEL = "Company type"
COMPANY_TYPES = [
    "Service company",
    "Product / trading company",
    "Tech / software company (possible R&D)",
    "Investment / holding company",
    "Property company",
    "Other",
]

COMPANY_PROFILE_LABEL       = "Additional client notes"
COMPANY_PROFILE_PLACEHOLDER = (
    "e.g. Small service company, sole director, no inventory. "
    "Has R&D Tax Incentive claim. "
    "Related-party loans to be reviewed."
)
COMPANY_PROFILE_HELP = (
    "Used to prioritise review notes and highlight relevant items. "
    "Does not change tax calculations."
)

# ── Document description prompt ────────────────────────────────────────────────
DOC_DESCRIPTION_LABEL       = "What are these files?"
DOC_DESCRIPTION_PLACEHOLDER = (
    "e.g. FY2025 Xero export. P&L has two comparison periods (FY2024 and FY2025). "
    "Tax depreciation schedule not included — will need to be entered manually."
)
DOC_DESCRIPTION_HELP = (
    "Helps explain the input files. "
    "Useful for audit trail and edge-case detection."
)

# ── Generate button ────────────────────────────────────────────────────────────
GENERATE_BUTTON_LABEL    = "Generate workpaper"
GENERATING_SPINNER_LABEL = "Running pipeline…"

# ── Result display ─────────────────────────────────────────────────────────────
SUCCESS_HEADER  = "Workpaper generated"
DOWNLOAD_BUTTON = "Download Excel workpaper"
DOWNLOAD_MIME   = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

DETECTED_HEADER  = "Detected reports"
REVIEW_HEADER    = "Review items"
WARNINGS_HEADER  = "Balance sheet checks"

REVIEW_NONE    = "No medium/low confidence items."
WARNINGS_NONE  = "All balance sheet checks passed."

REVIEW_HELP = (
    "Medium and low confidence labels require accountant review before signing off. "
    "These appear in the ITR Ref column of the workpaper."
)

# ── Revision / question box ────────────────────────────────────────────────────
REVISE_LABEL       = "Ask a question or request a revision"
REVISE_PLACEHOLDER = (
    "e.g. Why is depreciation added back?\n"
    "Why is COGS under 6A?\n"
    "Mark entertainment as review required.\n"
    "Explain the R&D mapping."
)
REVISE_HELP = (
    "This does not automatically change the workpaper. "
    "Use it to get explanations or flag items for the next regeneration."
)
REVISE_BUTTON = "Submit question"

# ── Admin ──────────────────────────────────────────────────────────────────────
ADMIN_HEADER        = "Admin: Update ATO metadata"
ADMIN_WARNING       = (
    "This updates ITR labels and tax rates for a new income year. "
    "Changes must be reviewed before applying. "
    "Do not use during an active engagement."
)
ADMIN_BUTTON        = "Open ATO metadata editor"
ADMIN_NOT_IMPL      = "ATO metadata editor coming soon. Edit itr_metadata.py and itr_rules.py directly for now."

# ── Error messages ─────────────────────────────────────────────────────────────
ERROR_NO_FILES   = "Please upload at least one file before generating."
ERROR_PIPELINE   = "Pipeline error. See details below."
ERROR_COMBINED_MISSING = "Please upload a combined workbook."
ERROR_SEPARATE_MISSING = "Please upload both P&L and Balance Sheet files."