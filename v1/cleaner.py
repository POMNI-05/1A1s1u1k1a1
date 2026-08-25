# v1/cleaner.py
"""Parse/chunk accountant, audit, and Xero reports without changing evidence.

Responsibilities:
1. Discover possible report inputs.
2. Detect whether each sheet is P&L, Balance Sheet, tax depreciation, or unknown.
3. Clean financial report sheets into structured rows.
4. Extract optional support totals such as tax depreciation.

Design rule:
- Accountant/audit titles and sheet names are generally reliable.
- Sheet name and top title text are treated as strong signals.
- Content scoring is used as confirmation/fallback.
- Source metadata stays internal in ReportInput and is not displayed in output sheets.
"""

from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Iterable

import pandas as pd

try:
    from .config import (
        ALLOW_COMBINED_WORKBOOK,
        BS_RAW_PATH,
        BS_SHEET_NAME,
        INPUT_WORKBOOK_PATH,
        PL_RAW_PATH,
        PL_SHEET_NAME,
        REPORT_TYPE_BS,
        REPORT_TYPE_PL,
        REPORT_TYPE_TAX_DEPRECIATION,
        REPORT_TYPE_UNKNOWN,
        SELECTED_INCOME_YEAR,
        TAX_DEPRECIATION_PATH,
        TAX_DEPRECIATION_SHEET_NAME,
    )
except ImportError:  # Direct-script compatibility.
    from config import (
    ALLOW_COMBINED_WORKBOOK,
    BS_RAW_PATH,
    BS_SHEET_NAME,
    INPUT_WORKBOOK_PATH,
    PL_RAW_PATH,
    PL_SHEET_NAME,
    REPORT_TYPE_BS,
    REPORT_TYPE_PL,
    REPORT_TYPE_TAX_DEPRECIATION,
    REPORT_TYPE_UNKNOWN,
    SELECTED_INCOME_YEAR,
    TAX_DEPRECIATION_PATH,
    TAX_DEPRECIATION_SHEET_NAME,
    )

logger = logging.getLogger(__name__)

NET_PROFIT_ALIASES = [
    "net profit",
    "net loss",
    "net profit / loss",
    "net profit/(loss)",
    "profit before tax",
    "accounting profit before tax",
    "profit (loss)",
]

TOTAL_ASSETS_ALIASES = ["total assets"]
TOTAL_LIABILITIES_ALIASES = ["total liabilities"]
TOTAL_EQUITY_ALIASES = ["total equity"]
NET_ASSETS_ALIASES = ["net assets"]

TAX_DEPRECIATION_TOTAL_ALIASES = [
    "total depreciation",
    "total tax depreciation",
    "total decline in value",
    "decline in value",
    "deductible decline in value",
    "tax depreciation",
    "depreciation deduction",
]

ACCOUNT_LABEL_COL = "Account Label"

HELPER_COLS = {
    "source row",
    "row type",
    "report section",
    "itr ref",
    "itr label",
    "treatment",
    "confidence",
    "review note",
    "label reason",
    "recon itr ref",
    "account label",
}

# A generated workpaper is sometimes re-uploaded as evidence.  Its copied
# source report remains useful, but its right-hand ITR columns are not source
# amounts and must never participate in period/amount detection.
GENERATED_OUTPUT_MARKERS = {
    "itr label",
    "itr ref",
    "confidence",
    "label reason",
    "review note",
    "itr totals",
    "balance sheet itr summary",
}

PL_TITLE_KEYWORDS = [
    "profit and loss",
    "profit & loss",
    "p&l",
    "income statement",
    "statement of profit or loss",
    "statement of comprehensive income",
]

BS_TITLE_KEYWORDS = [
    "balance sheet",
    "statement of financial position",
]

TAX_DEPRECIATION_TITLE_KEYWORDS = [
    "tax depreciation",
    "depreciation schedule",
    "tax depreciation schedule",
    "decline in value",
    "capital allowance",
    "capital allowances",
]

PL_CONTENT_KEYWORDS = [
    "trading income",
    "gross profit",
    "net profit",
    "net loss",
    "operating expenses",
    "cost of sales",
    "total income",
    "total expenses",
]

BS_CONTENT_KEYWORDS = [
    "total assets",
    "total liabilities",
    "net assets",
    "total equity",
    "current assets",
    "non-current assets",
    "current liabilities",
    "retained earnings",
]

TAX_DEPRECIATION_CONTENT_KEYWORDS = [
    "opening adjustable value",
    "closing adjustable value",
    "prime cost",
    "diminishing value",
    "effective life",
    "depreciable asset",
    "taxable use",
    "decline in value",
    "depreciation deduction",
]


@dataclass(frozen=True)
class ReportStructure:
    account_col: str
    amount_cols: list[str]
    current_amount_col: str


