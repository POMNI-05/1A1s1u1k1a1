# v1_selenium/reconciler.py
"""
Small extraction/check helpers used by workpaper_builder.py and tests.
"""

from __future__ import annotations

import logging
from typing import Optional

import pandas as pd

from cleaner import (
    NET_PROFIT_ALIASES,
    TOTAL_ASSETS_ALIASES,
    TOTAL_EQUITY_ALIASES,
    TOTAL_LIABILITIES_ALIASES,
    NET_ASSETS_ALIASES,
    _detect_amount_col,
    clean_amount,
    detect_account_col,
    extract_value,
)
from config import TAX_RATE

logger = logging.getLogger(__name__)


def _last_numeric_total_fallback(df: pd.DataFrame, amount_col: str, account_col: str) -> Optional[float]:
    """Fallback only when aliases fail. Prefer total/net rows near the bottom."""
    temp = df.copy()
    temp["_amount"] = temp[amount_col].apply(clean_amount)
    temp["_name"] = temp[account_col].astype(str).str.lower().str.strip()

    likely_total = temp[temp["_name"].str.contains(r"net profit|profit.*loss|current year earnings|total", regex=True, na=False)]
    if not likely_total.empty:
        return clean_amount(likely_total.iloc[-1][amount_col])

    numeric = temp[temp["_amount"] != 0]
    if not numeric.empty:
        return clean_amount(numeric.iloc[-1][amount_col])

    return None


def extract_pl_values(pl_df: pd.DataFrame) -> dict:
    amount_col = _detect_amount_col(pl_df)
    account_col = detect_account_col(pl_df)
    logger.info("P&L current amount column detected: %s", amount_col)

    net_profit = extract_value(pl_df, NET_PROFIT_ALIASES, amount_col, account_col)
    extraction_method = "alias match"

    if net_profit is None:
        logger.warning("Net profit not found by alias; using fallback total search.")
        net_profit = _last_numeric_total_fallback(pl_df, amount_col, account_col)
        extraction_method = "fallback total search"

    if net_profit is None:
        net_profit = 0.0
        extraction_method = "not found - defaulted to zero"
        logger.error("No net profit could be extracted from P&L.")

    logger.info("Net profit extracted: %.2f (%s)", net_profit, extraction_method)
    return {
        "net_profit": net_profit,
        "amount_col": amount_col,
        "account_col": account_col,
        "extraction_method": extraction_method,
    }


def extract_bs_values(bs_df: pd.DataFrame) -> dict:
    amount_col = _detect_amount_col(bs_df)
    account_col = detect_account_col(bs_df)
    logger.info("BS current amount column detected: %s", amount_col)

    total_assets = extract_value(bs_df, TOTAL_ASSETS_ALIASES, amount_col, account_col)
    total_liabilities = extract_value(bs_df, TOTAL_LIABILITIES_ALIASES, amount_col, account_col)
    total_equity = extract_value(bs_df, TOTAL_EQUITY_ALIASES, amount_col, account_col)
    net_assets = extract_value(bs_df, NET_ASSETS_ALIASES, amount_col, account_col)

    # Do not treat missing as true zero silently: expose missing flags.
    missing = []
    if total_assets is None:
        missing.append("total_assets")
        total_assets = 0.0
    if total_liabilities is None:
        missing.append("total_liabilities")
        total_liabilities = 0.0
    if total_equity is None:
        missing.append("total_equity")
        total_equity = 0.0

    if net_assets is None:
        net_assets = total_assets - total_liabilities

    equation_diff = round(total_assets - (total_liabilities + total_equity), 2)

    return {
        "total_assets": total_assets,
        "total_liabilities": total_liabilities,
        "total_equity": total_equity,
        "net_assets": net_assets,
        "equation_diff": equation_diff,
        "missing": missing,
        "amount_col": amount_col,
        "account_col": account_col,
    }


def build_reconciliation(pl_df: pd.DataFrame, bs_df: pd.DataFrame) -> pd.DataFrame:
    """Simple test reconciliation. The full tax workpaper is in workpaper_builder.py."""
    pl_vals = extract_pl_values(pl_df)
    bs_vals = extract_bs_values(bs_df)

    net_profit = pl_vals["net_profit"]
    tax_payable = max(net_profit, 0) * TAX_RATE

    rows = [
        {"Description": "Net Profit / (Loss) per P&L", "Amount": net_profit, "Status": "OK"},
        {"Description": f"Tax Payable at {TAX_RATE:.0%}", "Amount": tax_payable, "Status": "Calculated"},
        {"Description": "Total Assets", "Amount": bs_vals["total_assets"], "Status": "Extracted"},
        {"Description": "Total Liabilities", "Amount": bs_vals["total_liabilities"], "Status": "Extracted"},
        {"Description": "Total Equity", "Amount": bs_vals["total_equity"], "Status": "Extracted"},
        {
            "Description": "Accounting Equation Difference: Assets - (Liabilities + Equity)",
            "Amount": bs_vals["equation_diff"],
            "Status": "PASS" if abs(bs_vals["equation_diff"]) <= 1 else "REVIEW",
        },
    ]
    return pd.DataFrame(rows)