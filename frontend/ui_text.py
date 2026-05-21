# frontend/ui_text.py
"""
All display strings, help text, and labels for the Streamlit UI.

Keep display text here so app.py stays clean.
"""

APP_TITLE = "Tax Workpaper Generator"
APP_SUBTITLE = "ICGTAX Partners · Automated Tax Reconciliation"

# ── Section headers ───────────────────────────────────────────────────────────
SECTION_FILES = "1  Upload files"
SECTION_PROFILE = "2  Client profile"
SECTION_DESCRIBE = "3  Document description"
SECTION_RESULT = "Result"
SECTION_REVISE = "Questions & revision requests"
SECTION_DEBUG = "Run details"

# ── File upload ───────────────────────────────────────────────────────────────
UPLOAD_FILE_TYPES = ["xlsx", "xls", "xlsm"]

UPLOAD_FILES_LABEL = "Upload Excel workbook(s)"
UPLOAD_FILES_HELP = (
    "Upload one combined workbook, or upload multiple Excel files. "
    "The backend will copy these into v1/data and automatically detect "
    "Profit & Loss and Balance Sheet sheets."
)

UPLOAD_SELECTED_PREFIX = "file(s) selected"
UPLOAD_USED_HEADER = "Uploaded files used"

# ── Client name ───────────────────────────────────────────────────────────────
CLIENT_NAME_LABEL = "Client / engagement name"
CLIENT_NAME_PLACEHOLDER = "e.g. Smith Holdings Pty Ltd FY2025"
CLIENT_NAME_HELP = "Used in the output filename. Optional."

# ── Company profile prompt ────────────────────────────────────────────────────
COMPANY_TYPE_LABEL = "Company type"
COMPANY_TYPES = [
    "Service company",
    "Product / trading company",
    "Tech / software company (possible R&D)",
    "Investment / holding company",
    "Property company",
    "Other",
]

COMPANY_PROFILE_LABEL = "Additional client notes"
COMPANY_PROFILE_PLACEHOLDER = (
    "e.g. Small service company, sole director, no inventory. "
    "Has R&D Tax Incentive claim. "
    "Related-party loans to be reviewed."
)
COMPANY_PROFILE_HELP = (
    "Stored for audit trail / future prompt context. "
    "Does not directly change tax calculations yet."
)

# ── Document description prompt ───────────────────────────────────────────────
DOC_DESCRIPTION_LABEL = "What are these files?"
DOC_DESCRIPTION_PLACEHOLDER = (
    "e.g. FY2025 Xero export. Combined workbook contains P&L and Balance Sheet. "
    "Tax depreciation schedule not included."
)
DOC_DESCRIPTION_HELP = (
    "Helps explain the input files. Useful for audit trail and edge-case detection."
)

# ── Generate button ───────────────────────────────────────────────────────────
GENERATE_BUTTON_LABEL = "Generate workpaper"
GENERATING_SPINNER_LABEL = "Running backend pipeline…"

# ── Result display ────────────────────────────────────────────────────────────
SUCCESS_HEADER = "Workpaper generated"
DOWNLOAD_BUTTON = "Download Excel workpaper"
DOWNLOAD_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

DETECTED_HEADER = "Detected reports"
REVIEW_HEADER = "Review items"
WARNINGS_HEADER = "Backend warnings"

REVIEW_NONE = "No medium/low confidence items returned."
WARNINGS_NONE = "No backend warnings returned."

REVIEW_HELP = (
    "Medium and low confidence labels require accountant review before signing off. "
    "These appear in the ITR Ref / Review note columns of the workpaper."
)

# ── Revision / question box ───────────────────────────────────────────────────
REVISE_LABEL = "Ask a question or request a revision"
REVISE_PLACEHOLDER = (
    "e.g. Why is depreciation added back?\n"
    "Why is COGS under 6A?\n"
    "Mark entertainment as review required.\n"
    "Explain the R&D mapping."
)
REVISE_HELP = (
    "This does not automatically change the workpaper. "
    "Use it to get explanations or flag items for next regeneration."
)
REVISE_BUTTON = "Submit question"

# ── Admin ─────────────────────────────────────────────────────────────────────
ADMIN_HEADER = "Admin: Update ATO metadata"
ADMIN_WARNING = (
    "This updates ITR labels and tax rates for a new income year. "
    "Changes must be reviewed before applying. "
    "Do not use during an active engagement."
)
ADMIN_BUTTON = "Open ATO metadata editor"
ADMIN_NOT_IMPL = "ATO metadata editor coming soon. Edit itr_metadata.py and itr_rules.py directly for now."

# ── Errors ────────────────────────────────────────────────────────────────────
ERROR_NO_FILES = "Please upload at least one Excel workbook before generating."
ERROR_PIPELINE = "Pipeline error. See details below."
ERROR_OUTPUT_MISSING = "Backend completed, but no new Excel output was found."

# ── Debug labels ──────────────────────────────────────────────────────────────
DEBUG_FRONTEND_UPLOAD_DIR = "Frontend upload folder"
DEBUG_BACKEND_DATA_DIR = "Backend data folder"
DEBUG_BACKEND_OUTPUT_DIR = "Backend output folder"
DEBUG_BACKEND_COMMAND = "Backend command"
DEBUG_BACKEND_LOG = "Backend log"