@dataclass(frozen=True)
class ReportInput:
    report_type: str
    source_path: Path
    sheet_name: str
    raw_df: pd.DataFrame
    detection_score: int
    detection_reason: str
    forced_type: bool = False


@dataclass(frozen=True)
class CleanedReports:
    raw_pl: pd.DataFrame
    raw_bs: pd.DataFrame
    clean_pl: pd.DataFrame
    clean_bs: pd.DataFrame
    pl_input: ReportInput
    bs_input: ReportInput
    tax_depreciation_total: float | None = None
    tax_depreciation_source: str | None = None
    tax_depreciation_report: ReportInput | None = None
    tax_depreciation_matches_selected_period: bool = False


class AmountParseStatus(str, Enum):
    """Meaning of a source amount before it enters calculation logic."""

    BLANK = "blank"
    VALID = "valid"
    INVALID = "invalid"


@dataclass(frozen=True)
class AmountParseResult:
    """A source monetary value with its parsing outcome preserved."""

    value: float | None
    status: AmountParseStatus
    raw_value: object


def parse_amount(value) -> AmountParseResult:
    """Parse a monetary cell without silently converting invalid text to zero."""

    if pd.isna(value):
        return AmountParseResult(None, AmountParseStatus.BLANK, value)

    if isinstance(value, bool):
        return AmountParseResult(None, AmountParseStatus.INVALID, value)

    if isinstance(value, (int, float)):
        number = float(value)
        if math.isfinite(number):
            return AmountParseResult(number, AmountParseStatus.VALID, value)
        return AmountParseResult(None, AmountParseStatus.INVALID, value)

    text = str(value).strip()
    if text.lower() in {"", "nan", "none", "-", "--"}:
        return AmountParseResult(None, AmountParseStatus.BLANK, value)

    negative = text.startswith("(") and text.endswith(")")
    if negative:
        text = text[1:-1]

    cleaned = re.sub(r"[$,%\s,]", "", text)
    try:
        number = float(cleaned)
    except ValueError:
        return AmountParseResult(None, AmountParseStatus.INVALID, value)

    if not math.isfinite(number):
        return AmountParseResult(None, AmountParseStatus.INVALID, value)
    return AmountParseResult(-number if negative else number, AmountParseStatus.VALID, value)


def clean_amount(value) -> float:
    """Return a calculation value, rejecting invalid source monetary text."""

    result = parse_amount(value)
    if result.status == AmountParseStatus.INVALID:
        raise ValueError(f"CELL-002: unparseable monetary value: {value!r}")
    return 0.0 if result.value is None else result.value


def _invalid_amount_value(value) -> bool:
    """Return True for explicit Excel errors; blanks remain valid blanks."""
    if pd.isna(value):
        return False
    return bool(
        re.search(
            r"#(?:REF!|VALUE!|DIV/0!|NAME\?|N/A|NUM!|NULL!)",
            str(value),
            flags=re.IGNORECASE,
        )
    )


def _has_unsafe_side_by_side_tables(raw_df: pd.DataFrame) -> bool:
    """Detect the known unsafe tax-disclosure + client-TB composite layout."""
    preview = " | ".join(
        normalise_match_text(value)
        for value in raw_df.head(20).to_numpy().ravel()
        if not pd.isna(value)
    )
    has_tax_disclosure = "tax return disclosures" in preview
    has_client_tb = any(
        marker in preview
        for marker in (
            "source data from client trial balance",
            "from client tb",
            "client trial balance",
        )
    )
    return has_tax_disclosure and has_client_tb


def normalise_text(value) -> str:
    if pd.isna(value):
        return ""
    return re.sub(r"\s+", " ", str(value).replace("\n", " ")).strip()


def normalise_match_text(value) -> str:
    return normalise_text(value).lower()


def _normalise_column_names(columns: Iterable) -> list[str]:
    seen: dict[str, int] = {}
    out = []

    for idx, col in enumerate(columns):
        name = normalise_text(col)

        if not name or name.lower().startswith("unnamed"):
            name = f"Column {idx + 1}"

        count = seen.get(name, 0)
        seen[name] = count + 1

        out.append(name if count == 0 else f"{name}_{count + 1}")

    return out


def standardise_account_names(series: pd.Series) -> pd.Series:
    return series.apply(normalise_text)

def _is_blank_text(value) -> bool:
    text = normalise_match_text(value)
    return text in {"", "nan", "none"}


