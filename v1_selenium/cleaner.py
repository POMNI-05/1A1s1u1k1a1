# v1_selenium/cleaner.py
"""
Load and clean Xero P&L / Balance Sheet exports.

Main improvements:
- More robust header detection.
- Separates account column detection from amount column detection.
- Keeps all period amount columns instead of only one fixed column.
- Ignores variance percentage columns when choosing the current amount column.
- Distinguishes between "found zero" and "not found".
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Iterable, List, Optional

import pandas as pd

from config import PL_RAW_PATH, BS_RAW_PATH

logger = logging.getLogger(__name__)

NET_PROFIT_ALIASES = [
    "net profit",
    "net profit/(loss)",
    "net profit / loss",
    "profit / loss",
    "profit and loss",
    "profit after tax",
    "profit (loss)",
    "net income",
    "current year earnings",
]

TOTAL_ASSETS_ALIASES = ["total assets", "assets total"]
TOTAL_LIABILITIES_ALIASES = ["total liabilities", "liabilities total"]
TOTAL_EQUITY_ALIASES = ["total equity", "equity total"]
NET_ASSETS_ALIASES = ["net assets"]

NON_DATA_ACCOUNT_WORDS = {
    "nan",
    "none",
    "",
    "account",
    "description",
}


@dataclass
class ReportStructure:
    account_col: str
    amount_cols: List[str]
    current_amount_col: str


# ---------------------------------------------------------------------------
# Amount cleaning
# ---------------------------------------------------------------------------
def clean_amount(value) -> float:
    if pd.isna(value):
        return 0.0

    s = str(value).strip()
    if s.lower() in {"", "nan", "none", "-", "--"}:
        return 0.0

    is_negative = False
    if s.startswith("(") and s.endswith(")"):
        is_negative = True
        s = s[1:-1]

    s = (
        s.replace("$", "")
        .replace(",", "")
        .replace("%", "")
        .replace(" ", "")
    )

    try:
        number = float(s)
    except ValueError:
        return 0.0

    return -number if is_negative else number


def clean_amount_column(series: pd.Series) -> pd.Series:
    return series.apply(clean_amount)


def _numeric_density(series: pd.Series) -> float:
    if len(series) == 0:
        return 0.0
    numeric = series.apply(lambda x: str(x).strip()).apply(
        lambda x: bool(re.search(r"\d", x)) and clean_amount(x) == clean_amount(x)
    )
    return numeric.sum() / len(series)


# ---------------------------------------------------------------------------
# Header / column detection
# ---------------------------------------------------------------------------
def find_data_start_row(filepath: str, scan_rows: int = 80) -> int:
    preview = pd.read_excel(filepath, header=None, nrows=scan_rows)

    best_row = 0
    best_score = -1

    for i, row in preview.iterrows():
        values = [str(x).strip().lower() for x in row.tolist()]
        score = 0

        if any(v in {"account", "description"} for v in values):
            score += 5
        if any(re.search(r"20\d{2}|30 june|30 jun|year", v) for v in values):
            score += 2
        if sum(1 for v in values if v not in {"", "nan", "none"}) >= 2:
            score += 1

        if score > best_score:
            best_score = score
            best_row = i

        if score >= 6:
            logger.info("Data header detected at row %s in %s", i, filepath)
            return i

    logger.warning("Could not confidently detect header row in %s; using row %s", filepath, best_row)
    return best_row


def _normalise_column_names(columns: Iterable) -> List[str]:
    seen = {}
    output = []
    for idx, col in enumerate(columns):
        name = str(col).strip() if str(col).strip() else f"Column {idx + 1}"
        if name.lower().startswith("unnamed"):
            name = f"Column {idx + 1}"
        count = seen.get(name, 0)
        seen[name] = count + 1
        if count:
            name = f"{name}_{count + 1}"
        output.append(name)
    return output


def detect_account_col(df: pd.DataFrame) -> str:
    for col in df.columns:
        name = str(col).strip().lower()
        if name in {"account", "description", "account name"}:
            return col

    # Fallback: choose the first mostly-text column.
    best_col = df.columns[0]
    best_text_count = -1
    for col in df.columns:
        text_count = df[col].astype(str).str.contains(r"[A-Za-z]", regex=True, na=False).sum()
        if text_count > best_text_count:
            best_text_count = text_count
            best_col = col
    return best_col


def _is_percentage_or_variance_col(col_name: str) -> bool:
    text = str(col_name).strip().lower()
    return "%" in text or "variance %" in text or text in {"var %", "variance percentage"}


def detect_amount_cols(df: pd.DataFrame, account_col: Optional[str] = None) -> List[str]:
    if account_col is None:
        account_col = detect_account_col(df)

    amount_cols = []
    for col in df.columns:
        if col == account_col:
            continue
        if _is_percentage_or_variance_col(str(col)):
            continue

        cleaned = df[col].apply(clean_amount)
        raw_has_digits = df[col].astype(str).str.contains(r"\d", regex=True, na=False)
        numeric_like_count = raw_has_digits.sum()
        non_zero_count = (cleaned != 0).sum()

        if numeric_like_count >= max(2, len(df) * 0.15) or non_zero_count >= 1:
            amount_cols.append(col)

    return amount_cols


def choose_current_amount_col(df: pd.DataFrame, amount_cols: List[str]) -> str:
    if not amount_cols:
        raise ValueError("No amount columns detected in cleaned report.")

    # Prefer first year/date column. Xero exports commonly list current period first.
    for col in amount_cols:
        text = str(col).lower()
        if re.search(r"20\d{2}|30 june|30 jun|year", text) and not re.search(r"variance|budget", text):
            return col

    return amount_cols[0]


def detect_report_structure(df: pd.DataFrame) -> ReportStructure:
    account_col = detect_account_col(df)
    amount_cols = detect_amount_cols(df, account_col)
    current_amount_col = choose_current_amount_col(df, amount_cols)
    return ReportStructure(account_col, amount_cols, current_amount_col)


# Backward-compatible alias for older imports.
def _detect_amount_col(df: pd.DataFrame) -> str:
    return detect_report_structure(df).current_amount_col


# ---------------------------------------------------------------------------
# Row cleaning / extraction
# ---------------------------------------------------------------------------
def standardise_account_names(series: pd.Series) -> pd.Series:
    def clean_name(value) -> str:
        if pd.isna(value):
            return ""
        text = str(value).replace("\n", " ").strip()
        text = re.sub(r"\s+", " ", text)
        return text

    return series.apply(clean_name)


def _is_data_row(account_name: str) -> bool:
    text = str(account_name or "").strip().lower()
    return text not in NON_DATA_ACCOUNT_WORDS


def add_row_type(df: pd.DataFrame, account_col: str) -> pd.DataFrame:
    out = df.copy()

    def row_type(account_name: str) -> str:
        text = str(account_name or "").strip().lower()
        if not text:
            return "blank"
        if text.startswith("total") or text in {"gross profit", "net profit", "net assets"}:
            return "total"
        if text in {
            "trading income",
            "cost of sales",
            "other income",
            "operating expenses",
            "assets",
            "liabilities",
            "equity",
            "current assets",
            "current liabilities",
            "non-current assets",
            "non-current liabilities",
        }:
            return "heading"
        return "account"

    out["Row Type"] = out[account_col].apply(row_type)
    return out


def clean_report(filepath: str, report_label: str) -> pd.DataFrame:
    logger.info("Cleaning %s from %s", report_label, filepath)
    start_row = find_data_start_row(filepath)
    df = pd.read_excel(filepath, header=start_row)
    df.columns = _normalise_column_names(df.columns)

    df.dropna(how="all", inplace=True)
    df.dropna(axis=1, how="all", inplace=True)
    df.reset_index(drop=True, inplace=True)

    structure = detect_report_structure(df)
    account_col = structure.account_col

    df[account_col] = standardise_account_names(df[account_col])
    df = df[df[account_col].apply(_is_data_row)].copy()

    for col in structure.amount_cols:
        df[col] = clean_amount_column(df[col])

    df = add_row_type(df, account_col)
    logger.info(
        "%s cleaned: %s rows, account_col=%s, amount_cols=%s, current=%s",
        report_label,
        len(df),
        account_col,
        structure.amount_cols,
        structure.current_amount_col,
    )
    return df


def extract_value(
    df: pd.DataFrame,
    aliases: List[str],
    amount_col: Optional[str] = None,
    account_col: Optional[str] = None,
) -> Optional[float]:
    """Return matched amount, including a true 0.0. Return None only if not found."""
    if account_col is None:
        account_col = detect_account_col(df)
    if amount_col is None:
        amount_col = _detect_amount_col(df)

    names = df[account_col].astype(str).str.strip().str.lower()

    for alias in aliases:
        alias_text = alias.strip().lower()
        # Prefer exact match, then contains match.
        exact = df[names == alias_text]
        matches = exact if not exact.empty else df[names.str.contains(re.escape(alias_text), na=False)]

        if not matches.empty:
            # Last match usually captures the final total if Xero has subtotals above it.
            return clean_amount(matches.iloc[-1][amount_col])

    return None


def load_raw_reports() -> tuple[pd.DataFrame, pd.DataFrame]:
    import os

    if not os.path.exists(PL_RAW_PATH):
        raise FileNotFoundError(f"P&L not found: {PL_RAW_PATH}")
    if not os.path.exists(BS_RAW_PATH):
        raise FileNotFoundError(f"Balance Sheet not found: {BS_RAW_PATH}")

    raw_pl = pd.read_excel(PL_RAW_PATH, header=None)
    raw_bs = pd.read_excel(BS_RAW_PATH, header=None)
    logger.info("Raw P&L rows=%s | Raw BS rows=%s", len(raw_pl), len(raw_bs))
    return raw_pl, raw_bs


def load_clean_reports() -> tuple[pd.DataFrame, pd.DataFrame]:
    return (
        clean_report(PL_RAW_PATH, "Profit and Loss"),
        clean_report(BS_RAW_PATH, "Balance Sheet"),
    )
