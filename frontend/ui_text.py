# frontend/ui_text.py
"""
All display strings, help text, and labels for the Streamlit UI.

Keep display text here so app.py stays clean.
"""

APP_TITLE = "Tax Workpaper Generator"
APP_SUBTITLE = "ICGTAX Partners · Automated Tax Reconciliation"

# ── Section headers ───────────────────────────────────────────────────────────
SECTION_FILES = "Upload Balance Sheet and Profit & Loss sheets"
SECTION_PROFILE = "Engagement information"
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

# ── Business profile prompt ───────────────────────────────────────────────────
BUSINESS_PROFILE_LABEL = "Business profile / industry"
BUSINESS_PROFILE_SECTION_TITLE = "Business profile"
BUSINESS_PROFILE_SECTION_ICON = "🏢"
BUSINESS_PROFILE_IMPACT_NOTE = (
    "Used to pre-select likely review schedules and save engagement context. "
    "Calculations still come only from uploaded workbooks, deterministic rules "
    "and reviewed accountant inputs."
)
BUSINESS_PROFILE_OPTIONS = [
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
]
BUSINESS_PROFILE_ICONS = {
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
}

ATO_STATUS_SECTION = "ATO company-return status"
ATO_STATUS_IMPACT_NOTE = (
    "These return-status facts feed the company tax-rate control below. "
    "Special statuses block tax payable until an accountant confirms the rate."
)
ATO_STATUS_PRESET_LABEL = "Status preset"
ATO_STATUS_PRESET_OPTIONS = [
    "Private",
    "Public",
    "Special/review",
    "Detailed",
]
ATO_RESIDENCY_LABEL = "Residency status"
ATO_RESIDENCY_OPTIONS = [
    "Australian resident company",
    "Non-resident company",
    "Non-resident company carrying on business through an Australian PE",
    "Not required for selected entity type",
]

ATO_ENTITY_TYPE_LABEL = "Entity type for company return"
ATO_ENTITY_TYPE_OPTIONS = [
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
]
ATO_SPECIAL_STATUS_LABEL = "Special status"
ATO_SPECIAL_STATUS_OPTIONS = [
    "Non-profit company",
    "Trustee capacity / other special rate",
    "Life insurance company / friendly society",
    "Medium credit union",
    "Other / review required",
]

ATO_ACTIVITY_LABEL = "Activity indicator"
ATO_ACTIVITY_OPTIONS = [
    "None / ordinary trading or investment activity",
    "Life insurance or friendly society activity",
    "Pooled development fund / special entity activity",
    "Other activity requiring return-status review",
]

ATO_BUSINESS_INDICATORS_LABEL = "Business indicators"
ATO_CONSOLIDATION_LABEL = "Consolidation status"
ATO_CONSOLIDATION_OPTIONS = [
    "Not a consolidated or MEC group member",
    "Consolidated or MEC head company",
    "Consolidated or MEC subsidiary member with non-membership period",
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


def safety_stop_guidance(
    error_code: str | None,
    selected_income_year: str | None = None,
) -> dict[str, str] | None:
    """Return recovery text for a fail-closed input validation result.

    These messages deliberately distinguish a protected source-data problem
    from an application crash.  They never suggest changing a source amount in
    the generated workpaper: the correction must be made, evidenced and
    re-uploaded at source.
    """
    messages = {
        "CELL-001": {
            "title": "Stopped deliberately: an Excel error needs repair",
            "reason": (
                "A confirmed monetary cell contains an Excel error such as "
                "#REF!, #VALUE! or #DIV/0!. The system did not convert it to "
                "zero or guess a replacement amount."
            ),
            "action": (
                "Repair the formula or reference in the source workbook, or "
                "replace it with an accountant-confirmed amount. Keep the "
                "source evidence, then upload the corrected workbook and run again."
            ),
        },
        "CELL-002": {
            "title": "Stopped deliberately: a monetary cell is not a valid number",
            "reason": (
                "A confirmed amount column contains text that cannot safely be "
                "read as money (for example, $12O0). The system did not guess "
                "which number was intended or change the source value."
            ),
            "action": (
                "Correct the source cell to a valid numeric amount, retain the "
                "supporting evidence, then upload the corrected workbook and run again."
            ),
        },
        "STRUCT-003": {
            "title": "Stopped deliberately: incompatible report tables were detected",
            "reason": (
                "The upload appears to contain a tax-disclosure table and a "
                "client trial-balance table that cannot be paired safely. The "
                "system did not choose one or combine their amounts."
            ),
            "action": (
                "Upload the source Profit and Loss and Balance Sheet reports "
                "separately, or provide a clearly scoped workbook with one report "
                "table per sheet. Then run again."
            ),
        },
    }
    if error_code == "PERIOD-001":
        year = selected_income_year or "the selected income year"
        return {
            "title": "Stopped deliberately: the source-period column is not unique",
            "reason": (
                f"The source report does not have exactly one clear amount column for {year}. "
                "The system did not select a duplicate, neighbouring or similarly named period."
            ),
            "action": (
                "Check the uploaded Profit and Loss report: it needs one **Account** or "
                "**Description** header row and exactly one column headed with the selected "
                "income year (for example `2025` or `30 June 2025`). Remove duplicate "
                "period columns or select the matching Income year, then run again."
            ),
        }
    return messages.get(error_code)


SAFETY_STOP_NO_CHANGE = (
    "This is a deliberate safety stop, not a tax conclusion or a software crash. "
    "No workbook was created and no source amount was changed."
)

# ── Debug labels ──────────────────────────────────────────────────────────────
DEBUG_FRONTEND_UPLOAD_DIR = "Frontend upload folder"
DEBUG_BACKEND_DATA_DIR = "Backend data folder"
DEBUG_BACKEND_OUTPUT_DIR = "Backend output folder"
DEBUG_BACKEND_COMMAND = "Backend command"
DEBUG_BACKEND_LOG = "Backend log"