def _candidate_label_cols(
    df: pd.DataFrame,
    account_col: str,
    amount_cols: list[str],
) -> list[str]:
    """Return text-like columns that may contain the visible row label.

    Xero/accountant exports sometimes put headings/totals in a left structural
    column, while detail accounts sit in the Account column. We need both.
    """
    amount_set = set(amount_cols)
    candidates: list[str] = []

    for col in df.columns:
        lower = normalise_match_text(col)

        if col in amount_set:
            continue

        if lower in HELPER_COLS:
            continue

        if lower.endswith("parse status"):
            continue

        if "variance" in lower or "%" in lower:
            continue

        text_count = df[col].astype(str).str.contains(
            r"[A-Za-z]",
            na=False,
            regex=True,
        ).sum()

        if text_count > 0:
            candidates.append(col)

    # Prefer structural/left columns first, but still include account_col.
    if account_col in candidates:
        candidates.remove(account_col)
        candidates.append(account_col)

    return candidates


def add_account_label_column(
    df: pd.DataFrame,
    account_col: str,
    amount_cols: list[str],
) -> pd.DataFrame:
    """Create an internal row label used for cleaning/labelling.

    Priority:
    - use the Account column when populated;
    - otherwise use the first non-empty structural text column.

    This fixes rows like:
    - Less Cost of Sales
    - Total Liabilities
    - Net Assets
    - Total Equity
    """
    out = df.copy()
    candidate_cols = _candidate_label_cols(out, account_col, amount_cols)

    def row_label(row) -> str:
        account_value = normalise_text(row.get(account_col, ""))
        if account_value and normalise_match_text(account_value) not in {"nan", "none"}:
            return account_value

        for col in candidate_cols:
            value = normalise_text(row.get(col, ""))
            if value and normalise_match_text(value) not in {"nan", "none"}:
                return value

        return ""

    out[ACCOUNT_LABEL_COL] = out.apply(row_label, axis=1)
    return out

def _sheet_names(path: Path) -> list[str]:
    excel = pd.ExcelFile(path)
    return list(excel.sheet_names)


def _read_excel_sheet(path: Path, sheet_name: str | int) -> pd.DataFrame:
    return pd.read_excel(path, sheet_name=sheet_name, header=None)


def _remove_generated_output_columns(raw_df: pd.DataFrame) -> pd.DataFrame:
    """Remove known generated ITR helper columns from a re-uploaded output.

    This is intentionally narrow: only columns with a generated-workpaper
    marker in the first 40 rows are removed.  For a two-column ITR summary,
    remove its immediately following amount/formula column as well.  Raw
    source evidence remains unchanged on disk.
    """

    generated_columns: set[int] = set()
    for col_idx in range(raw_df.shape[1]):
        values = {
            normalise_match_text(value)
            for value in raw_df.iloc[:40, col_idx].tolist()
            if not pd.isna(value)
        }
        matched_markers = values & GENERATED_OUTPUT_MARKERS
        if not matched_markers:
            continue

        generated_columns.add(col_idx)
        if {"itr totals", "balance sheet itr summary"} & matched_markers:
            generated_columns.add(col_idx + 1)

    if not generated_columns:
        return raw_df

    keep_columns = [
        col_idx
        for col_idx in range(raw_df.shape[1])
        if col_idx not in generated_columns
    ]
    logger.info(
        "INTAKE-004: ignored generated workpaper helper columns=%s",
        sorted(generated_columns),
    )
    return raw_df.iloc[:, keep_columns].copy()


def _first_rows_text(raw_df: pd.DataFrame, rows: int = 15) -> str:
    preview = raw_df.head(rows).astype(str).fillna("")
    values = preview.values.ravel().tolist()
    return " ".join(normalise_match_text(v) for v in values if normalise_match_text(v))


def _keyword_score(text: str, keywords: list[str], points: int) -> int:
    return sum(points for keyword in keywords if keyword in text)


def infer_report_type(sheet_name: str, raw_df: pd.DataFrame) -> tuple[str, int, str]:
    sheet_text = normalise_match_text(sheet_name)
    title_text = _first_rows_text(raw_df, rows=8)
    content_text = _first_rows_text(raw_df, rows=45)

    scores = {
        REPORT_TYPE_PL: 0,
        REPORT_TYPE_BS: 0,
        REPORT_TYPE_TAX_DEPRECIATION: 0,
    }

    reasons = {
        REPORT_TYPE_PL: [],
        REPORT_TYPE_BS: [],
        REPORT_TYPE_TAX_DEPRECIATION: [],
    }

    title_keyword_sets = [
        (REPORT_TYPE_PL, PL_TITLE_KEYWORDS),
        (REPORT_TYPE_BS, BS_TITLE_KEYWORDS),
        (REPORT_TYPE_TAX_DEPRECIATION, TAX_DEPRECIATION_TITLE_KEYWORDS),
    ]

    content_keyword_sets = [
        (REPORT_TYPE_PL, PL_CONTENT_KEYWORDS),
        (REPORT_TYPE_BS, BS_CONTENT_KEYWORDS),
        (REPORT_TYPE_TAX_DEPRECIATION, TAX_DEPRECIATION_CONTENT_KEYWORDS),
    ]

    for report_type, keywords in title_keyword_sets:
        score = _keyword_score(sheet_text, keywords, points=12)
        if score:
            scores[report_type] += score
            reasons[report_type].append("sheet name matched")

    for report_type, keywords in title_keyword_sets:
        score = _keyword_score(title_text, keywords, points=10)
        if score:
            scores[report_type] += score
            reasons[report_type].append("top rows/title matched")

    for report_type, keywords in content_keyword_sets:
        score = _keyword_score(content_text, keywords, points=3)
        if score:
            scores[report_type] += score
            reasons[report_type].append("content keywords matched")

    best_type = max(scores, key=scores.get)
    best_score = scores[best_type]

    if best_score <= 0:
        return REPORT_TYPE_UNKNOWN, 0, "no report-type keywords matched"

    reason = "; ".join(reasons[best_type]) or "best score"
    return best_type, best_score, reason


