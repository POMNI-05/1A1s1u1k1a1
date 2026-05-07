# v1_selenium/cleaner.py
"""Parse/chunk Xero P&L and Balance Sheet exports without changing evidence."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import pandas as pd

from config import BS_RAW_PATH, PL_RAW_PATH

logger = logging.getLogger(__name__)

NET_PROFIT_ALIASES = [
    "net profit", "net loss", "net profit / loss", "net profit/(loss)",
    "profit before tax", "accounting profit before tax", "profit (loss)",
]
TOTAL_ASSETS_ALIASES = ["total assets"]
TOTAL_LIABILITIES_ALIASES = ["total liabilities"]
TOTAL_EQUITY_ALIASES = ["total equity"]
NET_ASSETS_ALIASES = ["net assets"]

HELPER_COLS = {
    "source row", "row type", "report section", "itr ref", "itr label",
    "treatment", "confidence", "review note", "label reason",
}

@dataclass(frozen=True)
class ReportStructure:
    account_col: str
    amount_cols: list[str]
    current_amount_col: str


def clean_amount(value) -> float:
    if pd.isna(value):
        return 0.0
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    s = str(value).strip()
    if s.lower() in {"", "nan", "none", "-", "--"}:
        return 0.0
    negative = s.startswith("(") and s.endswith(")")
    if negative:
        s = s[1:-1]
    s = re.sub(r"[$,%\s,]", "", s)
    try:
        number = float(s)
    except ValueError:
        return 0.0
    return -number if negative else number


def find_data_start_row(filepath: str | Path, scan_rows: int = 80) -> int:
    preview = pd.read_excel(filepath, header=None, nrows=scan_rows)
    best_row, best_score = 0, -1
    for i, row in preview.iterrows():
        values = [str(x).strip().lower() for x in row.tolist()]
        score = 0
        if any(v in {"account", "description", "account name"} for v in values):
            score += 6
        if any(re.search(r"20\d{2}|30 june|30 jun|year", v) for v in values):
            score += 2
        if sum(v not in {"", "nan", "none"} for v in values) >= 2:
            score += 1
        if score > best_score:
            best_row, best_score = i, score
        if score >= 7:
            return i
    logger.warning("Weak header detection for %s; using row %s", filepath, best_row)
    return best_row


def _normalise_column_names(columns: Iterable) -> list[str]:
    seen: dict[str, int] = {}
    out = []
    for idx, col in enumerate(columns):
        name = str(col).strip()
        if not name or name.lower().startswith("unnamed"):
            name = f"Column {idx + 1}"
        count = seen.get(name, 0)
        seen[name] = count + 1
        out.append(name if count == 0 else f"{name}_{count + 1}")
    return out


def detect_account_col(df: pd.DataFrame) -> str:
    for col in df.columns:
        if str(col).strip().lower() in {"account", "description", "account name"}:
            return col
    best = df.columns[0]
    best_text = -1
    for col in df.columns:
        text_count = df[col].astype(str).str.contains(r"[A-Za-z]", na=False, regex=True).sum()
        if text_count > best_text:
            best, best_text = col, text_count
    return best


def detect_amount_cols(df: pd.DataFrame, account_col: str | None = None) -> list[str]:
    account_col = account_col or detect_account_col(df)
    amount_cols: list[str] = []
    for col in df.columns:
        lower = str(col).strip().lower()
        if col == account_col or lower in HELPER_COLS or "variance" in lower or "%" in lower:
            continue
        cleaned = df[col].apply(clean_amount)
        raw_has_digits = df[col].astype(str).str.contains(r"\d", na=False, regex=True)
        if raw_has_digits.sum() >= max(2, len(df) * 0.12) or (cleaned != 0).sum() >= 1:
            amount_cols.append(col)
    return amount_cols


def choose_current_amount_col(df: pd.DataFrame, amount_cols: list[str]) -> str:
    if not amount_cols:
        raise ValueError("No amount columns detected in Xero report.")
    for col in amount_cols:
        lower = str(col).lower()
        if re.search(r"20\d{2}|30 june|30 jun", lower) and "variance" not in lower:
            return col
    return amount_cols[0]


def detect_report_structure(df: pd.DataFrame) -> ReportStructure:
    account_col = detect_account_col(df)
    amount_cols = detect_amount_cols(df, account_col)
    return ReportStructure(account_col, amount_cols, choose_current_amount_col(df, amount_cols))


def _detect_amount_col(df: pd.DataFrame) -> str:
    return detect_report_structure(df).current_amount_col


def standardise_account_names(series: pd.Series) -> pd.Series:
    return series.apply(lambda v: re.sub(r"\s+", " ", str(v).replace("\n", " ")).strip() if not pd.isna(v) else "")


def _normalised_name(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def add_row_type(df: pd.DataFrame, account_col: str, amount_cols: list[str]) -> pd.DataFrame:
    out = df.copy()
    heading_names = {
        "trading income", "income", "revenue", "cost of sales", "cost of goods sold",
        "other income", "operating expenses", "expenses", "assets", "current assets",
        "non-current assets", "fixed assets", "liabilities", "current liabilities",
        "non-current liabilities", "equity", "bank",
    }
    total_exact = {
        "gross profit", "net profit", "net loss", "net profit / loss", "net profit/(loss)",
        "profit before tax", "accounting profit before tax", "net assets", "total income",
        "total expenses", "total trading income", "total cost of sales", "total other income",
        "total operating expenses", "total assets", "total liabilities", "total equity",
    }

    def row_type(row) -> str:
        text = _normalised_name(row.get(account_col, ""))
        if text in {"", "nan", "none"}:
            return "blank"
        if text in heading_names:
            return "heading"
        if text in total_exact or text.startswith("total "):
            return "total"
        # Heading rows normally have no value in amount columns.
        if text and all(abs(clean_amount(row.get(c, 0))) < 0.005 for c in amount_cols) and text in heading_names:
            return "heading"
        return "account"

    out["Row Type"] = out.apply(row_type, axis=1)
    return out


def add_report_section(df: pd.DataFrame, account_col: str) -> pd.DataFrame:
    out = df.copy()
    current = ""
    sections = []
    for _, row in out.iterrows():
        if str(row.get("Row Type", "")).lower() == "heading":
            current = str(row.get(account_col, "")).strip()
        sections.append(current)
    out["Report Section"] = sections
    return out


def clean_report(filepath: str | Path, report_label: str) -> pd.DataFrame:
    logger.info("Parsing %s from %s", report_label, filepath)
    start_row = find_data_start_row(filepath)
    df = pd.read_excel(filepath, header=start_row)
    df.columns = _normalise_column_names(df.columns)
    df["Source Row"] = [start_row + 2 + i for i in range(len(df))]
    df = df.dropna(how="all").dropna(axis=1, how="all").reset_index(drop=True)

    structure = detect_report_structure(df)
    account_col = structure.account_col
    df[account_col] = standardise_account_names(df[account_col])
    df = df[~df[account_col].str.lower().isin({"", "nan", "none", "account", "description"})].copy()

    for col in structure.amount_cols:
        df[col] = df[col].apply(clean_amount)

    df = add_row_type(df, account_col, structure.amount_cols)
    df = add_report_section(df, account_col)
    logger.info("%s parsed rows=%s account_col=%s amount_cols=%s", report_label, len(df), account_col, structure.amount_cols)
    return df


def extract_value(df: pd.DataFrame, aliases: list[str], amount_col: str | None = None, account_col: str | None = None) -> float | None:
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


def load_raw_reports() -> tuple[pd.DataFrame, pd.DataFrame]:
    if not Path(PL_RAW_PATH).exists():
        raise FileNotFoundError(f"P&L not found: {PL_RAW_PATH}")
    if not Path(BS_RAW_PATH).exists():
        raise FileNotFoundError(f"Balance Sheet not found: {BS_RAW_PATH}")
    return pd.read_excel(PL_RAW_PATH, header=None), pd.read_excel(BS_RAW_PATH, header=None)


def load_clean_reports() -> tuple[pd.DataFrame, pd.DataFrame]:
    return clean_report(PL_RAW_PATH, "Profit and Loss"), clean_report(BS_RAW_PATH, "Balance Sheet")