def _make_report_input(
    path: Path,
    sheet_name: str,
    forced_report_type: str | None = None,
) -> ReportInput:
    raw_df = _read_excel_sheet(path, sheet_name)

    if forced_report_type:
        return ReportInput(
            report_type=forced_report_type,
            source_path=path,
            sheet_name=str(sheet_name),
            raw_df=raw_df,
            detection_score=999,
            detection_reason="forced by config/path",
            forced_type=True,
        )

    report_type, score, reason = infer_report_type(str(sheet_name), raw_df)

    return ReportInput(
        report_type=report_type,
        source_path=path,
        sheet_name=str(sheet_name),
        raw_df=raw_df,
        detection_score=score,
        detection_reason=reason,
        forced_type=False,
    )


def _read_workbook_inputs(
    path: str | Path,
    forced_report_type: str | None = None,
    forced_sheet_name: str = "",
) -> list[ReportInput]:
    path = Path(path)

    if not path.exists():
        return []

    if forced_sheet_name:
        return [_make_report_input(path, forced_sheet_name, forced_report_type)]

    return [_make_report_input(path, sheet, forced_report_type) for sheet in _sheet_names(path)]


def discover_report_inputs() -> list[ReportInput]:
    inputs: list[ReportInput] = []

    # 1. Scan every Excel workbook placed in data/
    data_dir = Path(INPUT_WORKBOOK_PATH).parent

    if data_dir.exists():
        for path in sorted(data_dir.glob("*.xlsx")):
            if path.name.startswith("~$"):
                continue

            logger.info("Scanning workbook in data folder: %s", path)
            inputs.extend(_read_workbook_inputs(path))

    # 2. Also support explicit INPUT_WORKBOOK_PATH outside data/
    input_path = Path(INPUT_WORKBOOK_PATH)
    if input_path.exists() and input_path.parent != data_dir:
        inputs.extend(_read_workbook_inputs(input_path))

    # 3. Keep old separate-file fallback support
    inputs.extend(
        _read_workbook_inputs(
            PL_RAW_PATH,
            forced_report_type=REPORT_TYPE_PL,
            forced_sheet_name=PL_SHEET_NAME,
        )
    )

    inputs.extend(
        _read_workbook_inputs(
            BS_RAW_PATH,
            forced_report_type=REPORT_TYPE_BS,
            forced_sheet_name=BS_SHEET_NAME,
        )
    )

    # 4. Optional tax depreciation file
    if TAX_DEPRECIATION_PATH:
        inputs.extend(
            _read_workbook_inputs(
                TAX_DEPRECIATION_PATH,
                forced_report_type=REPORT_TYPE_TAX_DEPRECIATION,
                forced_sheet_name=TAX_DEPRECIATION_SHEET_NAME,
            )
        )

    # 5. Optional forced tax depreciation sheet from combined workbook
    if (
        ALLOW_COMBINED_WORKBOOK
        and TAX_DEPRECIATION_SHEET_NAME
        and Path(INPUT_WORKBOOK_PATH).exists()
    ):
        inputs.append(
            _make_report_input(
                Path(INPUT_WORKBOOK_PATH),
                TAX_DEPRECIATION_SHEET_NAME,
                REPORT_TYPE_TAX_DEPRECIATION,
            )
        )

    for item in inputs:
        logger.info(
            "Discovered report input type=%s score=%s forced=%s file=%s sheet=%s reason=%s",
            item.report_type,
            item.detection_score,
            item.forced_type,
            item.source_path,
            item.sheet_name,
            item.detection_reason,
        )

    return inputs

def _select_best_input(
    inputs: list[ReportInput],
    report_type: str,
    required: bool = True,
) -> ReportInput | None:
    matches = [item for item in inputs if item.report_type == report_type]

    if not matches:
        if required:
            searched = sorted({str(item.source_path) for item in inputs})
            raise FileNotFoundError(
                f"Could not find required report type {report_type!r}. "
                f"Searched sources: {searched}"
            )
        return None

    matches.sort(key=lambda item: (item.forced_type, item.detection_score), reverse=True)
    selected = matches[0]

    if len(matches) > 1:
        logger.warning(
            "Multiple %s reports found. Selected file=%s sheet=%s. Other candidates=%s",
            report_type,
            selected.source_path,
            selected.sheet_name,
            [(str(x.source_path), x.sheet_name, x.detection_score) for x in matches[1:]],
        )

    return selected


def find_data_start_row_in_df(raw_df: pd.DataFrame, scan_rows: int = 80) -> int:
    preview = raw_df.head(scan_rows)
    best_row, best_score = 0, -1

    for i, row in preview.iterrows():
        values = [normalise_match_text(x) for x in row.tolist()]
        score = 0

        if any(v in {"account", "description", "account name", "name"} for v in values):
            score += 6

        # Do not treat a ledger balance such as 5,352,063 as a period merely
        # because it contains the digit sequence 2063.  A period header must
        # be an explicit year/date label, not an arbitrary numeric cell.
        if any(
            re.search(r"30 june|30 jun|\byear\b", v)
            or re.fullmatch(r"20\d{2}(?:\.0)?", v)
            or re.match(r"20\d{2}[-/]\d{1,2}[-/]\d{1,2}", v)
            for v in values
        ):
            score += 2

        if sum(v not in {"", "nan", "none"} for v in values) >= 2:
            score += 1

        if score > best_score:
            best_row, best_score = int(i), score

        if score >= 7:
            return int(i)

    logger.warning("Weak header detection; using row %s", best_row)
    return best_row


def find_data_start_row(
    filepath: str | Path,
    scan_rows: int = 80,
    sheet_name: str | int = 0,
) -> int:
    raw_df = _read_excel_sheet(Path(filepath), sheet_name)
    return find_data_start_row_in_df(raw_df, scan_rows=scan_rows)


def detect_account_col(df: pd.DataFrame) -> str:
    for col in df.columns:
        if normalise_match_text(col) in {"account", "description", "account name", "name"}:
            return col

    best = df.columns[0]
    best_text = -1

    for col in df.columns:
        text_count = df[col].astype(str).str.contains(r"[A-Za-z]", na=False, regex=True).sum()

        if text_count > best_text:
            best, best_text = col, text_count

    return best


def _is_report_amount_header(column_name: object) -> bool:
    """Return whether a header can represent a report amount period/value.

    Xero exports commonly contain blank structural columns and `[FX]` marker
    columns beside an Account column.  Numeric density alone cannot promote
    those columns to money: the header must say it is a period or amount.
    """
    header = normalise_match_text(column_name)
    if not header or header.startswith("column "):
        return False

    return bool(
        re.fullmatch(r"20\d{2}(?:\.0)?", header)
        or re.search(r"\b30\s+(?:june|jun)\b|\byear\s+ended\b|\bas\s+at\b", header)
        or header
        in {
            "amount",
            "actual",
            "balance",
            "closing balance",
            "debit",
            "credit",
            "cost",
            "depreciation",
            "closing value",
        }
        or bool(re.search(r"depreciation|decline in value|tax deduction", header))
    )


def detect_amount_cols(df: pd.DataFrame, account_col: str | None = None) -> list[str]:
    account_col = account_col or detect_account_col(df)
    amount_cols: list[str] = []

    for col in df.columns:
        lower = normalise_match_text(col)

        if col == account_col:
            continue

        if lower in HELPER_COLS:
            continue

        if "variance" in lower or "%" in lower:
            continue

        # Do not parse a structural/separator/annotation column just because
        # it happens to contain digits.  This is the Xero `Column 1` false
        # positive that previously surfaced headings such as "Assets" as
        # CELL-002 amount failures.
        if not _is_report_amount_header(col):
            continue

        parsed = df[col].apply(parse_amount)
        cleaned = parsed.map(lambda result: result.value or 0.0)
        raw_has_digits = df[col].astype(str).str.contains(r"\d", na=False, regex=True)
        raw_has_errors = df[col].apply(_invalid_amount_value)

        if (
            raw_has_digits.sum() >= max(2, len(df) * 0.12)
            or (cleaned != 0).sum() >= 1
            or raw_has_errors.any()
        ):
            amount_cols.append(col)

    return amount_cols


def choose_current_amount_col(df: pd.DataFrame, amount_cols: list[str]) -> str:
    if not amount_cols:
        raise ValueError("No amount columns detected in report.")

    requested_year_matches = []

    for col in amount_cols:
        lower = normalise_match_text(col)

        if str(SELECTED_INCOME_YEAR) in lower and "variance" not in lower:
            requested_year_matches.append(col)

    if len(requested_year_matches) == 1:
        return requested_year_matches[0]

    if len(requested_year_matches) > 1:
        raise ValueError(
            f"PERIOD-001: income year {SELECTED_INCOME_YEAR} matches multiple amount columns: "
            f"{requested_year_matches}"
        )

    # A one-period report can legitimately use a generic amount header.
    if len(amount_cols) == 1:
        return amount_cols[0]

    raise ValueError(
        f"PERIOD-001: income year {SELECTED_INCOME_YEAR} is not uniquely present in report columns: "
        f"{amount_cols}"
    )


def detect_report_structure(df: pd.DataFrame) -> ReportStructure:
    account_col = detect_account_col(df)
    amount_cols = detect_amount_cols(df, account_col)

    return ReportStructure(
        account_col=account_col,
        amount_cols=amount_cols,
        current_amount_col=choose_current_amount_col(df, amount_cols),
    )


def _detect_amount_col(df: pd.DataFrame) -> str:
    return detect_report_structure(df).current_amount_col


def _normalised_name(value: str) -> str:
    return normalise_match_text(value)

def add_row_type(df: pd.DataFrame, account_col: str, amount_cols: list[str]) -> pd.DataFrame:
    """
    Classify each cleaned row.

    Main goal:
    - headings/sections are structure only
    - totals are check/result rows
    - actual accounts are the only rows that should be mapped by rules
    """
    out = df.copy()

    heading_names = {
        # P&L headings
        "trading income",
        "income",
        "revenue",
        "sales",
        "operating revenue",
        "other revenue",
        "other income",
        "less cost of sales",
        "cost of sales",
        "cost of goods sold",
        "cogs",
        "direct costs",
        "gross profit",
        "less operating expenses",
        "operating expenses",
        "expenses",

        # Balance Sheet headings
        "assets",
        "current assets",
        "non-current assets",
        "non current assets",
        "fixed assets",
        "property plant and equipment",
        "liabilities",
        "current liabilities",
        "non-current liabilities",
        "non current liabilities",
        "equity",
        "shareholders equity",
        "shareholder equity",
        "owners equity",
    }

    total_exact = {
        # P&L totals
        "total income",
        "total revenue",
        "total sales",
        "total trading income",
        "total cost of sales",
        "total cogs",
        "total direct costs",
        "total other income",
        "total operating expenses",
        "total expenses",
        "gross profit",
        "gross loss",
        "net profit",
        "net loss",
        "net profit / loss",
        "net profit/(loss)",
        "profit before tax",
        "accounting profit before tax",
        "net profit after tax",

        # Balance Sheet totals
        "net assets",
        "total assets",
        "total liabilities",
        "total equity",
        "total current assets",
        "total non-current assets",
        "total non current assets",
        "total current liabilities",
        "total non-current liabilities",
        "total non current liabilities",
    }

    def has_amount(row) -> bool:
        for col in amount_cols:
            if abs(clean_amount(row.get(col, 0.0))) > 0.005:
                return True
        return False

    def row_type(row) -> str:
        text = _normalised_name(row.get(account_col, ""))

        if text in {"", "nan", "none"}:
            return "blank"

        if text in total_exact or text.startswith("total "):
            return "total"

        # A populated monetary row is an account even when its name also looks
        # like a section heading (for example Sales or Other Income).
        if has_amount(row):
            return "account"

        if text in heading_names:
            return "heading"

        # Rows with no amounts and very short structural names are probably headings/notes.
        if not has_amount(row):
            if len(text.split()) <= 5 and not re.search(r"\d", text):
                return "heading"
            return "note"

        return "account"

    out["Row Type"] = out.apply(row_type, axis=1)
    return out


def add_report_section(df: pd.DataFrame, account_col: str) -> pd.DataFrame:
    """
    Carry down the most recent heading as Report Section.

    For total rows such as Gross Profit / Net Profit, keep the previous section.
    """
    out = df.copy()
    current = ""
    sections: list[str] = []

    for _, row in out.iterrows():
        row_type = normalise_match_text(row.get("Row Type", ""))
        label = normalise_text(row.get(account_col, ""))

        if row_type == "heading":
            current = label

        sections.append(current)

    out["Report Section"] = sections
    return out

def _table_from_raw_df(raw_df: pd.DataFrame, start_row: int) -> pd.DataFrame:
    header = raw_df.iloc[start_row].tolist()
    data = raw_df.iloc[start_row + 1:].copy()

    data.columns = _normalise_column_names(header)
    data["Source Row"] = [start_row + 2 + i for i in range(len(data))]

    return data.dropna(how="all").dropna(axis=1, how="all").reset_index(drop=True)


def clean_report_input(report_input: ReportInput) -> pd.DataFrame:
    logger.info(
        "Cleaning report type=%s file=%s sheet=%s",
        report_input.report_type,
        report_input.source_path,
        report_input.sheet_name,
    )

    if _has_unsafe_side_by_side_tables(report_input.raw_df):
        raise ValueError(
            "STRUCT-003: tax-disclosure and client trial-balance tables are "
            "side by side and cannot be safely paired"
        )

    raw_df = _remove_generated_output_columns(report_input.raw_df)
    start_row = find_data_start_row_in_df(raw_df)
    df = _table_from_raw_df(raw_df, start_row)

    structure = detect_report_structure(df)
    account_col = structure.account_col

    parsed_amounts: dict[str, pd.Series] = {}
    invalid_excel_cells = []
    invalid_amount_cells = []
    for col in structure.amount_cols:
        parsed = df[col].apply(parse_amount)
        parsed_amounts[col] = parsed
        for row_index, result in parsed.items():
            if result.status == AmountParseStatus.INVALID:
                cell = f"{col} row {int(row_index) + start_row + 2}: {result.raw_value}"
                if _invalid_amount_value(result.raw_value):
                    invalid_excel_cells.append(cell)
                else:
                    invalid_amount_cells.append(cell)

    if invalid_excel_cells:
        sample = "; ".join(invalid_excel_cells[:5])
        raise ValueError(f"CELL-001: invalid Excel amount value(s): {sample}")
    if invalid_amount_cells:
        sample = "; ".join(invalid_amount_cells[:5])
        raise ValueError(f"CELL-002: unparseable monetary value(s): {sample}")

    df[account_col] = standardise_account_names(df[account_col])

    for col in structure.amount_cols:
        parsed = parsed_amounts[col]
        df[col] = parsed.map(lambda result: result.value)
        df[f"{col} Parse Status"] = parsed.map(lambda result: result.status.value)

    # Internal visible row label.
    # This is used for headings/totals that may sit outside the formal Account column.
    df = add_account_label_column(df, account_col, structure.amount_cols)

    df = df[
        ~df[ACCOUNT_LABEL_COL].str.lower().isin(
            {"", "nan", "none", "account", "description"}
        )
    ].copy()

    df = add_row_type(df, ACCOUNT_LABEL_COL, structure.amount_cols)
    df = add_report_section(df, ACCOUNT_LABEL_COL)

    logger.info(
        "Cleaned %s rows=%s account_col=%s amount_cols=%s",
        report_input.report_type,
        len(df),
        account_col,
        structure.amount_cols,
    )

    return df


def clean_report(
    filepath: str | Path,
    report_label: str,
    sheet_name: str | int = 0,
) -> pd.DataFrame:
    path = Path(filepath)
    raw_df = _read_excel_sheet(path, sheet_name)

    report_type = {
        "Profit and Loss": REPORT_TYPE_PL,
        "Balance Sheet": REPORT_TYPE_BS,
        "Tax Depreciation": REPORT_TYPE_TAX_DEPRECIATION,
    }.get(report_label, REPORT_TYPE_UNKNOWN)

    report_input = ReportInput(
        report_type=report_type,
        source_path=path,
        sheet_name=str(sheet_name),
        raw_df=raw_df,
        detection_score=999,
        detection_reason=f"forced by clean_report label {report_label!r}",
        forced_type=True,
    )

    return clean_report_input(report_input)


def extract_value(
    df: pd.DataFrame,
    aliases: list[str],
    amount_col: str | None = None,
    account_col: str | None = None,
) -> float | None:
    account_col = account_col or detect_account_col(df)
    amount_col = amount_col or _detect_amount_col(df)

    names = df[account_col].astype(str).str.strip().str.lower()

    for alias in aliases:
        a = alias.strip().lower()

        exact = df[names.eq(a)]
        if not exact.empty:
            return clean_amount(exact.iloc[-1][amount_col])

        contains = df[names.str.contains(re.escape(a), na=False, regex=True)]
        if not contains.empty:
            return clean_amount(contains.iloc[-1][amount_col])

    return None


def _clean_support_sheet(raw_df: pd.DataFrame) -> pd.DataFrame:
    start_row = find_data_start_row_in_df(raw_df)
    df = _table_from_raw_df(raw_df, start_row)

    if df.empty:
        return df

    # Support schedules may have several numeric columns (cost, depreciation,
    # closing value) but no report-period header.  Their selected deduction is
    # resolved explicitly by extract_tax_depreciation_total(), so do not apply
    # the P&L/BS requested-period selector here.
    account_col = detect_account_col(df)
    amount_cols = detect_amount_cols(df, account_col)

    for col in amount_cols:
        parsed = df[col].apply(parse_amount)
        invalid = parsed[parsed.map(lambda result: result.status == AmountParseStatus.INVALID)]
        if not invalid.empty:
            samples = "; ".join(str(result.raw_value) for result in invalid.iloc[:5])
            raise ValueError(f"CELL-002: unparseable support-schedule amount value(s): {samples}")
        df[col] = parsed.map(lambda result: result.value)
        df[f"{col} Parse Status"] = parsed.map(lambda result: result.status.value)

    return df


def extract_tax_depreciation_total(report_input: ReportInput) -> float | None:
    df = _clean_support_sheet(report_input.raw_df)

    if df.empty:
        return None

    account_col = detect_account_col(df)
    amount_cols = detect_amount_cols(df, account_col)

    if not amount_cols:
        return None

    names = df[account_col].astype(str).map(normalise_match_text)
    total_rows = df[
        names.eq("total")
        | names.eq("total depreciation")
        | names.eq("total tax depreciation")
        | names.eq("total decline in value")
        | names.eq("depreciation deduction")
    ]

    depreciation_cols = [
        col for col in amount_cols
        if re.search(
            r"depreciation|decline in value|tax deduction",
            normalise_match_text(col),
        )
    ]

    if total_rows.empty or not depreciation_cols:
        logger.warning(
            "DEPR-002: explicit depreciation total/column not found in %s :: %s",
            report_input.source_path,
            report_input.sheet_name,
        )
        return None

    year_cols = [
        col for col in depreciation_cols
        if str(SELECTED_INCOME_YEAR) in normalise_match_text(col)
    ]
    if len(year_cols) > 1:
        logger.warning("DEPR-001: multiple requested-year depreciation columns: %s", year_cols)
        return None

    amount_col = year_cols[0] if year_cols else depreciation_cols[0]
    value = total_rows.iloc[-1][amount_col]

    if _invalid_amount_value(value):
        raise ValueError(f"CELL-001: invalid tax depreciation total: {value}")

    return clean_amount(value)


def _tax_depreciation_matches_selected_period(report_input: ReportInput) -> bool:
    """Require an explicit selected-year marker in a schedule's title/header.

    A tax depreciation schedule is period-specific evidence.  Do not reuse a
    previous-year schedule merely because it is the only schedule uploaded.
    """
    preview = " ".join(
        str(value)
        for value in report_input.raw_df.head(6).to_numpy().ravel()
        if not pd.isna(value)
    )
    return bool(re.search(rf"\b{re.escape(str(SELECTED_INCOME_YEAR))}\b", preview))


def load_clean_report_bundle() -> CleanedReports:
    inputs = discover_report_inputs()

    pl_input = _select_best_input(inputs, REPORT_TYPE_PL, required=True)
    bs_input = _select_best_input(inputs, REPORT_TYPE_BS, required=True)
    tax_dep_input = _select_best_input(inputs, REPORT_TYPE_TAX_DEPRECIATION, required=False)

    assert pl_input is not None
    assert bs_input is not None

    clean_pl = clean_report_input(pl_input)
    clean_bs = clean_report_input(bs_input)

    tax_depreciation_total = None
    tax_depreciation_source = None
    tax_depreciation_matches_selected_period = False

    if tax_dep_input is not None:
        tax_depreciation_total = extract_tax_depreciation_total(tax_dep_input)
        tax_depreciation_source = f"{tax_dep_input.source_path} :: {tax_dep_input.sheet_name}"
        tax_depreciation_matches_selected_period = _tax_depreciation_matches_selected_period(
            tax_dep_input
        )

        logger.info(
            "Extracted tax depreciation total=%s from %s matches_selected_period=%s",
            tax_depreciation_total,
            tax_depreciation_source,
            tax_depreciation_matches_selected_period,
        )

    return CleanedReports(
        raw_pl=pl_input.raw_df,
        raw_bs=bs_input.raw_df,
        clean_pl=clean_pl,
        clean_bs=clean_bs,
        pl_input=pl_input,
        bs_input=bs_input,
        tax_depreciation_total=tax_depreciation_total,
        tax_depreciation_source=tax_depreciation_source,
        tax_depreciation_report=tax_dep_input,
        tax_depreciation_matches_selected_period=tax_depreciation_matches_selected_period,
    )


def load_raw_reports() -> tuple[pd.DataFrame, pd.DataFrame]:
    bundle = load_clean_report_bundle()
    return bundle.raw_pl, bundle.raw_bs


def load_clean_reports() -> tuple[pd.DataFrame, pd.DataFrame]:
    bundle = load_clean_report_bundle()
    return bundle.clean_pl, bundle.clean_bs
